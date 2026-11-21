"""Reporting service (Phase 8).

Handles generation, retrieval, and formal CA sign-off for Adjusted Trial Balance,
financial statements, and validation outputs.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.reporting_agent.agent import ReportingAgent
from app.core.errors import NotFoundError, PermissionDeniedError
from app.models.reporting import FinancialReport
from app.services.authz import Principal, get_accessible_client, require_permission

logger = logging.getLogger("app.services.reporting")


async def generate_financial_reports(
    session: AsyncSession,
    principal: Principal,
    *,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    currency: str = "PKR",
) -> dict[str, Any]:
    """Triggers Agent 4 to produce Adjusted TB and financial statement packs."""
    require_permission(principal, "report:generate")
    await get_accessible_client(session, principal, client_id)

    agent = ReportingAgent()
    return await agent.generate_reporting_pack(
        session,
        client_id=client_id,
        period_id=period_id,
        firm_id=principal.firm_id,
        currency=currency,
    )


async def list_reports(
    session: AsyncSession,
    principal: Principal,
    *,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    report_type: str | None = None,
) -> list[FinancialReport]:
    require_permission(principal, "report:read")
    await get_accessible_client(session, principal, client_id)

    q = select(FinancialReport).where(
        FinancialReport.firm_id == principal.firm_id,
        FinancialReport.client_id == client_id,
        FinancialReport.period_id == period_id,
    )
    if report_type:
        q = q.where(FinancialReport.report_type == report_type)

    q = q.order_by(FinancialReport.created_at.desc())
    result = await session.scalars(q)
    return list(result.all())


async def get_report(
    session: AsyncSession,
    principal: Principal,
    report_id: uuid.UUID,
) -> FinancialReport:
    require_permission(principal, "report:read")
    report = await session.scalar(
        select(FinancialReport).where(
            FinancialReport.id == report_id,
            FinancialReport.firm_id == principal.firm_id,
        )
    )
    if report is None:
        raise NotFoundError("Financial report not found")
    await get_accessible_client(session, principal, report.client_id)
    return report


async def sign_off_report(
    session: AsyncSession,
    principal: Principal,
    report_id: uuid.UUID,
    *,
    notes: str | None = None,
) -> FinancialReport:
    """Formal CA reviewer sign-off on a financial report."""
    require_permission(principal, "report:sign_off")
    report = await get_report(session, principal, report_id)

    report.status = "signed_off"
    report.signed_off_by = principal.user_id
    report.signed_off_at = datetime.now(UTC)
    report.sign_off_notes = notes
    report.updated_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(report)

    # Publish approved output to the Central Shared Data Layer
    try:
        from app.services.shared_data import publish_approved_accounting_output
        await publish_approved_accounting_output(
            session,
            principal,
            client_id=report.client_id,
            period_id=report.period_id,
            notes=notes or f"Published on CA sign-off of report {report.report_type}",
        )
    except Exception as exc:
        logger.warning(
            "Auto-publish to shared data layer skipped/failed on sign-off: %s",
            exc,
            extra={"report_id": str(report.id)},
        )

    logger.info(
        "financial report signed off",
        extra={"report_id": str(report.id), "ca_id": str(principal.user_id)},
    )
    return report
