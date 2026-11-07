# ruff: noqa: E501
"""Review operations on extracted data. Every call is authorised (permission, then client scope via
the document lookup) and every change is audited in the same transaction.

Corrections change only the *confirmed* column roles / table type and the derived normalized
values. The raw extracted cells and the original file are never modified."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.intake_agent.normalize import normalize_rows
from app.agents.intake_agent.types import DOC_TYPES, ROLES, FindingDraft, RawCell
from app.core.config import Settings
from app.core.errors import ConflictError, DomainValidationError, NotFoundError
from app.models import (
    DataQualityFinding,
    Document,
    ExtractedColumn,
    ExtractedRow,
    ExtractedTable,
    ExtractionRun,
)
from app.services.audit import record_audit
from app.services.authz import Principal, require_permission
from app.services.documents import _get_document

ROW_UPDATE_CHUNK = 2000


async def _current_run(session: AsyncSession, doc: Document) -> ExtractionRun | None:
    return await session.scalar(
        select(ExtractionRun).where(
            ExtractionRun.document_id == doc.id, ExtractionRun.is_current.is_(True)
        )
    )


async def _scoped_table(
    session: AsyncSession, doc: Document, table_id: uuid.UUID
) -> ExtractedTable:
    """A table is reachable only through its own, in-scope, current document run."""
    table = await session.scalar(
        select(ExtractedTable)
        .join(ExtractionRun, ExtractionRun.id == ExtractedTable.run_id)
        .where(
            ExtractedTable.id == table_id,
            ExtractedTable.document_id == doc.id,
            ExtractedTable.client_id == doc.client_id,
            ExtractedTable.firm_id == doc.firm_id,
            ExtractionRun.is_current.is_(True),
        )
    )
    if table is None:
        raise NotFoundError("Extracted table not found")
    await session.commit()
    return table


# ------------------------------------------------------------------------------- reads


async def get_extraction(
    session: AsyncSession,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
) -> dict[str, Any]:
    require_permission(principal, "extraction:read")
    doc = await _get_document(session, principal, client_id, period_id, document_id)
    run = await _current_run(session, doc)
    tables: list[dict[str, Any]] = []
    totals: dict[str, int] = {"info": 0, "warning": 0, "error": 0}
    if run is not None:
        for t in (
            await session.scalars(
                select(ExtractedTable)
                .where(ExtractedTable.run_id == run.id)
                .order_by(ExtractedTable.ordinal)
            )
        ).all():
            cols = (
                await session.scalars(
                    select(ExtractedColumn)
                    .where(ExtractedColumn.table_id == t.id)
                    .order_by(ExtractedColumn.col_index)
                )
            ).all()
            open_count = await session.scalar(
                select(func.count()).select_from(DataQualityFinding).where(
                    DataQualityFinding.table_id == t.id, DataQualityFinding.status == "open"
                )
            )  # fmt: skip
            tables.append({"table": t, "columns": list(cols), "open_findings": open_count or 0})
        for sev, n in await session.execute(
            select(DataQualityFinding.severity, func.count())
            .where(DataQualityFinding.run_id == run.id, DataQualityFinding.status == "open")
            .group_by(DataQualityFinding.severity)
        ):
            totals[sev] = n
    return {"document": doc, "run": run, "tables": tables, "open_findings": totals}


async def list_rows(
    session: AsyncSession,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    table_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
    flagged_only: bool,
) -> tuple[list[ExtractedRow], int]:
    require_permission(principal, "extraction:read")
    doc = await _get_document(session, principal, client_id, period_id, document_id)
    table = await _scoped_table(session, doc, table_id)
    cond = [ExtractedRow.table_id == table.id]
    if flagged_only:
        cond.append(func.jsonb_array_length(ExtractedRow.flags) > 0)
    total = await session.scalar(select(func.count()).select_from(ExtractedRow).where(*cond))
    rows = (
        await session.scalars(
            select(ExtractedRow)
            .where(*cond)
            .order_by(ExtractedRow.row_index, ExtractedRow.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return list(rows), total or 0


async def list_findings(
    session: AsyncSession,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    status: str | None,
    severity: str | None,
) -> list[DataQualityFinding]:
    require_permission(principal, "extraction:read")
    doc = await _get_document(session, principal, client_id, period_id, document_id)
    run = await _current_run(session, doc)
    if run is None:
        return []
    cond = [DataQualityFinding.run_id == run.id, DataQualityFinding.firm_id == principal.firm_id]
    if status:
        cond.append(DataQualityFinding.status == status)
    if severity:
        cond.append(DataQualityFinding.severity == severity)
    sev_order = func.array_position(["error", "warning", "info"], DataQualityFinding.severity)
    return list(
        (
            await session.scalars(
                select(DataQualityFinding)
                .where(*cond)
                .order_by(sev_order, DataQualityFinding.created_at, DataQualityFinding.id)
            )
        ).all()
    )


# ------------------------------------------------------------------------------- writes


def effective_role(col: ExtractedColumn) -> str:
    return col.confirmed_role or col.suggested_role


def _needs_review(table: ExtractedTable, cols: list[ExtractedColumn], min_conf: float) -> bool:
    etype = table.confirmed_type or table.detected_type
    if etype == "unknown":
        return True
    if table.type_source == "llm" and not table.confirmed_type:
        return True
    if table.detected_type == "text_document" and not table.confirmed_type:
        return True
    return any(
        not c.confirmed_role
        and c.suggested_role != "ignore"
        and (c.confidence < min_conf or c.role_source == "llm")
        for c in cols
    )


async def _renormalize(
    session: AsyncSession, table: ExtractedTable, cols: list[ExtractedColumn], settings: Settings
) -> int:
    """Recomputes normalized values + row flags from the preserved raw cells and current roles."""
    roles = [effective_role(c) for c in cols]
    headers = [c.header_raw or f"column {c.col_index + 1}" for c in cols]
    ids: list[int] = []
    data: list[list[RawCell | None]] = []
    for row in (
        await session.scalars(
            select(ExtractedRow)
            .where(ExtractedRow.table_id == table.id)
            .order_by(ExtractedRow.row_index, ExtractedRow.id)
        )
    ).all():
        ids.append(row.id)
        data.append(
            [
                RawCell.from_json(row.raw[str(i)]) if str(i) in row.raw else None
                for i in range(len(cols))
            ]
        )
    result = normalize_rows(
        data, list(range(len(data))), roles, headers, settings.intake_default_date_order
    )
    for start in range(0, len(ids), ROW_UPDATE_CHUNK):
        await session.execute(
            update(ExtractedRow),
            [
                {"id": ids[i], "normalized": result.rows[i], "flags": result.flags[i]}
                for i in range(start, min(start + ROW_UPDATE_CHUNK, len(ids)))
            ],
        )
    await _replace_normalize_findings(session, table, result.findings)
    return len(ids)


async def _replace_normalize_findings(
    session: AsyncSession, table: ExtractedTable, drafts: list[FindingDraft]
) -> None:
    """Swap the derived findings, keeping reviewers' earlier resolve/dismiss decisions."""
    old = (
        await session.scalars(
            select(DataQualityFinding).where(
                DataQualityFinding.table_id == table.id, DataQualityFinding.origin == "normalize"
            )
        )
    ).all()
    keep = {(f.code, f.col_index): f for f in old if f.status != "open"}
    await session.execute(
        delete(DataQualityFinding).where(
            DataQualityFinding.table_id == table.id, DataQualityFinding.origin == "normalize"
        )
    )
    for d in drafts:
        prev = keep.get((d.code, d.col_index))
        session.add(
            DataQualityFinding(
                run_id=table.run_id, table_id=table.id, firm_id=table.firm_id,
                client_id=table.client_id, period_id=table.period_id, document_id=table.document_id,
                row_index=d.row_index, col_index=d.col_index, code=d.code, severity=d.severity,
                message=d.message, details=d.details, source_ref=d.source_ref, origin="normalize",
                status=prev.status if prev else "open",
                resolved_by=prev.resolved_by if prev else None,
                resolved_at=prev.resolved_at if prev else None,
                resolution_note=prev.resolution_note if prev else None,
            )
        )  # fmt: skip


