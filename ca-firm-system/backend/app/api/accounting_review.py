"""Accounting Review API — Phase 6.

Routes are nested under /clients/{client_id}/periods/{period_id}/review.

All routes enforce:
- JWT authentication (via get_principal dep)
- Permission checks (review:read / review:manage / review:resolve)
- Firm and client isolation (service layer re-checks after route-level gate)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import PrincipalDep, SessionDep, requires
from app.schemas.accounting_review import (
    FindingStatusUpdate,
    ReconciliationScheduleOut,
    ReviewFindingListOut,
    ReviewFindingOut,
    ReviewRunListOut,
    ReviewRunOut,
    TriggerReviewIn,
)
from app.services import accounting_review as review_svc

router = APIRouter(
    prefix="/clients/{client_id}/periods/{period_id}/review",
    tags=["accounting-review"],
)


@router.post(
    "/",
    response_model=ReviewRunOut,
    status_code=201,
    summary="Trigger a new accounting review run",
)
async def trigger_review(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    body: TriggerReviewIn,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("review:manage")),
) -> ReviewRunOut:
    run = await review_svc.create_review_run(
        session,
        principal,
        client_id=client_id,
        period_id=period_id,
        trigger="manual",
    )
    return ReviewRunOut.model_validate(run)


@router.get(
    "/",
    response_model=ReviewRunListOut,
    summary="List accounting review runs for a client/period",
)
async def list_review_runs(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("review:read")),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ReviewRunListOut:
    runs = await review_svc.list_review_runs(
        session,
        principal,
        client_id=client_id,
        period_id=period_id,
        limit=limit,
        offset=offset,
    )
    return ReviewRunListOut(
        items=[ReviewRunOut.model_validate(r) for r in runs],
        total=len(runs),
    )


@router.get(
    "/{review_run_id}",
    response_model=ReviewRunOut,
    summary="Get a specific review run",
)
async def get_review_run(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    review_run_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("review:read")),
) -> ReviewRunOut:
    run = await review_svc.get_review_run(session, principal, review_run_id)
    return ReviewRunOut.model_validate(run)


@router.get(
    "/{review_run_id}/findings",
    response_model=ReviewFindingListOut,
    summary="List findings for a review run (filterable)",
)
async def list_findings(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    review_run_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("review:read")),
    module: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ReviewFindingListOut:
    findings = await review_svc.list_findings(
        session,
        principal,
        review_run_id,
        module=module,
        severity=severity,
        status=status,
        limit=limit,
        offset=offset,
    )
    return ReviewFindingListOut(
        items=[ReviewFindingOut.model_validate(f) for f in findings],
        total=len(findings),
    )


@router.patch(
    "/{review_run_id}/findings/{finding_id}",
    response_model=ReviewFindingOut,
    summary="Update a finding's status (open/explained/resolved/escalated)",
)
async def update_finding(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    review_run_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: FindingStatusUpdate,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("review:resolve")),
) -> ReviewFindingOut:
    finding = await review_svc.update_finding_status(
        session,
        principal,
        finding_id,
        new_status=body.status,
        reviewer_note=body.reviewer_note,
    )
    return ReviewFindingOut.model_validate(finding)


@router.get(
    "/{review_run_id}/schedules",
    response_model=list[ReconciliationScheduleOut],
    summary="List reconciliation schedules for a review run",
)
async def list_schedules(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    review_run_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("review:read")),
) -> list[ReconciliationScheduleOut]:
    schedules = await review_svc.list_schedules(session, principal, review_run_id)
    return [ReconciliationScheduleOut.model_validate(s) for s in schedules]


@router.get(
    "/{review_run_id}/schedules/{schedule_id}",
    response_model=ReconciliationScheduleOut,
    summary="Get a specific reconciliation schedule",
)
async def get_schedule(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    review_run_id: uuid.UUID,
    schedule_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep = Depends(requires("review:read")),
) -> ReconciliationScheduleOut:
    schedule = await review_svc.get_schedule(
        session, principal, review_run_id, schedule_id
    )
    return ReconciliationScheduleOut.model_validate(schedule)
