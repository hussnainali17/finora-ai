"""Financial Reporting & Validation API (Phase 8).

Nested under /clients/{client_id}/periods/{period_id}/reports.
Enforces:
- `report:read` for viewing reports
- `report:generate` for generating reporting outputs
- `report:sign_off` for CA sign-off
"""

from __future__ import annotations

import io
import uuid

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import PrincipalDep, SessionDep, requires
from app.schemas.reporting import (
    FinancialReportListOut,
    FinancialReportOut,
    GenerateReportIn,
    ReportSignOffIn,
)
from app.services import reporting as rep_svc

router = APIRouter(
    prefix="/clients/{client_id}/periods/{period_id}/reports",
    tags=["reporting"],
)


@router.post(
    "/generate",
    response_model=dict,
    status_code=201,
    summary="Generate Adjusted Trial Balance and Financial Statements (Agent 4)",
)
async def generate_reports(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    body: GenerateReportIn,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("report:generate")),
) -> dict:
    return await rep_svc.generate_financial_reports(
        session,
        principal,
        client_id=client_id,
        period_id=period_id,
        currency=body.currency,
    )


@router.get(
    "/",
    response_model=FinancialReportListOut,
    summary="List generated financial reports for a period",
)
async def list_reports(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("report:read")),
    report_type: str | None = Query(default=None),
) -> FinancialReportListOut:
    reports = await rep_svc.list_reports(
        session,
        principal,
        client_id=client_id,
        period_id=period_id,
        report_type=report_type,
    )
    return FinancialReportListOut(
        items=[FinancialReportOut.model_validate(r) for r in reports],
        total=len(reports),
    )


@router.get(
    "/{report_id}",
    response_model=FinancialReportOut,
    summary="Get a specific financial report and validation status",
)
async def get_report(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    report_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("report:read")),
) -> FinancialReportOut:
    report = await rep_svc.get_report(session, principal, report_id)
    return FinancialReportOut.model_validate(report)


@router.post(
    "/{report_id}/sign-off",
    response_model=FinancialReportOut,
    summary="Formal CA reviewer sign-off on a financial report",
)
async def sign_off_report(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    report_id: uuid.UUID,
    body: ReportSignOffIn,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("report:sign_off")),
) -> FinancialReportOut:
    report = await rep_svc.sign_off_report(
        session,
        principal,
        report_id,
        notes=body.notes,
    )
    return FinancialReportOut.model_validate(report)


@router.get(
    "/{report_id}/export/excel",
    summary="Download generated financial report as an Excel spreadsheet",
)
async def export_excel(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    report_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("report:read")),
) -> Response:
    from app.agents.reporting_agent.agent import ReportingAgent

    report = await rep_svc.get_report(session, principal, report_id)
    agent = ReportingAgent()
    data = report.data

    excel_bytes = agent._build_excel_pack(
        client_id=client_id,
        period_id=period_id,
        currency=data.get("currency", "PKR"),
        adjusted_tb_rows=data.get("adjusted_tb", {}).get("rows", []),
        pl_data=data.get("profit_and_loss", {}),
        bs_data=data.get("balance_sheet", {}),
        validation=report.validation_results or {},
    )

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="financial_report_{report.report_type}_{period_id}.xlsx"',
            "X-Content-Type-Options": "nosniff",
        },
    )
