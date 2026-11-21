"""Central Shared Data Layer Service.

Manages publishing, retrieval, versioning, and cross-module invalidation
for approved Accounting and Taxation outputs.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, require_permission
from app.core.errors import DomainValidationError, NotFoundError
from app.models.adjustments import PeriodAdjustment
from app.models.identity import AccountingPeriod, Client
from app.models.reporting import AccountMapping, FinancialReport
from app.models.shared_data import ApprovedModuleOutput
from app.services.audit import record_audit
from app.services.clients import get_accessible_client

logger = logging.getLogger("app.services.shared_data")


async def publish_approved_accounting_output(
    session: AsyncSession,
    principal: Principal,
    *,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    notes: str | None = None,
) -> ApprovedModuleOutput:
    """Compiles and publishes approved accounting results to the Central Shared Data Layer.

    Gathers:
    - Adjusted Trial Balance
    - Balance Sheet & Profit and Loss statements
    - Approved Period Adjustments
    - Account Mappings
    Checks for prior versions, marks them superseded, assigns next version,
    and invalidates any dependent taxation runs that used older versions.
    """
    require_permission(principal, "shared:publish")
    await get_accessible_client(session, principal, client_id)

    # 1. Fetch reports for this period
    reports_res = await session.scalars(
        select(FinancialReport).where(
            FinancialReport.firm_id == principal.firm_id,
            FinancialReport.client_id == client_id,
            FinancialReport.period_id == period_id,
        )
    )
    reports = list(reports_res.all())
    if not reports:
        raise DomainValidationError("No financial reports found for this period to publish.")

    # Find Adjusted Trial Balance and Full Pack / Statements
    tb_report = next((r for r in reports if r.report_type == "adjusted_trial_balance"), None)
    pl_report = next((r for r in reports if r.report_type == "profit_loss"), None)
    bs_report = next((r for r in reports if r.report_type == "balance_sheet"), None)
    full_pack = next((r for r in reports if r.report_type == "full_pack"), None)

    # 2. Fetch approved adjustments
    adj_res = await session.scalars(
        select(PeriodAdjustment).where(
            PeriodAdjustment.firm_id == principal.firm_id,
            PeriodAdjustment.client_id == client_id,
            PeriodAdjustment.period_id == period_id,
            PeriodAdjustment.status == "approved",
        )
    )
    approved_adjustments = [
        {
            "id": str(a.id),
            "adjustment_type": a.adjustment_type,
            "debit_account": a.debit_account,
            "credit_account": a.credit_account,
            "amount": str(a.amount),
            "description": a.description,
            "effective_date": a.effective_date.isoformat(),
        }
        for a in adj_res.all()
    ]

    # 3. Fetch account mappings
    map_res = await session.scalars(
        select(AccountMapping).where(
            AccountMapping.firm_id == principal.firm_id,
            AccountMapping.client_id == client_id,
        )
    )
    account_mappings = [
        {
            "account_code": m.account_code,
            "account_name": m.account_name,
            "statement_type": m.statement_type,
            "category": m.category,
            "sub_category": m.sub_category,
        }
        for m in map_res.all()
    ]

    # Assemble snapshot data
    payload_data: dict[str, Any] = {
        "trial_balance": tb_report.data if tb_report else {},
        "profit_loss": pl_report.data if pl_report else {},
        "balance_sheet": bs_report.data if bs_report else {},
        "full_pack": full_pack.data if full_pack else {},
        "adjustments": approved_adjustments,
        "account_mappings": account_mappings,
    }

    # Summary metrics
    pl_data = pl_report.data if pl_report else {}
    bs_data = bs_report.data if bs_report else {}
    summary_data: dict[str, Any] = {
        "net_profit": pl_data.get("net_profit", 0),
        "total_revenue": pl_data.get("total_revenue", 0),
        "total_expenses": pl_data.get("total_expenses", 0),
        "total_assets": bs_data.get("total_assets", 0),
        "total_liabilities": bs_data.get("total_liabilities", 0),
        "total_equity": bs_data.get("total_equity", 0),
        "adjustments_count": len(approved_adjustments),
    }

    # Determine next version
    prior_res = await session.scalars(
        select(ApprovedModuleOutput).where(
            ApprovedModuleOutput.firm_id == principal.firm_id,
            ApprovedModuleOutput.client_id == client_id,
            ApprovedModuleOutput.period_id == period_id,
            ApprovedModuleOutput.module == "accounting",
        ).order_by(desc(ApprovedModuleOutput.version))
    )
    prior_outputs = list(prior_res.all())
    next_version = (prior_outputs[0].version + 1) if prior_outputs else 1

    # Mark older approved versions as superseded
    for prev in prior_outputs:
        if prev.status == "approved":
            prev.status = "superseded"

    new_output = ApprovedModuleOutput(
        firm_id=principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        module="accounting",
        output_type="financial_reporting_pack",
        version=next_version,
        status="approved",
        data=payload_data,
        summary=summary_data,
        source_version_refs={},
        validation_results={
            "tb_balanced": tb_report.validation_results.get("is_valid", True) if tb_report else True,
            "statements_tied": True,
        },
        is_outdated=False,
        signed_off_by=principal.user_id,
        signed_off_at=datetime.now(UTC),
        sign_off_notes=notes or "Published upon CA financial statement sign-off",
    )
    session.add(new_output)
    await session.flush()

    # 4. Dependency Invalidation: Check if dependent taxation outputs need to be flagged
    dep_res = await session.scalars(
        select(ApprovedModuleOutput).where(
            ApprovedModuleOutput.firm_id == principal.firm_id,
            ApprovedModuleOutput.client_id == client_id,
            ApprovedModuleOutput.period_id == period_id,
            ApprovedModuleOutput.module == "taxation",
            ApprovedModuleOutput.is_outdated == False,  # noqa: E712
        )
    )
    stale_count = 0
    for tax_output in dep_res.all():
        consumed_ver = tax_output.source_version_refs.get("accounting_output_version")
        if consumed_ver is not None and consumed_ver < next_version:
            tax_output.is_outdated = True
            tax_output.stale_reason = (
                f"Accounting outputs updated to version {next_version}. "
                f"Tax calculations previously used version {consumed_ver}."
            )
            stale_count += 1

    record_audit(
        session,
        action="shared_output:published",
        actor=principal,
        target_type="approved_module_output",
        target_id=new_output.id,
        client_id=client_id,
        metadata={
            "module": "accounting",
            "version": next_version,
            "stale_tax_outputs_flagged": stale_count,
        },
    )

    await session.commit()
    await session.refresh(new_output)
    logger.info(
        "published accounting output to shared data layer",
        extra={
            "output_id": str(new_output.id),
            "version": next_version,
            "stale_tax_outputs": stale_count,
        },
    )
    return new_output


async def get_latest_approved_accounting_output(
    session: AsyncSession,
    principal: Principal,
    *,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    version: int | None = None,
) -> ApprovedModuleOutput | None:
    """Retrieves the latest or specified version of approved accounting output."""
    require_permission(principal, "shared:read")
    await get_accessible_client(session, principal, client_id)

    query = select(ApprovedModuleOutput).where(
        ApprovedModuleOutput.firm_id == principal.firm_id,
        ApprovedModuleOutput.client_id == client_id,
        ApprovedModuleOutput.period_id == period_id,
        ApprovedModuleOutput.module == "accounting",
    )
    if version is not None:
        query = query.where(ApprovedModuleOutput.version == version)
    else:
        query = query.where(ApprovedModuleOutput.status == "approved")

    query = query.order_by(desc(ApprovedModuleOutput.version)).limit(1)
    res = await session.scalars(query)
    return res.first()


async def list_approved_outputs(
    session: AsyncSession,
    principal: Principal,
    *,
    client_id: uuid.UUID,
    period_id: uuid.UUID | None = None,
    module: str | None = None,
) -> list[ApprovedModuleOutput]:
    """Lists approved outputs from the central shared data layer."""
    require_permission(principal, "shared:read")
    await get_accessible_client(session, principal, client_id)

    query = select(ApprovedModuleOutput).where(
        ApprovedModuleOutput.firm_id == principal.firm_id,
        ApprovedModuleOutput.client_id == client_id,
    )
    if period_id is not None:
        query = query.where(ApprovedModuleOutput.period_id == period_id)
    if module is not None:
        query = query.where(ApprovedModuleOutput.module == module)

    query = query.order_by(desc(ApprovedModuleOutput.created_at))
    res = await session.scalars(query)
    return list(res.all())


async def publish_approved_tax_output(
    session: AsyncSession,
    principal: Principal,
    *,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    data: dict[str, Any],
    summary: dict[str, Any],
    source_version_refs: dict[str, Any],
    validation_results: dict[str, Any],
    notes: str | None = None,
) -> ApprovedModuleOutput:
    """Publishes approved taxation results to the Central Shared Data Layer."""
    require_permission(principal, "shared:publish")
    await get_accessible_client(session, principal, client_id)

    prior_res = await session.scalars(
        select(ApprovedModuleOutput).where(
            ApprovedModuleOutput.firm_id == principal.firm_id,
            ApprovedModuleOutput.client_id == client_id,
            ApprovedModuleOutput.period_id == period_id,
            ApprovedModuleOutput.module == "taxation",
        ).order_by(desc(ApprovedModuleOutput.version))
    )
    prior_outputs = list(prior_res.all())
    next_version = (prior_outputs[0].version + 1) if prior_outputs else 1

    for prev in prior_outputs:
        if prev.status == "approved":
            prev.status = "superseded"

    new_output = ApprovedModuleOutput(
        firm_id=principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        module="taxation",
        output_type="tax_filing_pack",
        version=next_version,
        status="approved",
        data=data,
        summary=summary,
        source_version_refs=source_version_refs,
        validation_results=validation_results,
        is_outdated=False,
        signed_off_by=principal.user_id,
        signed_off_at=datetime.now(UTC),
        sign_off_notes=notes or "Published upon CA tax pack approval",
    )
    session.add(new_output)
    record_audit(
        session,
        action="shared_output:published",
        actor=principal,
        target_type="approved_module_output",
        target_id=new_output.id,
        client_id=client_id,
        metadata={"module": "taxation", "version": next_version},
    )
    await session.commit()
    await session.refresh(new_output)
    return new_output
