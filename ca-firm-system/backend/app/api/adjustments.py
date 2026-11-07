"""Period-End Adjustments API (Phase 7).

Nested under /clients/{client_id}/periods/{period_id}/adjustments.
Enforces:
- `adjustment:read` for viewing
- `adjustment:propose` for drafting/updating
- `adjustment:approve` for CA approval/rejection
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.agents.adjustments_agent.agent import AdjustmentsAgent
from app.api.deps import PrincipalDep, SessionDep, requires
from app.schemas.adjustments import (
    AdjustmentCreateIn,
    AdjustmentDecisionIn,
    AdjustmentListOut,
    AdjustmentUpdateIn,
    PeriodAdjustmentOut,
)
from app.services import adjustments as adj_svc

router = APIRouter(
    prefix="/clients/{client_id}/periods/{period_id}/adjustments",
    tags=["adjustments"],
)


@router.get(
    "/",
    response_model=AdjustmentListOut,
    summary="List proposed/approved adjustments for a client period",
)
async def list_adjustments(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("adjustment:read")),
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AdjustmentListOut:
    items = await adj_svc.list_adjustments(
        session,
        principal,
        client_id=client_id,
        period_id=period_id,
        status=status,
        category=category,
        limit=limit,
        offset=offset,
    )
    return AdjustmentListOut(
        items=[PeriodAdjustmentOut.model_validate(i) for i in items],
        total=len(items),
    )


@router.post(
    "/generate",
    response_model=list[PeriodAdjustmentOut],
    status_code=201,
    summary="Trigger Agent 3 to generate proposed adjustments",
)
async def generate_adjustments(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("adjustment:propose")),
) -> list[PeriodAdjustmentOut]:
    agent = AdjustmentsAgent()
    generated = await agent.generate_adjustments_for_period(
        session,
        client_id=client_id,
        period_id=period_id,
        firm_id=principal.firm_id,
    )
    return [PeriodAdjustmentOut.model_validate(g) for g in generated]


@router.post(
    "/",
    response_model=PeriodAdjustmentOut,
    status_code=201,
    summary="Manually propose a period-end adjustment",
)
async def create_adjustment(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    body: AdjustmentCreateIn,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("adjustment:propose")),
) -> PeriodAdjustmentOut:
    adj = await adj_svc.create_adjustment(
        session,
        principal,
        client_id=client_id,
        period_id=period_id,
        category=body.category,
        debit_account_code=body.debit_account_code,
        debit_account_name=body.debit_account_name,
        credit_account_code=body.credit_account_code,
        credit_account_name=body.credit_account_name,
        amount=body.amount,
        currency=body.currency,
        accounting_rationale=body.accounting_rationale,
        calculation_details=body.calculation_details,
        source_refs=body.source_refs,
    )
    return PeriodAdjustmentOut.model_validate(adj)


@router.get(
    "/{adjustment_id}",
    response_model=PeriodAdjustmentOut,
    summary="Get adjustment details and audit history",
)
async def get_adjustment(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    adjustment_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("adjustment:read")),
) -> PeriodAdjustmentOut:
    adj = await adj_svc.get_adjustment(session, principal, adjustment_id)
    return PeriodAdjustmentOut.model_validate(adj)


@router.patch(
    "/{adjustment_id}",
    response_model=PeriodAdjustmentOut,
    summary="Edit an adjustment (creates new version, resets approval)",
)
async def update_adjustment(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    adjustment_id: uuid.UUID,
    body: AdjustmentUpdateIn,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("adjustment:propose")),
) -> PeriodAdjustmentOut:
    adj = await adj_svc.update_adjustment(
        session,
        principal,
        adjustment_id,
        debit_account_code=body.debit_account_code,
        debit_account_name=body.debit_account_name,
        credit_account_code=body.credit_account_code,
        credit_account_name=body.credit_account_name,
        amount=body.amount,
        accounting_rationale=body.accounting_rationale,
        calculation_details=body.calculation_details,
    )
    return PeriodAdjustmentOut.model_validate(adj)


@router.post(
    "/{adjustment_id}/decision",
    response_model=PeriodAdjustmentOut,
    summary="CA approve or reject an adjustment proposal",
)
async def decide_adjustment(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    adjustment_id: uuid.UUID,
    body: AdjustmentDecisionIn,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("adjustment:approve")),
) -> PeriodAdjustmentOut:
    adj = await adj_svc.decide_adjustment(
        session,
        principal,
        adjustment_id,
        decision=body.decision,
        comments=body.comments,
    )
    return PeriodAdjustmentOut.model_validate(adj)
