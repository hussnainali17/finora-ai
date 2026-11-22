"""Pakistan Taxation API.

Provides endpoints for:
- Tax Engagements
- Agent 1: Tax Intake & Taxpayer Profile
- Agent 2: Tax Data Mapping & Reconciliations
- Agent 3: Deterministic Tax Computations
- Agent 4: Tax Review, CA Sign-off & Filing Evidence
- Independent Taxation LangGraph Workflow execution
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.agents.tax_computation_agent.agent import TaxComputationAgent
from app.agents.tax_data_agent.agent import TaxDataAgent
from app.agents.tax_intake_agent.agent import TaxIntakeAgent
from app.agents.tax_review_agent.agent import TaxReviewAgent
from app.api.deps import Principal, SessionDep, requires
from app.schemas.taxation import (
    CreateTaxEngagementIn,
    FilingEvidenceIn,
    InitiateTaxWorkflowIn,
    TaxCalculationRunOut,
    TaxEngagementListOut,
    TaxEngagementOut,
    TaxpayerProfileIn,
    TaxpayerProfileOut,
    TaxReturnDraftOut,
    TaxSignOffIn,
    TaxWorkflowRunOut,
    TaxWorkpaperListOut,
    TaxWorkpaperOut,
)
from app.services import taxation as tax_svc
from app.workflows.taxation.orchestrator import TaxWorkflowOrchestrator

router = APIRouter(
    prefix="/clients/{client_id}/periods/{period_id}/taxation",
    tags=["taxation"],
)


# ----------------------------------------------------------------------------- Engagements
@router.post(
    "/engagements",
    response_model=TaxEngagementOut,
    status_code=201,
    summary="Create a new tax engagement",
)
async def create_engagement(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    body: CreateTaxEngagementIn,
    session: SessionDep,
    principal: Principal = Depends(requires("tax:manage")),
) -> TaxEngagementOut:
    eng = await tax_svc.create_tax_engagement(
        session,
        principal,
        client_id=client_id,
        period_id=period_id,
        tax_year=body.tax_year,
        tax_period_label=body.tax_period_label,
        tax_type=body.tax_type,
        notes=body.notes,
    )
    return TaxEngagementOut.model_validate(eng)


@router.get(
    "/engagements",
    response_model=TaxEngagementListOut,
    summary="List tax engagements for this client & period",
)
async def list_engagements(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("tax:read")),
) -> TaxEngagementListOut:
    items = await tax_svc.list_tax_engagements(
        session,
        principal,
        client_id=client_id,
        period_id=period_id,
    )
    return TaxEngagementListOut(
        items=[TaxEngagementOut.model_validate(i) for i in items],
        total=len(items),
    )


# ----------------------------------------------------------------------------- Agent 1
@router.post(
    "/engagements/{engagement_id}/intake",
    response_model=dict,
    summary="Execute Agent 1: Tax Intake & Taxpayer Profile",
)
async def execute_intake(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    engagement_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("tax:manage")),
    body: TaxpayerProfileIn | None = None,
) -> dict:
    agent = TaxIntakeAgent()
    return await agent.execute_intake(
        session,
        engagement_id=engagement_id,
        override_profile_data=body.model_dump() if body else None,
    )


@router.get(
    "/engagements/{engagement_id}/profile",
    response_model=TaxpayerProfileOut | None,
    summary="Get verified taxpayer profile and obligations",
)
async def get_profile(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    engagement_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("tax:read")),
) -> TaxpayerProfileOut | None:
    prof = await tax_svc.get_taxpayer_profile(session, principal, engagement_id)
    return TaxpayerProfileOut.model_validate(prof) if prof else None


# ----------------------------------------------------------------------------- Agent 2
@router.post(
    "/engagements/{engagement_id}/reconcile",
    response_model=dict,
    summary="Execute Agent 2: Tax Data Mapping & Reconciliations",
)
async def execute_reconcile(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    engagement_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("tax:manage")),
    source_origin: str = Query(default="approved_accounting"),
    version: int | None = Query(default=None),
) -> dict:
    agent = TaxDataAgent()
    return await agent.execute_data_and_reconciliation(
        session,
        engagement_id=engagement_id,
        principal=principal,
        source_origin_preference=source_origin,
        version=version,
    )


@router.get(
    "/engagements/{engagement_id}/workpapers",
    response_model=TaxWorkpaperListOut,
    summary="Get tax workpapers and reconciliations",
)
async def get_workpapers(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    engagement_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("tax:read")),
) -> TaxWorkpaperListOut:
    items = await tax_svc.list_tax_workpapers(session, principal, engagement_id)
    return TaxWorkpaperListOut(
        items=[TaxWorkpaperOut.model_validate(w) for w in items],
        total=len(items),
    )


# ----------------------------------------------------------------------------- Agent 3
@router.post(
    "/engagements/{engagement_id}/compute",
    response_model=dict,
    summary="Execute Agent 3: Tax Computation & Compliance Engine",
)
async def execute_compute(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    engagement_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("tax:manage")),
) -> dict:
    agent = TaxComputationAgent()
    return await agent.execute_computation(session, engagement_id=engagement_id)


@router.get(
    "/engagements/{engagement_id}/calculations",
    response_model=TaxCalculationRunOut | None,
    summary="Get latest deterministic tax calculation run",
)
async def get_calculations(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    engagement_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("tax:read")),
) -> TaxCalculationRunOut | None:
    calc = await tax_svc.get_latest_calculation_run(session, principal, engagement_id)
    return TaxCalculationRunOut.model_validate(calc) if calc else None


# ----------------------------------------------------------------------------- Agent 4
@router.post(
    "/engagements/{engagement_id}/review",
    response_model=dict,
    summary="Execute Agent 4: Tax Review & Draft Filing Pack",
)
async def execute_review(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    engagement_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("tax:manage")),
) -> dict:
    agent = TaxReviewAgent()
    return await agent.generate_review_and_draft(session, engagement_id=engagement_id)


@router.get(
    "/engagements/{engagement_id}/drafts",
    response_model=list[TaxReturnDraftOut],
    summary="List draft tax return packs",
)
async def list_drafts(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    engagement_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("tax:read")),
) -> list[TaxReturnDraftOut]:
    drafts = await tax_svc.list_tax_drafts(session, principal, engagement_id)
    return [TaxReturnDraftOut.model_validate(d) for d in drafts]


@router.post(
    "/drafts/{draft_id}/sign-off",
    response_model=TaxReturnDraftOut,
    summary="CA Reviewer sign-off on tax pack & publish to Shared Data Layer",
)
async def sign_off_draft(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: TaxSignOffIn,
    session: SessionDep,
    principal: Principal = Depends(requires("tax:approve")),
) -> TaxReturnDraftOut:
    agent = TaxReviewAgent()
    signed = await agent.sign_off_tax_pack(
        session,
        principal,
        draft_id=draft_id,
        notes=body.notes,
    )
    return TaxReturnDraftOut.model_validate(signed)


@router.post(
    "/drafts/{draft_id}/filing-evidence",
    response_model=TaxReturnDraftOut,
    summary="Record FBR IRIS filing evidence (CPRs, acknowledgment slip)",
)
async def record_filing(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: FilingEvidenceIn,
    session: SessionDep,
    principal: Principal = Depends(requires("tax:manage")),
) -> TaxReturnDraftOut:
    agent = TaxReviewAgent()
    filed = await agent.record_filing_evidence(
        session,
        principal,
        draft_id=draft_id,
        cpr_numbers=body.cpr_numbers,
        acknowledgment_number=body.acknowledgment_number,
        filing_date=body.filing_date,
        bank_name=body.bank_name,
        amount_paid=body.amount_paid,
        notes=body.notes,
    )
    return TaxReturnDraftOut.model_validate(filed)


# ----------------------------------------------------------------------------- Independent Workflow
@router.post(
    "/workflows/start",
    response_model=TaxWorkflowRunOut,
    status_code=201,
    summary="Trigger independent Pakistan Taxation LangGraph workflow",
)
async def start_tax_workflow(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    body: InitiateTaxWorkflowIn,
    session: SessionDep,
    principal: Principal = Depends(requires("workflow:execute")),
) -> TaxWorkflowRunOut:
    wf = TaxWorkflowOrchestrator()
    run = await wf.initiate_workflow(
        session,
        firm_id=principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        engagement_id=body.engagement_id,
        principal=principal,
        source_origin=body.source_origin,
        accounting_version=body.accounting_version,
    )
    return TaxWorkflowRunOut.model_validate(run)


@router.post(
    "/workflows/{workflow_id}/resume",
    response_model=TaxWorkflowRunOut,
    summary="Resume paused Taxation workflow upon CA approval",
)
async def resume_tax_workflow(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    workflow_id: uuid.UUID,
    body: TaxSignOffIn,
    session: SessionDep,
    principal: Principal = Depends(requires("tax:approve")),
) -> TaxWorkflowRunOut:
    wf = TaxWorkflowOrchestrator()
    run = await wf.resume_after_ca_approval(
        session,
        workflow_id=workflow_id,
        principal=principal,
        notes=body.notes,
    )
    return TaxWorkflowRunOut.model_validate(run)


@router.get(
    "/workflows/{workflow_id}",
    response_model=TaxWorkflowRunOut,
    summary="Get status of a Taxation workflow run",
)
async def get_tax_workflow(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    workflow_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("workflow:read")),
) -> TaxWorkflowRunOut:
    run = await session.get(tax_svc.TaxWorkflowRun, workflow_id)
    if not run or run.firm_id != principal.firm_id:
        raise NotFoundError("TaxWorkflowRun not found")
    return TaxWorkflowRunOut.model_validate(run)
