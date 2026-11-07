# ruff: noqa: E501
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import PrincipalDep, SessionDep, SettingsDep
from app.schemas.common import Page
from app.schemas.extraction import (
    ColumnOut,
    ColumnRoleIn,
    ExtractionOut,
    FindingOut,
    FindingUpdateIn,
    RowOut,
    RunOut,
    TableOut,
    TableTypeIn,
)
from app.services import extraction as svc

router = APIRouter(
    prefix="/clients/{client_id}/periods/{period_id}/documents/{document_id}/extraction",
    tags=["extraction"],
)


def _table_out(t: object, cols: list[object], open_findings: int) -> TableOut:
    from app.models import ExtractedColumn, ExtractedTable

    assert isinstance(t, ExtractedTable)  # noqa: S101
    columns = [c for c in cols if isinstance(c, ExtractedColumn)]
    return TableOut(
        id=t.id, ordinal=t.ordinal, name=t.name, kind=t.kind, n_rows=t.n_rows, n_cols=t.n_cols,
        header_row=t.header_row, has_header=t.has_header, detected_type=t.detected_type,
        type_confidence=t.type_confidence, type_source=t.type_source,
        confirmed_type=t.confirmed_type, effective_type=t.confirmed_type or t.detected_type,
        currency=t.detected_currency, period_start=t.period_start, period_end=t.period_end,
        status=t.status, open_findings=open_findings,
        columns=[
            ColumnOut(
                col_index=c.col_index, letter=c.letter, header=c.header_raw,
                header_synthetic=c.header_synthetic, suggested_role=c.suggested_role,
                confidence=c.confidence, role_source=c.role_source,
                confirmed_role=c.confirmed_role, effective_role=svc.effective_role(c),
            )
            for c in columns
        ],
    )  # fmt: skip


def _finding_out(f: object) -> FindingOut:
    from app.models import DataQualityFinding

    assert isinstance(f, DataQualityFinding)  # noqa: S101
    return FindingOut(
        id=f.id, table_id=f.table_id, row_index=f.row_index, col_index=f.col_index, code=f.code,
        severity=f.severity, message=f.message, details=f.details, origin=f.origin,
        status=f.status, resolution_note=f.resolution_note, created_at=f.created_at,
    )  # fmt: skip


@router.get("", response_model=ExtractionOut)
async def get_extraction(
    client_id: uuid.UUID, period_id: uuid.UUID, document_id: uuid.UUID,
    principal: PrincipalDep, session: SessionDep,
) -> ExtractionOut:  # fmt: skip
    r = await svc.get_extraction(session, principal, client_id, period_id, document_id)
    run = r["run"]
    return ExtractionOut(
        document_id=document_id,
        document_status=r["document"].status,
        run=RunOut.model_validate(run, from_attributes=True) if run else None,
        tables=[_table_out(x["table"], x["columns"], x["open_findings"]) for x in r["tables"]],
        open_findings=r["open_findings"],
    )


@router.get("/tables/{table_id}/rows", response_model=Page[RowOut])
async def list_rows(
    client_id: uuid.UUID, period_id: uuid.UUID, document_id: uuid.UUID, table_id: uuid.UUID,
    principal: PrincipalDep, session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    flagged_only: bool = False,
) -> Page[RowOut]:  # fmt: skip
    rows, total = await svc.list_rows(
        session, principal, client_id, period_id, document_id, table_id,
        limit=limit, offset=offset, flagged_only=flagged_only,
    )  # fmt: skip
    return Page[RowOut](
        items=[RowOut.model_validate(r, from_attributes=True) for r in rows],
        total=total, limit=limit, offset=offset,
    )  # fmt: skip


@router.patch("/tables/{table_id}/columns/{col_index}", response_model=TableOut)
async def set_column_role(
    client_id: uuid.UUID, period_id: uuid.UUID, document_id: uuid.UUID, table_id: uuid.UUID,
    col_index: int, body: ColumnRoleIn,
    principal: PrincipalDep, session: SessionDep, settings: SettingsDep,
) -> TableOut:  # fmt: skip
    await svc.set_column_role(
        session, settings, principal, client_id, period_id, document_id, table_id, col_index,
        body.role,
    )  # fmt: skip
    return await _reload_table(session, principal, client_id, period_id, document_id, table_id)


@router.patch("/tables/{table_id}", response_model=TableOut)
async def set_table_type(
    client_id: uuid.UUID, period_id: uuid.UUID, document_id: uuid.UUID, table_id: uuid.UUID,
    body: TableTypeIn, principal: PrincipalDep, session: SessionDep, settings: SettingsDep,
) -> TableOut:  # fmt: skip
    await svc.set_table_type(
        session, settings, principal, client_id, period_id, document_id, table_id,
        body.confirmed_type,
    )  # fmt: skip
    return await _reload_table(session, principal, client_id, period_id, document_id, table_id)


async def _reload_table(
    session: SessionDep, principal: PrincipalDep, client_id: uuid.UUID, period_id: uuid.UUID,
    document_id: uuid.UUID, table_id: uuid.UUID,
) -> TableOut:  # fmt: skip
    r = await svc.get_extraction(session, principal, client_id, period_id, document_id)
    for x in r["tables"]:
        if x["table"].id == table_id:
            return _table_out(x["table"], x["columns"], x["open_findings"])
    raise RuntimeError("table vanished")  # pragma: no cover


@router.get("/findings", response_model=list[FindingOut])
async def list_findings(
    client_id: uuid.UUID, period_id: uuid.UUID, document_id: uuid.UUID,
    principal: PrincipalDep, session: SessionDep,
    finding_status: Annotated[Literal["open", "resolved", "dismissed"] | None, Query(alias="status")] = None,
    severity: Annotated[Literal["info", "warning", "error"] | None, Query()] = None,
) -> list[FindingOut]:  # fmt: skip
    rows = await svc.list_findings(
        session,
        principal,
        client_id,
        period_id,
        document_id,
        status=finding_status,
        severity=severity,
    )
    return [_finding_out(f) for f in rows]


@router.patch("/findings/{finding_id}", response_model=FindingOut)
async def update_finding(
    client_id: uuid.UUID, period_id: uuid.UUID, document_id: uuid.UUID, finding_id: uuid.UUID,
    body: FindingUpdateIn, principal: PrincipalDep, session: SessionDep,
) -> FindingOut:  # fmt: skip
    f = await svc.update_finding(
        session, principal, client_id, period_id, document_id, finding_id,
        status=body.status, note=body.note,
    )  # fmt: skip
    return _finding_out(f)


@router.post("/rerun", status_code=status.HTTP_202_ACCEPTED)
async def rerun(
    client_id: uuid.UUID, period_id: uuid.UUID, document_id: uuid.UUID,
    principal: PrincipalDep, session: SessionDep,
) -> dict[str, str]:  # fmt: skip
    doc = await svc.request_rerun(session, principal, client_id, period_id, document_id)
    return {"document_id": str(doc.id), "status": doc.status}
