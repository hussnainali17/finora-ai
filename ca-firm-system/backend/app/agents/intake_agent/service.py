# ruff: noqa: E501
"""Agent 1 orchestration: claim a document, parse it, persist structured REVIEW data.

State machine: document uploaded|queued -> processing -> processed|failed. Every attempt is an
immutable-ish ``extraction_runs`` row (versioned); the newest is ``is_current``. A failed or
interrupted run never leaves half-written tables: results are written in one transaction.
The original file is only ever read."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.intake_agent.llm import GatewayAssistant, IntakeAssistant
from app.agents.intake_agent.parsers.csv_parser import parse_csv
from app.agents.intake_agent.parsers.excel import parse_xls, parse_xlsx
from app.agents.intake_agent.parsers.ocr import OcrEngine, OcrMyPdfEngine, image_to_pdf
from app.agents.intake_agent.parsers.pdf import parse_pdf
from app.agents.intake_agent.pipeline import PARSER_VERSION, TableDraft, build_tables
from app.agents.intake_agent.types import ExtractionError, FindingDraft, ParsedFile
from app.core.config import Settings
from app.integrations.storage.s3 import ObjectStore
from app.llm.gateway import LlmGateway
from app.models import (
    AccountingPeriod,
    DataQualityFinding,
    Document,
    ExtractedColumn,
    ExtractedRow,
    ExtractedTable,
    ExtractionRun,
)
from app.services.audit import record_audit

logger = logging.getLogger("app.intake")
MAX_AUTO_ATTEMPTS = 3
ROW_INSERT_CHUNK = 2000
CLAIMABLE = ("uploaded", "queued")


def default_ocr_engine(settings: Settings) -> OcrEngine | None:
    if not settings.intake_ocr_enabled:
        return None
    return OcrMyPdfEngine(settings.intake_ocr_language, settings.intake_ocr_timeout_seconds)


def default_assistant(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    firm_id: uuid.UUID,
    client_id: uuid.UUID,
) -> IntakeAssistant | None:
    if not settings.intake_llm_enabled:
        return None
    return GatewayAssistant(LlmGateway(sessionmaker, settings), firm_id, client_id)


def parse_bytes(
    filename: str, data: bytes, settings: Settings, ocr_engine: OcrEngine | None
) -> ParsedFile:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "xlsx":
        return parse_xlsx(data, settings.intake_max_rows, settings.intake_max_uncompressed_bytes)
    if ext == "xls":
        return parse_xls(data, settings.intake_max_rows)
    if ext == "csv":
        return parse_csv(data, settings.intake_max_rows)
    if ext == "pdf":
        return parse_pdf(
            data, max_pages=settings.intake_max_pages, max_rows=settings.intake_max_rows,
            ocr_engine=ocr_engine,
        )  # fmt: skip
    if ext in ("png", "jpg", "jpeg"):
        if ocr_engine is None:
            raise ExtractionError("ocr_unavailable", "Images need OCR, which is disabled")
        return parse_pdf(
            image_to_pdf(data), max_pages=1, max_rows=settings.intake_max_rows,
            ocr_engine=ocr_engine,
        )  # fmt: skip
    raise ExtractionError("unsupported_type", f"Cannot extract data from .{ext or 'unknown'} files")


# ----------------------------------------------------------------------------- claiming


async def claim_document(
    session: AsyncSession, doc: Document, *, trigger: str, actor_user_id: uuid.UUID | None
) -> ExtractionRun:
    """Marks the document processing and opens a new run. Caller commits."""
    last = await session.scalar(
        select(func.max(ExtractionRun.version)).where(ExtractionRun.document_id == doc.id)
    )
    await session.execute(
        update(ExtractionRun)
        .where(ExtractionRun.document_id == doc.id, ExtractionRun.is_current.is_(True))
        .values(is_current=False)
    )
    run = ExtractionRun(
        id=uuid.uuid4(), firm_id=doc.firm_id, client_id=doc.client_id, period_id=doc.period_id,
        document_id=doc.id, version=(last or 0) + 1, is_current=True, status="running",
        trigger=trigger, parser_version=PARSER_VERSION, created_by=actor_user_id,
    )  # fmt: skip
    session.add(run)
    doc.status = "processing"
    await session.flush()
    return run


async def claim_next(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Atomically claims one uploaded/queued document (safe with many runner replicas)."""
    async with sessionmaker() as session, session.begin():
        doc = await session.scalar(
            select(Document)
            .where(Document.status.in_(CLAIMABLE), Document.deleted_at.is_(None))
            .order_by(Document.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if doc is None:
            return None
        run = await claim_document(session, doc, trigger="auto", actor_user_id=None)
        return doc.id, run.id


async def reclaim_stale(sessionmaker: async_sessionmaker[AsyncSession], settings: Settings) -> int:
    """Runs left 'running' by a crashed worker are failed and their documents re-queued (bounded)."""
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.intake_stale_after_minutes)
    n = 0
    async with sessionmaker() as session, session.begin():
        stale = (
            await session.scalars(
                select(ExtractionRun)
                .where(ExtractionRun.status == "running", ExtractionRun.started_at < cutoff)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for run in stale:
            run.status, run.finished_at = "failed", datetime.now(UTC)
            run.error_code, run.error_message = "interrupted", "Processing was interrupted"
            attempts = await session.scalar(
                select(func.count()).select_from(ExtractionRun).where(
                    ExtractionRun.document_id == run.document_id,
                    ExtractionRun.error_code == "interrupted",
                )
            )  # fmt: skip
            doc = await session.get(Document, run.document_id)
            if doc is not None and doc.status == "processing":
                doc.status = "queued" if (attempts or 0) < MAX_AUTO_ATTEMPTS else "failed"
            n += 1
    return n


# ----------------------------------------------------------------------------- processing


async def process_run(
    sessionmaker: async_sessionmaker[AsyncSession],
    store: ObjectStore,
    settings: Settings,
    *,
    document_id: uuid.UUID,
    run_id: uuid.UUID,
    assistant: IntakeAssistant | None = None,
    ocr_engine: OcrEngine | None = None,
) -> bool:
    """Executes a claimed run. Returns True on success. Never raises for bad input files."""
    async with sessionmaker() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            return False
        key, filename, category = doc.object_key, doc.original_filename, doc.category
        firm_id, client_id, period_id = doc.firm_id, doc.client_id, doc.period_id
        carried_roles, carried_types = await _carried_decisions(session, document_id, run_id)
        period = await session.get(AccountingPeriod, period_id)
        period_range = (period.start_date, period.end_date) if period else None
    try:
        data = await asyncio.to_thread(lambda: b"".join(store.iter_chunks(key)))
        engine = ocr_engine if ocr_engine is not None else default_ocr_engine(settings)
        parsed = await asyncio.to_thread(parse_bytes, filename, data, settings, engine)
        tables = await build_tables(
            parsed, category=category, default_date_order=settings.intake_default_date_order,
            assistant=assistant
            if assistant is not None
            else default_assistant(settings, sessionmaker, firm_id, client_id),
            llm_min_confidence=settings.intake_llm_min_confidence, carried_roles=carried_roles,
        )  # fmt: skip
        if not tables:
            raise ExtractionError("no_content", "No tabular data could be found in this file")
        for t in tables:
            _check_period(t, period_range)
        top_findings = list(parsed.findings)
    except ExtractionError as exc:
        await _fail(sessionmaker, run_id, document_id, exc.code, exc.message, firm_id, client_id)
        return False
    except Exception:
        logger.exception("extraction crashed", extra={"document_id": str(document_id)})
        await _fail(sessionmaker, run_id, document_id, "internal_error",
                    "An unexpected error occurred while reading this file", firm_id, client_id)  # fmt: skip
        return False
    try:
        async with sessionmaker() as session, session.begin():
            await _persist(
                session,
                firm_id,
                client_id,
                period_id,
                document_id,
                run_id,
                tables,
                top_findings,
                carried_types,
            )
    except Exception:
        logger.exception("persisting extraction failed", extra={"document_id": str(document_id)})
        await _fail(sessionmaker, run_id, document_id, "persist_failed",
                    "Extracted data could not be saved", firm_id, client_id)  # fmt: skip
        return False
    return True


def _check_period(t: TableDraft, rng: tuple[Any, Any] | None) -> None:
    if rng is None or t.period_end is None:
        return
    start, end = rng
    if not (start <= t.period_end <= end):
        t.findings.append(
            FindingDraft(
                "period_mismatch", "warning",
                f"The file states a period ending {t.period_end.isoformat()}, which is outside the "
                f"accounting period {start.isoformat()} to {end.isoformat()}.",
                details={"detected_end": t.period_end.isoformat()},
            )
        )  # fmt: skip


async def _carried_decisions(
    session: AsyncSession, document_id: uuid.UUID, run_id: uuid.UUID
) -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    """Human decisions from earlier runs of the same document, keyed by (sheet, header)."""
    roles: dict[tuple[str, str], str] = {}
    types: dict[str, str] = {}
    rows = await session.execute(
        select(ExtractedTable.name, ExtractedColumn.header_normalized, ExtractedColumn.confirmed_role)
        .join(ExtractedColumn, ExtractedColumn.table_id == ExtractedTable.id)
        .join(ExtractionRun, ExtractionRun.id == ExtractedTable.run_id)
        .where(
            ExtractedTable.document_id == document_id,
            ExtractionRun.id != run_id,
            ExtractedColumn.confirmed_role.is_not(None),
        )
        .order_by(ExtractionRun.version)
    )  # fmt: skip
    for name, header, role in rows:
        if header and role:
            roles[(name, header)] = role  # later versions overwrite earlier ones
    trows = await session.execute(
        select(ExtractedTable.name, ExtractedTable.confirmed_type)
        .join(ExtractionRun, ExtractionRun.id == ExtractedTable.run_id)
        .where(
            ExtractedTable.document_id == document_id,
            ExtractionRun.id != run_id,
            ExtractedTable.confirmed_type.is_not(None),
        )
        .order_by(ExtractionRun.version)
    )
    for name, ctype in trows:
        if ctype:
            types[name] = ctype
    return roles, types


async def _persist(
    session: AsyncSession,
    firm_id: uuid.UUID,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    run_id: uuid.UUID,
    tables: list[TableDraft],
    top_findings: list[FindingDraft],
    carried_types: dict[str, str],
) -> None:
    run = await session.get(ExtractionRun, run_id, with_for_update=True)
    doc = await session.get(Document, document_id, with_for_update=True)
    if run is None or doc is None or run.status != "running":
        raise RuntimeError("run is no longer active")
    n_rows = n_findings = 0
    need_review = False
    scope = {"firm_id": firm_id, "client_id": client_id, "period_id": period_id,
             "document_id": document_id}  # fmt: skip

    def add_finding(f: FindingDraft, table_id: uuid.UUID | None) -> None:
        nonlocal n_findings
        session.add(
            DataQualityFinding(
                run_id=run_id, table_id=table_id, row_index=f.row_index, col_index=f.col_index,
                code=f.code, severity=f.severity, message=f.message, details=f.details,
                source_ref=f.source_ref, origin=f.origin, **scope,
            )
        )  # fmt: skip
        n_findings += 1

    for f in top_findings:
        add_finding(f, None)
    for ordinal, t in enumerate(tables):
        tid = uuid.uuid4()
        ctype = carried_types.get(t.name)
        session.add(
            ExtractedTable(
                id=tid, run_id=run_id, ordinal=ordinal, name=t.name[:300], kind=t.kind,
                source_ref=t.source_ref, n_rows=len(t.raw_rows), n_cols=len(t.columns),
                header_row=t.header_row, has_header=t.has_header, detected_type=t.detected_type,
                type_confidence=t.type_confidence, type_source=t.type_source, confirmed_type=ctype,
                detected_currency=t.currency, period_start=t.period_start, period_end=t.period_end,
                status=t.status, table_metadata=t.metadata, **scope,
            )
        )  # fmt: skip
        await session.flush()
        for c in t.columns:
            session.add(
                ExtractedColumn(
                    table_id=tid, col_index=c.col_index, letter=c.letter, header_raw=c.header_raw,
                    header_normalized=c.header_normalized[:300], header_synthetic=c.header_synthetic,
                    suggested_role=c.role, confidence=c.confidence, role_source=c.source,
                    confirmed_role=c.confirmed_role,
                )
            )  # fmt: skip
        batch: list[dict[str, Any]] = []
        for i, raw in enumerate(t.raw_rows):
            batch.append(
                {
                    "table_id": tid, "row_index": t.row_numbers[i], "source_ref": t.row_refs[i],
                    "raw": {str(ci): cell.to_json() for ci, cell in enumerate(raw) if cell is not None},
                    "normalized": t.normalized.rows[i], "flags": t.normalized.flags[i],
                }
            )  # fmt: skip
            if len(batch) >= ROW_INSERT_CHUNK:
                await session.execute(insert(ExtractedRow), batch)
                batch = []
        if batch:
            await session.execute(insert(ExtractedRow), batch)
        n_rows += len(t.raw_rows)
        for f in t.findings:
            add_finding(f, tid)
        need_review = need_review or t.status == "needs_review"

    run.status, run.finished_at = "completed", datetime.now(UTC)
    run.summary = {
        "tables": len(tables), "rows": n_rows, "findings": n_findings,
        "needs_review": need_review,
        "types": [t.detected_type for t in tables],
    }  # fmt: skip
    run.llm_used = any(t.llm_used for t in tables)
    run.llm_model = next((t.llm_model for t in tables if t.llm_model), None)
    doc.status = "processed"
    record_audit(
        session, action="extraction.completed", actor_user_id=run.created_by, firm_id=firm_id,
        actor_email=None if run.created_by else "system:intake", target_type="document",
        target_id=document_id, client_id=client_id,
        metadata={"run_id": str(run_id), "version": run.version, **run.summary},
    )  # fmt: skip


async def _fail(
    sessionmaker: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    document_id: uuid.UUID,
    code: str,
    message: str,
    firm_id: uuid.UUID,
    client_id: uuid.UUID,
) -> None:
    async with sessionmaker() as session, session.begin():
        run = await session.get(ExtractionRun, run_id, with_for_update=True)
        doc = await session.get(Document, document_id, with_for_update=True)
        if run is None or doc is None:
            return
        run.status, run.finished_at = "failed", datetime.now(UTC)
        run.error_code, run.error_message = code, message[:500]
        doc.status = "failed"
        record_audit(
            session, action="extraction.failed", actor_user_id=run.created_by, firm_id=firm_id,
            actor_email=None if run.created_by else "system:intake", target_type="document",
            target_id=document_id, client_id=client_id, outcome="failure",
            metadata={"run_id": str(run_id), "error_code": code},
        )  # fmt: skip


async def extract_document(
    sessionmaker: async_sessionmaker[AsyncSession],
    store: ObjectStore,
    settings: Settings,
    document_id: uuid.UUID,
    *,
    trigger: str = "auto",
    actor_user_id: uuid.UUID | None = None,
    assistant: IntakeAssistant | None = None,
    ocr_engine: OcrEngine | None = None,
) -> uuid.UUID | None:
    """Claim + process one specific document (used by tests, re-runs and the CLI)."""
    async with sessionmaker() as session, session.begin():
        doc = await session.scalar(
            select(Document)
            .where(Document.id == document_id, Document.deleted_at.is_(None))
            .with_for_update()
        )
        if doc is None or doc.status == "processing":
            return None
        run = await claim_document(session, doc, trigger=trigger, actor_user_id=actor_user_id)
        run_id = run.id
    await process_run(
        sessionmaker, store, settings, document_id=document_id, run_id=run_id,
        assistant=assistant, ocr_engine=ocr_engine,
    )  # fmt: skip
    return run_id


# ----------------------------------------------------------------------------- runner


async def run_intake_loop(
    sessionmaker: async_sessionmaker[AsyncSession],
    store: ObjectStore,
    settings: Settings,
    stop: asyncio.Event,
) -> None:
    logger.info("intake runner started")
    while not stop.is_set():
        try:
            await reclaim_stale(sessionmaker, settings)
            while not stop.is_set():
                claimed = await claim_next(sessionmaker)
                if claimed is None:
                    break
                await process_run(
                    sessionmaker, store, settings, document_id=claimed[0], run_id=claimed[1]
                )
        except Exception:
            logger.exception("intake runner iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.intake_poll_interval_seconds)
        except TimeoutError:
            pass
    logger.info("intake runner stopped")
