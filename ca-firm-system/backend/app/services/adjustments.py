"""Adjustments service (Phase 7).

Manages lifecycle and CA approval for period-end adjustments.
Rules:
1. Proposed adjustments require explicit authorized CA approval (`adjustment:approve`).
2. Rejected or draft adjustments cannot feed reporting.
3. Editing an adjustment invalidates prior approval and increments version.
4. Full immutable history trail is preserved.
5. Strictly review/reporting preparation: NO LEDGER POSTING.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.models.adjustments import PeriodAdjustment
from app.services.authz import Principal, get_accessible_client, require_permission

logger = logging.getLogger("app.services.adjustments")


async def list_adjustments(
    session: AsyncSession,
    principal: Principal,
    *,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    status: str | None = None,
    category: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[PeriodAdjustment]:
    require_permission(principal, "adjustment:read")
    await get_accessible_client(session, principal, client_id)

    q = select(PeriodAdjustment).where(
        PeriodAdjustment.firm_id == principal.firm_id,
        PeriodAdjustment.client_id == client_id,
        PeriodAdjustment.period_id == period_id,
    )
    if status:
        q = q.where(PeriodAdjustment.status == status)
    if category:
        q = q.where(PeriodAdjustment.category == category)

    q = q.order_by(PeriodAdjustment.created_at.desc()).limit(limit).offset(offset)
    result = await session.scalars(q)
    return list(result.all())


async def get_adjustment(
    session: AsyncSession,
    principal: Principal,
    adjustment_id: uuid.UUID,
) -> PeriodAdjustment:
    require_permission(principal, "adjustment:read")
    adj = await session.scalar(
        select(PeriodAdjustment).where(
            PeriodAdjustment.id == adjustment_id,
            PeriodAdjustment.firm_id == principal.firm_id,
        )
    )
    if adj is None:
        raise NotFoundError("Adjustment not found")
    await get_accessible_client(session, principal, adj.client_id)
    return adj


async def create_adjustment(
    session: AsyncSession,
    principal: Principal,
    *,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    category: str,
    debit_account_code: str,
    debit_account_name: str,
    credit_account_code: str,
    credit_account_name: str,
    amount: Decimal,
    currency: str = "PKR",
    accounting_rationale: str,
    calculation_details: dict[str, Any] | None = None,
    source_refs: list[dict[str, Any]] | None = None,
    status: str = "proposed",
) -> PeriodAdjustment:
    require_permission(principal, "adjustment:propose")
    await get_accessible_client(session, principal, client_id)

    adj = PeriodAdjustment(
        firm_id=principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        category=category,
        status=status,
        version=1,
        debit_account_code=debit_account_code,
        debit_account_name=debit_account_name,
        credit_account_code=credit_account_code,
        credit_account_name=credit_account_name,
        amount=amount,
        currency=currency,
        accounting_rationale=accounting_rationale,
        calculation_details=calculation_details or {},
        source_refs=source_refs or [],
        prepared_by_agent="manual_user",
        created_by=principal.user_id,
        history=[
            {
                "action": "created",
                "status": status,
                "actor": str(principal.user_id),
                "timestamp": datetime.now(UTC).isoformat(),
                "note": "Created by user",
            }
        ],
    )
    session.add(adj)
    await session.commit()
    await session.refresh(adj)
    return adj


async def update_adjustment(
    session: AsyncSession,
    principal: Principal,
    adjustment_id: uuid.UUID,
    *,
    debit_account_code: str | None = None,
    debit_account_name: str | None = None,
    credit_account_code: str | None = None,
    credit_account_name: str | None = None,
    amount: Decimal | None = None,
    accounting_rationale: str | None = None,
    calculation_details: dict[str, Any] | None = None,
) -> PeriodAdjustment:
    require_permission(principal, "adjustment:propose")
    adj = await get_adjustment(session, principal, adjustment_id)

    prev_status = adj.status
    prev_version = adj.version

    if debit_account_code:
        adj.debit_account_code = debit_account_code
    if debit_account_name:
        adj.debit_account_name = debit_account_name
    if credit_account_code:
        adj.credit_account_code = credit_account_code
    if credit_account_name:
        adj.credit_account_name = credit_account_name
    if amount is not None:
        adj.amount = amount
    if accounting_rationale:
        adj.accounting_rationale = accounting_rationale
    if calculation_details is not None:
        adj.calculation_details = calculation_details

    # If the adjustment was approved, editing invalidates prior approval!
    adj.version = prev_version + 1
    if prev_status == "approved":
        adj.status = "proposed"
        adj.reviewer_id = None
        adj.reviewed_at = None
        adj.reviewer_decision = None

    history_entry = {
        "action": "edited",
        "actor": str(principal.user_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "previous_version": prev_version,
        "new_version": adj.version,
        "previous_status": prev_status,
        "new_status": adj.status,
    }
    adj.history = [*adj.history, history_entry]
    adj.updated_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(adj)
    return adj


async def decide_adjustment(
    session: AsyncSession,
    principal: Principal,
    adjustment_id: uuid.UUID,
    *,
    decision: str,  # "approved" | "rejected"
    comments: str | None = None,
) -> PeriodAdjustment:
    """Formal CA review decision. Only users with `adjustment:approve` can decide."""
    require_permission(principal, "adjustment:approve")
    if decision not in ("approved", "rejected"):
        raise ValueError("Decision must be 'approved' or 'rejected'")

    adj = await get_adjustment(session, principal, adjustment_id)

    adj.status = decision
    adj.reviewer_id = principal.user_id
    adj.reviewed_at = datetime.now(UTC)
    adj.reviewer_decision = decision
    adj.reviewer_comments = comments
    adj.updated_at = datetime.now(UTC)

    history_entry = {
        "action": decision,
        "actor": str(principal.user_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "decision": decision,
        "comments": comments or "",
    }
    adj.history = [*adj.history, history_entry]

    await session.commit()
    await session.refresh(adj)
    logger.info(
        "adjustment decision recorded",
        extra={"adjustment_id": str(adj.id), "decision": decision, "ca": str(principal.user_id)},
    )
    return adj


async def get_approved_adjustments(
    session: AsyncSession,
    firm_id: uuid.UUID,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
) -> list[PeriodAdjustment]:
    """Returns ONLY currently approved adjustments for feeding the Adjusted Trial Balance."""
    result = await session.scalars(
        select(PeriodAdjustment).where(
            PeriodAdjustment.firm_id == firm_id,
            PeriodAdjustment.client_id == client_id,
            PeriodAdjustment.period_id == period_id,
            PeriodAdjustment.status == "approved",
        )
    )
    return list(result.all())
