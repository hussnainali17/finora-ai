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

from app.api.deps import Principal, SessionDep, requires
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
    principal: Principal = Depends(requires("report:generate")),
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
    principal: Principal = Depends(requires("report:read")),
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
    principal: Principal = Depends(requires("report:read")),
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
    principal: Principal = Depends(requires("report:sign_off")),
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
    principal: Principal = Depends(requires("report:read")),
) -> Response:
    from app.agents.reporting_agent.agent import ReportingAgent

    report = await rep_svc.get_report(session, principal, report_id)
    agent = ReportingAgent()
    data = report.data or {}

    # Support both full_pack structure and standalone adjusted_trial_balance structure
    adjusted_tb_rows = data.get("adjusted_tb", {}).get("rows") if isinstance(data.get("adjusted_tb"), dict) else None
    if adjusted_tb_rows is None:
        adjusted_tb_rows = data.get("rows", [])

    pl_data = data.get("profit_and_loss") or {}
    bs_data = data.get("balance_sheet") or {}
    cf_data = data.get("cash_flow") or {}

    # If the user selected an individual report that lacks P&L or BS, try to load the sibling full_pack
    if report.report_type != "full_pack" and (not pl_data or not bs_data):
        sibling_reports = await rep_svc.list_reports(
            session, principal, client_id=client_id, period_id=period_id, report_type="full_pack"
        )
        if sibling_reports:
            full_data = sibling_reports[0].data or {}
            if not pl_data:
                pl_data = full_data.get("profit_and_loss") or {}
            if not bs_data:
                bs_data = full_data.get("balance_sheet") or {}
            if not cf_data:
                cf_data = full_data.get("cash_flow") or {}

    excel_bytes = agent._build_excel_pack(
        client_id=client_id,
        period_id=period_id,
        currency=data.get("currency", "PKR"),
        adjusted_tb_rows=adjusted_tb_rows,
        pl_data=pl_data,
        bs_data=bs_data,
        cf_data=cf_data,
        validation=report.validation_results or {},
    )

    filename = f"financial_report_{report.report_type}_{period_id}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
            "X-Content-Type-Options": "nosniff",
        },
    )