async def _resolve(
    session: AsyncSession, table: ExtractedTable, code: str, col_index: int | None,
    user_id: uuid.UUID, note: str,
) -> None:  # fmt: skip
    cond = [
        DataQualityFinding.table_id == table.id,
        DataQualityFinding.code == code,
        DataQualityFinding.status == "open",
    ]
    if col_index is not None:
        cond.append(DataQualityFinding.col_index == col_index)
    await session.execute(
        update(DataQualityFinding).where(*cond).values(
            status="resolved", resolved_by=user_id, resolved_at=datetime.now(UTC), resolution_note=note
        )
    )  # fmt: skip


async def set_column_role(
    session: AsyncSession,
    settings: Settings,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    table_id: uuid.UUID,
    col_index: int,
    role: str,
) -> ExtractedTable:
    require_permission(principal, "extraction:review")
    if role not in ROLES:
        raise DomainValidationError("Unknown column role")
    doc = await _get_document(session, principal, client_id, period_id, document_id)
    table = await _scoped_table(session, doc, table_id)
    cols = list(
        (
            await session.scalars(
                select(ExtractedColumn)
                .where(ExtractedColumn.table_id == table.id)
                .order_by(ExtractedColumn.col_index)
            )
        ).all()
    )
    col = next((c for c in cols if c.col_index == col_index), None)
    if col is None:
        raise NotFoundError("Column not found")
    before = effective_role(col)
    col.confirmed_role, col.confirmed_by, col.confirmed_at = (
        role,
        principal.user_id,
        datetime.now(UTC),
    )
    await session.flush()
    for code in ("low_confidence_column", "llm_suggested_role"):
        await _resolve(
            session, table, code, col_index, principal.user_id, "Role confirmed by reviewer"
        )
    n = await _renormalize(session, table, cols, settings)
    table.status = (
        "needs_review" if _needs_review(table, cols, settings.intake_llm_min_confidence) else "ok"
    )
    record_audit(
        session, action="extraction.column_role_set", actor=principal, target_type="document",
        target_id=doc.id, client_id=doc.client_id,
        metadata={"table_id": str(table.id), "col_index": col_index, "from": before, "to": role, "rows_renormalized": n},
    )  # fmt: skip
    await session.commit()
    return table


