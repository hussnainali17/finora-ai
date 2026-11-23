"""Central Document Intelligence Service.

Extracts generic document-processing responsibilities from the Accounting module
into a unified, reusable service shared by Accounting, Taxation, and Audit:
- File upload and validation.
- OCR and text extraction.
- Generic document classification & category verification.
- Generic structured data extraction (tables, columns, rows).
- Extraction quality validation & period consistency checks.
- Document metadata management & mismatch flagging.
- Unique source document ID generation and complete traceability.
- Module routing and cross-module shared document referencing.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import UploadFile
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.intake_agent.llm import GatewayAssistant, IntakeAssistant
from app.agents.intake_agent.normalize import normalize_rows
from app.agents.intake_agent.parsers.csv_parser import parse_csv
from app.agents.intake_agent.parsers.excel import parse_xls, parse_xlsx
from app.agents.intake_agent.parsers.ocr import OcrEngine, OcrMyPdfEngine, image_to_pdf
from app.agents.intake_agent.parsers.pdf import parse_pdf
from app.agents.intake_agent.pipeline import PARSER_VERSION, TableDraft, build_tables
from app.agents.intake_agent.types import ExtractionError, FindingDraft, ParsedFile
from app.core.config import Settings
from app.core.errors import (
    AppError,
    ConflictError,
    DomainValidationError,
    DuplicateDocumentError,
    NotFoundError,
    UnsupportedMediaTypeError,
)
from app.document_intelligence.categories import (
    ALL_CATEGORIES,
    is_valid_category_for_module,
    normalize_category_for_module,
)
from app.document_intelligence.classifier import ClassificationVerification, verify_category
from app.document_intelligence.workflow import create_document_intelligence_graph
from app.integrations.storage.s3 import ObjectStore
from app.llm.gateway import LlmGateway
from app.models import (
    AccountingPeriod,
    DataQualityFinding,
    Document,
    DocumentModuleReference,
    ExtractedColumn,
    ExtractedRow,
    ExtractedTable,
    ExtractionRun,
)
from app.services import uploads
from app.services.audit import record_audit
from app.services.authz import Principal, get_accessible_client, require_permission
from app.services.outbox import enqueue_event

logger = logging.getLogger("app.document_intelligence.service")

MAX_AUTO_ATTEMPTS = 3
ROW_INSERT_CHUNK = 2000
CLAIMABLE = ("uploaded", "queued")


def build_object_key(
    firm_id: uuid.UUID, client_id: uuid.UUID, period_id: uuid.UUID, doc_id: uuid.UUID
) -> str:
    return f"firms/{firm_id}/clients/{client_id}/periods/{period_id}/{doc_id}/original"


async def _scoped_period(
    session: AsyncSession, principal: Principal, client_id: uuid.UUID, period_id: uuid.UUID
) -> tuple[object, AccountingPeriod]:
    client = await get_accessible_client(session, principal, client_id)
    period = await session.scalar(
        select(AccountingPeriod).where(
            AccountingPeriod.id == period_id,
            AccountingPeriod.client_id == client.id,
            AccountingPeriod.firm_id == principal.firm_id,
        )
    )
    if period is None:
        raise NotFoundError("Accounting period not found")
    return client, period


def _duplicate(existing: Document) -> DuplicateDocumentError:
    return DuplicateDocumentError(
        f"This file was already uploaded to this period as {existing.original_filename}",
        existing_document_id=existing.id,
        existing_filename=existing.original_filename,
        existing_category=existing.category,
    )


async def _audit_failure(
    session: AsyncSession, principal: Principal, client_id: uuid.UUID, action: str, **meta: object
) -> None:
    await session.rollback()
    record_audit(
        session,
        action=action,
        actor=principal,
        target_type="document",
        client_id=client_id,
        outcome="failure",
        metadata=dict(meta),
    )
    await session.commit()


# -----------------------------------------------------------------------------
# 1. Central Upload & Ingestion
# -----------------------------------------------------------------------------


async def upload_and_ingest_document(
    session: AsyncSession,
    store: ObjectStore,
    settings: Settings,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    *,
    upload: UploadFile,
    category: str,
    module: str = "accounting",
    scanner: uploads.FileScanner | None = None,
) -> Document:
    """Central document upload with module-level categorization, validation,
    and unique document ID generation.
    """
    require_permission(principal, "document:upload")
    client, period = await _scoped_period(session, principal, client_id, period_id)
    if client.status != "active":  # type: ignore[attr-defined]
        raise ConflictError("Cannot upload to an archived client")
    if period.status != "open":
        raise ConflictError("This accounting period is closed; reopen it to upload files")

    mod = module.lower().strip()
    cat = normalize_category_for_module(mod, category)

    filename = uploads.sanitize_filename(upload.filename)
    ext = uploads.extension_of(filename)
    if not filename or ext not in settings.upload_extensions:
        await _audit_failure(
            session,
            principal,
            client_id,
            "document.upload_rejected",
            reason="type_not_allowed",
            extension=ext,
            module=mod,
        )
        allowed = ", ".join(sorted(settings.upload_extensions))
        raise UnsupportedMediaTypeError(f"Unsupported file type. Allowed: {allowed}")

    spooled = await uploads.spool_upload(upload, settings.max_upload_bytes)
    doc_id = uuid.uuid4()
    key = build_object_key(principal.firm_id, client_id, period_id, doc_id)
    stored = False
    try:
        try:
            content_type = uploads.verify_content(spooled, ext)
            await (scanner or uploads.NoopScanner()).scan(spooled.file, filename=filename)
        except AppError:
            await _audit_failure(
                session,
                principal,
                client_id,
                "document.upload_rejected",
                reason="content_mismatch",
                extension=ext,
                module=mod,
            )
            raise

        existing = await session.scalar(
            select(Document).where(
                Document.client_id == client_id,
                Document.period_id == period_id,
                Document.sha256 == spooled.sha256,
                Document.deleted_at.is_(None),
            )
        )
        if existing is not None:
            error = _duplicate(existing)
            await _audit_failure(
                session,
                principal,
                client_id,
                "document.duplicate_rejected",
                existing_document_id=error.extra["existing_document_id"],
                module=mod,
            )
            raise error

        await store.put(key, spooled.file, content_type=content_type, sha256=spooled.sha256)
        stored = True

        doc = Document(
            id=doc_id,
            firm_id=principal.firm_id,
            client_id=client_id,
            period_id=period_id,
            module=mod,
            category=cat,
            user_category=cat,  # Preserve the CA's exact selection as primary
            original_filename=filename,
            object_key=key,
            content_type=content_type,
            size_bytes=spooled.size,
            sha256=spooled.sha256,
            uploaded_by=principal.user_id,
        )
        session.add(doc)

        # Primary module reference
        primary_ref = DocumentModuleReference(
            id=uuid.uuid4(),
            firm_id=principal.firm_id,
            client_id=client_id,
            period_id=period_id,
            document_id=doc_id,
            module=mod,
            module_category=cat,
            is_primary=True,
            status="active",
        )
        session.add(primary_ref)

        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            existing = await session.scalar(
                select(Document).where(
                    Document.client_id == client_id,
                    Document.period_id == period_id,
                    Document.sha256 == spooled.sha256,
                    Document.deleted_at.is_(None),
                )
            )
            if existing is None:
                raise
            raise _duplicate(existing) from exc

        record_audit(
            session,
            action="document.uploaded",
            actor=principal,
            target_type="document",
            target_id=doc.id,
            client_id=client_id,
            metadata={
                "filename": filename,
                "category": cat,
                "module": mod,
                "size_bytes": spooled.size,
                "sha256": spooled.sha256,
                "period_id": str(period_id),
            },
        )
        enqueue_event(
            session,
            topic=settings.file_uploaded_topic,
            event_type="file.uploaded",
            partition_key=str(client_id),
            firm_id=principal.firm_id,
            client_id=client_id,
            period_id=period_id,
            payload={
                "document_id": str(doc.id),
                "module": mod,
                "category": cat,
                "object_key": key,
                "sha256": spooled.sha256,
                "size_bytes": spooled.size,
                "content_type": content_type,
            },
        )
        await session.commit()
        return doc
    except Exception:
        if stored:
            try:
                await store.delete(key)
            except Exception:
                logger.warning("storage rollback failed for %s", key, exc_info=True)
        raise
    finally:
        spooled.close()


# -----------------------------------------------------------------------------
# 2. Central Parsing, OCR, & Extraction Pipeline
# -----------------------------------------------------------------------------


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
            data,
            max_pages=settings.intake_max_pages,
            max_rows=settings.intake_max_rows,
            ocr_engine=ocr_engine,
        )
    if ext in ("png", "jpg", "jpeg"):
        if ocr_engine is None:
            raise ExtractionError("ocr_unavailable", "Images need OCR, which is disabled")
        return parse_pdf(
            image_to_pdf(data),
            max_pages=1,
            max_rows=settings.intake_max_rows,
            ocr_engine=ocr_engine,
        )
    raise ExtractionError("unsupported_type", f"Cannot extract data from .{ext or 'unknown'} files")


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
        id=uuid.uuid4(),
        firm_id=doc.firm_id,
        client_id=doc.client_id,
        period_id=doc.period_id,
        document_id=doc.id,
        version=(last or 0) + 1,
        is_current=True,
        status="running",
        trigger=trigger,
        parser_version=PARSER_VERSION,
        created_by=actor_user_id,
    )
    session.add(run)
    doc.status = "processing"
    await session.flush()
    return run


async def process_document_intelligence(
    sessionmaker: async_sessionmaker[AsyncSession],
    store: ObjectStore,
    settings: Settings,
    *,
    document_id: uuid.UUID,
    run_id: uuid.UUID,
    assistant: IntakeAssistant | None = None,
    ocr_engine: OcrEngine | None = None,
) -> bool:
    """Executes Central Document Intelligence on a claimed run.

    Performs:
    1. Object retrieval & OCR / text parsing
    2. Category verification & mismatch detection
    3. Structured table extraction
    4. Quality and period validation
    5. Persistence of extraction runs & findings
    6. Module routing & reference creation
    """
    async with sessionmaker() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            return False
        key = doc.object_key
        filename = doc.original_filename
        category = doc.category
        user_cat = doc.user_category or category
        module = doc.module or "accounting"
        firm_id, client_id, period_id = doc.firm_id, doc.client_id, doc.period_id
        period = await session.get(AccountingPeriod, period_id)
        period_range = (period.start_date, period.end_date) if period else None

    try:
        data = await asyncio.to_thread(lambda: b"".join(store.iter_chunks(key)))
        engine = ocr_engine if ocr_engine is not None else default_ocr_engine(settings)
        parsed = await asyncio.to_thread(parse_bytes, filename, data, settings, engine)

        # Build tables using existing generic pipeline
        tables = await build_tables(
            parsed,
            category=category,
            default_date_order=settings.intake_default_date_order,
            assistant=assistant
            if assistant is not None
            else default_assistant(settings, sessionmaker, firm_id, client_id),
            llm_min_confidence=settings.intake_llm_min_confidence,
        )
        if not tables:
            raise ExtractionError("no_content", "No tabular data could be found in this file")

        # Period check
        for t in tables:
            _check_period(t, period_range)

        # Collect text and headers for central classification verification
        table_headers = [c.header_normalized for t in tables for c in t.columns if c.header_normalized]
        sample_text = f"{filename} " + " ".join(table_headers)
        if parsed.grids and parsed.grids[0].rows:
            sample_text += " " + " ".join(
                str(c.v) for r in parsed.grids[0].rows[:10] for c in r if c is not None and c.v
            )

        # Run central category verification
        verification = verify_category(
            user_category=user_cat,
            module=module,
            filename=filename,
            text_content=sample_text,
            table_headers=table_headers,
        )

        top_findings = list(parsed.findings)
        if verification.is_mismatch:
            top_findings.append(
                FindingDraft(
                    code="category_mismatch",
                    severity="warning",
                    message=verification.explanation,
                    details={
                        "user_category": user_cat,
                        "detected_category": verification.detected_category,
                        "confidence": verification.confidence,
                        "module": module,
                    },
                    origin="central_doc_intel",
                )
            )

    except ExtractionError as exc:
        await _fail(sessionmaker, run_id, document_id, exc.code, exc.message, firm_id, client_id)
        return False
    except Exception:
        logger.exception("Central extraction failed for %s", document_id)
        await _fail(
            sessionmaker,
            run_id,
            document_id,
            "internal_error",
            "An unexpected error occurred while reading this file",
            firm_id,
            client_id,
        )
        return False

    try:
        async with sessionmaker() as session, session.begin():
            await _persist_central_extraction(
                session,
                firm_id=firm_id,
                client_id=client_id,
                period_id=period_id,
                document_id=document_id,
                run_id=run_id,
                tables=tables,
                top_findings=top_findings,
                verification=verification,
            )
    except Exception:
        logger.exception("Persisting central extraction failed for %s", document_id)
        await _fail(
            sessionmaker,
            run_id,
            document_id,
            "persist_failed",
            "Extracted data could not be saved",
            firm_id,
            client_id,
        )
        return False

    return True


def _check_period(t: TableDraft, rng: tuple[Any, Any] | None) -> None:
    if rng is None or t.period_end is None:
        return
    start, end = rng
    if not (start <= t.period_end <= end):
        t.findings.append(
            FindingDraft(
                "period_mismatch",
                "warning",
                f"The file states a period ending {t.period_end.isoformat()}, which is outside the "
                f"accounting period {start.isoformat()} to {end.isoformat()}.",
                details={"detected_end": t.period_end.isoformat()},
            )
        )


async def _persist_central_extraction(
    session: AsyncSession,
    firm_id: uuid.UUID,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    run_id: uuid.UUID,
    tables: list[TableDraft],
    top_findings: list[FindingDraft],
    verification: ClassificationVerification,
) -> None:
    run = await session.get(ExtractionRun, run_id, with_for_update=True)
    doc = await session.get(Document, document_id, with_for_update=True)
    if run is None or doc is None or run.status != "running":
        raise RuntimeError("run is no longer active")

    n_rows = n_findings = 0
    need_review = verification.is_mismatch
    scope = {
        "firm_id": firm_id,
        "client_id": client_id,
        "period_id": period_id,
        "document_id": document_id,
    }

    def add_finding(f: FindingDraft, table_id: uuid.UUID | None) -> None:
        nonlocal n_findings
        session.add(
            DataQualityFinding(
                run_id=run_id,
                table_id=table_id,
                row_index=f.row_index,
                col_index=f.col_index,
                code=f.code,
                severity=f.severity,
                message=f.message,
                details=f.details,
                source_ref=f.source_ref,
                origin=f.origin,
                **scope,
            )
        )
        n_findings += 1

    for f in top_findings:
        add_finding(f, None)

    for ordinal, t in enumerate(tables):
        tid = uuid.uuid4()
        session.add(
            ExtractedTable(
                id=tid,
                run_id=run_id,
                ordinal=ordinal,
                name=t.name[:300],
                kind=t.kind,
                source_ref=t.source_ref,
                n_rows=len(t.raw_rows),
                n_cols=len(t.columns),
                header_row=t.header_row,
                has_header=t.has_header,
                detected_type=t.detected_type,
                type_confidence=t.type_confidence,
                type_source=t.type_source,
                confirmed_type=None,
                detected_currency=t.currency,
                period_start=t.period_start,
                period_end=t.period_end,
                status=t.status,
                table_metadata=t.metadata,
                **scope,
            )
        )
        await session.flush()
        for c in t.columns:
            session.add(
                ExtractedColumn(
                    table_id=tid,
                    col_index=c.col_index,
                    letter=c.letter,
                    header_raw=c.header_raw,
                    header_normalized=c.header_normalized[:300],
                    header_synthetic=c.header_synthetic,
                    suggested_role=c.role,
                    confidence=c.confidence,
                    role_source=c.source,
                    confirmed_role=c.confirmed_role,
                )
            )
        batch: list[dict[str, Any]] = []
        for i, raw in enumerate(t.raw_rows):
            batch.append(
                {
                    "table_id": tid,
                    "row_index": t.row_numbers[i],
                    "source_ref": t.row_refs[i],
                    "raw": {
                        str(ci): cell.to_json()
                        for ci, cell in enumerate(raw)
                        if cell is not None
                    },
                    "normalized": t.normalized.rows[i],
                    "flags": t.normalized.flags[i],
                }
            )
            if len(batch) >= ROW_INSERT_CHUNK:
                await session.execute(insert(ExtractedRow), batch)
                batch = []
        if batch:
            await session.execute(insert(ExtractedRow), batch)
        n_rows += len(t.raw_rows)
        for f in t.findings:
            add_finding(f, tid)
        need_review = need_review or (t.status == "needs_review")

    # Update Document metadata with Central Document Intelligence results
    # User selection is preserved as primary; mismatch is flagged for CA confirmation
    doc.detected_category = verification.detected_category
    doc.category_confidence = verification.confidence
    doc.category_mismatch = verification.is_mismatch
    doc.status = "processed"

    run.status, run.finished_at = "completed", datetime.now(UTC)
    run.summary = {
        "tables": len(tables),
        "rows": n_rows,
        "findings": n_findings,
        "needs_review": need_review,
        "types": [t.detected_type for t in tables],
        "category_verification": {
            "user_category": verification.user_category,
            "detected_category": verification.detected_category,
            "confidence": verification.confidence,
            "is_mismatch": verification.is_mismatch,
            "explanation": verification.explanation,
        },
    }
    run.llm_used = any(t.llm_used for t in tables)
    run.llm_model = next((t.llm_model for t in tables if t.llm_model), None)

    record_audit(
        session,
        action="extraction.completed",
        actor_user_id=run.created_by,
        firm_id=firm_id,
        actor_email=None if run.created_by else "system:doc_intel",
        target_type="document",
        target_id=document_id,
        client_id=client_id,
        metadata={"run_id": str(run_id), "version": run.version, **run.summary},
    )


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
        if run is not None and run.status == "running":
            run.status, run.finished_at = "failed", datetime.now(UTC)
            run.error_code, run.error_message = code, message
        if doc is not None and doc.status == "processing":
            doc.status = "failed"
        record_audit(
            session,
            action="extraction.failed",
            actor_email="system:doc_intel",
            target_type="document",
            target_id=document_id,
            firm_id=firm_id,
            client_id=client_id,
            outcome="failure",
            metadata={"run_id": str(run_id), "error_code": code, "error_message": message},
        )


# -----------------------------------------------------------------------------
# 3. Cross-Module Document Sharing & Referencing
# -----------------------------------------------------------------------------


async def share_document_with_module(
    session: AsyncSession,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    target_module: str,
    target_category: str | None = None,
    notes: str | None = None,
) -> DocumentModuleReference:
    """Allows an already uploaded and extracted document (e.g. Sales Invoice)
    to be referenced by another module (e.g. Taxation) without duplicating the file or OCR.
    """
    require_permission(principal, "document:upload")
    doc = await session.get(Document, document_id)
    if (
        doc is None
        or doc.client_id != client_id
        or doc.period_id != period_id
        or doc.firm_id != principal.firm_id
    ):
        raise NotFoundError("Document not found")

    target_mod = target_module.lower().strip()
    cat = target_category or doc.category

    # Check if reference already exists
    existing = await session.scalar(
        select(DocumentModuleReference).where(
            DocumentModuleReference.document_id == document_id,
            DocumentModuleReference.module == target_mod,
        )
    )
    if existing:
        existing.module_category = cat
        existing.status = "active"
        if notes:
            existing.notes = notes
        existing.updated_at = datetime.now(UTC)
        await session.commit()
        return existing

    ref = DocumentModuleReference(
        id=uuid.uuid4(),
        firm_id=principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        document_id=document_id,
        module=target_mod,
        module_category=cat,
        is_primary=False,
        status="active",
        notes=notes,
        shared_by=principal.user_id,
    )
    session.add(ref)
    record_audit(
        session,
        action="document.shared_with_module",
        actor=principal,
        target_type="document",
        target_id=document_id,
        client_id=client_id,
        metadata={"target_module": target_mod, "category": cat, "period_id": str(period_id)},
    )
    await session.commit()
    await session.refresh(ref)
    return ref


async def list_module_documents(
    session: AsyncSession,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    *,
    module: str | None = None,
    category: str | None = None,
    include_shared: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Document], int]:
    """Lists documents scoped to client/period, optionally filtered by module.

    When include_shared is True, returns documents that belong primarily to the module
    OR have been shared with the module via DocumentModuleReference.
    """
    await _scoped_period(session, principal, client_id, period_id)

    stmt = select(Document).where(
        Document.firm_id == principal.firm_id,
        Document.client_id == client_id,
        Document.period_id == period_id,
        Document.deleted_at.is_(None),
    )

    if module:
        mod = module.lower().strip()
        if include_shared:
            # Match if doc.module == mod OR linked in document_module_references
            ref_subq = (
                select(DocumentModuleReference.document_id)
                .where(
                    DocumentModuleReference.firm_id == principal.firm_id,
                    DocumentModuleReference.client_id == client_id,
                    DocumentModuleReference.period_id == period_id,
                    DocumentModuleReference.module == mod,
                    DocumentModuleReference.status == "active",
                )
                .scalar_subquery()
            )
            stmt = stmt.where((Document.module == mod) | (Document.id.in_(ref_subq)))
        else:
            stmt = stmt.where(Document.module == mod)

    if category:
        stmt = stmt.where(Document.category == category)

    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    docs = (
        await session.scalars(
            stmt.order_by(Document.created_at.desc()).limit(limit).offset(offset)
        )
    ).all()
    return list(docs), total