async def set_table_type(
    session: AsyncSession,
    settings: Settings,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    table_id: uuid.UUID,
    confirmed_type: str,
) -> ExtractedTable:
    require_permission(principal, "extraction:review")
    if confirmed_type not in DOC_TYPES:
        raise DomainValidationError("Unknown document type")
    doc = await _get_document(session, principal, client_id, period_id, document_id)
    table = await _scoped_table(session, doc, table_id)
    before = table.confirmed_type or table.detected_type
    table.confirmed_type, table.confirmed_by, table.confirmed_at = (
        confirmed_type, principal.user_id, datetime.now(UTC),
    )  # fmt: skip
    cols = list(
        (
            await session.scalars(
                select(ExtractedColumn).where(ExtractedColumn.table_id == table.id)
            )
        ).all()
    )
    if confirmed_type != "unknown":
        for code in ("unknown_document_type", "type_mismatch", "llm_suggested_type"):
            await _resolve(session, table, code, None, principal.user_id, "Type set by reviewer")
    table.status = (
        "needs_review" if _needs_review(table, cols, settings.intake_llm_min_confidence) else "ok"
    )
    record_audit(
        session, action="extraction.table_type_set", actor=principal, target_type="document",
        target_id=doc.id, client_id=doc.client_id,
        metadata={"table_id": str(table.id), "from": before, "to": confirmed_type},
    )  # fmt: skip
    await session.commit()
    return table


async def update_finding(
    session: AsyncSession,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    finding_id: uuid.UUID,
    *,
    status: str,
    note: str | None,
) -> DataQualityFinding:
    require_permission(principal, "extraction:review")
    doc = await _get_document(session, principal, client_id, period_id, document_id)
    finding = await session.scalar(
        select(DataQualityFinding).where(
            DataQualityFinding.id == finding_id,
            DataQualityFinding.document_id == doc.id,
            DataQualityFinding.firm_id == principal.firm_id,
            DataQualityFinding.client_id == doc.client_id,
        )
    )
    if finding is None:
        raise NotFoundError("Finding not found")
    if finding.severity == "error" and status == "dismissed":
        raise DomainValidationError("Errors cannot be dismissed; resolve them or re-run extraction")
    before = finding.status
    finding.status = status
    if status == "open":
        finding.resolved_by, finding.resolved_at, finding.resolution_note = None, None, None
    else:
        finding.resolved_by, finding.resolved_at = principal.user_id, datetime.now(UTC)
        finding.resolution_note = note
    record_audit(
        session, action="extraction.finding_updated", actor=principal, target_type="document",
        target_id=doc.id, client_id=doc.client_id,
        metadata={"finding_id": str(finding.id), "code": finding.code, "from": before, "to": status},
    )  # fmt: skip
    await session.commit()
    return finding


async def request_rerun(
    session: AsyncSession,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Document:
    """Queues the document for another extraction; the runner picks it up. The previous run is
    kept (versioned) and reviewer-confirmed roles carry over by sheet + header."""
    require_permission(principal, "extraction:run")
    doc = await _get_document(session, principal, client_id, period_id, document_id)
    locked = await session.scalar(select(Document).where(Document.id == doc.id).with_for_update())
    if locked is None:
        raise NotFoundError("Document not found")
    if locked.status in ("processing", "queued", "uploaded"):
        raise ConflictError("Extraction is already queued or running for this document")
    locked.status = "queued"
    record_audit(
        session, action="extraction.rerun_requested", actor=principal, target_type="document",
        target_id=doc.id, client_id=doc.client_id, metadata={"previous_status": doc.status},
    )  # fmt: skip
    await session.commit()
    return locked
