"""Workflows API (Phase 9 - LangGraph End-to-End Orchestration).

Nested under /clients/{client_id}/periods/{period_id}/workflows.
Enforces:
- `workflow:read` for viewing workflow state and checkpoints
- `workflow:execute` for triggering and resuming workflows
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import Principal, SessionDep, requires
from app.models.taxation import MultiModuleWorkflowRun
from app.models.workflows import WorkflowRun
from app.schemas.taxation import MultiModuleWorkflowRunOut
from app.services.authz import get_accessible_client
from app.workflows.orchestrator import WorkflowOrchestrator
from app.workflows.coordination.complete_workflow import CompleteCAWorkflowOrchestrator

router = APIRouter(
    prefix="/clients/{client_id}/periods/{period_id}/workflows",
    tags=["workflows"],
)


class WorkflowRunOut(BaseModel):
    id: uuid.UUID
    firm_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    status: str
    current_step: str
    state_data: dict[str, Any]
    checkpoint_id: str | None
    error_message: str | None
    created_at: Any
    updated_at: Any

    model_config = {"from_attributes": True}


@router.post(
    "/",
    response_model=WorkflowRunOut,
    status_code=201,
    summary="Start an end-to-end accounting review & reporting workflow",
)
async def start_workflow(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("workflow:execute")),
) -> WorkflowRunOut:
    await get_accessible_client(session, principal, client_id)
    orch = WorkflowOrchestrator()
    run = await orch.initiate_workflow(
        session,
        firm_id=principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        user_id=principal.user_id,
    )
    await session.refresh(run)
    return WorkflowRunOut.model_validate(run)


@router.get(
    "/",
    response_model=list[WorkflowRunOut],
    summary="List workflow runs for a client period",
)
async def list_workflows(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("workflow:read")),
) -> list[WorkflowRunOut]:
    await get_accessible_client(session, principal, client_id)
    runs = await session.scalars(
        select(WorkflowRun)
        .where(
            WorkflowRun.firm_id == principal.firm_id,
            WorkflowRun.client_id == client_id,
            WorkflowRun.period_id == period_id,
        )
        .order_by(WorkflowRun.created_at.desc())
    )
    return [WorkflowRunOut.model_validate(r) for r in runs.all()]


@router.get(
    "/{workflow_id}",
    response_model=WorkflowRunOut,
    summary="Get current state and checkpoint of a workflow run",
)
async def get_workflow(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    workflow_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("workflow:read")),
) -> WorkflowRunOut:
    await get_accessible_client(session, principal, client_id)
    run = await session.scalar(
        select(WorkflowRun).where(
            WorkflowRun.id == workflow_id,
            WorkflowRun.firm_id == principal.firm_id,
            WorkflowRun.client_id == client_id,
        )
    )
    if not run:
        raise ValueError("Workflow run not found")
    return WorkflowRunOut.model_validate(run)


@router.post(
    "/{workflow_id}/resume",
    response_model=WorkflowRunOut,
    summary="Resume a paused workflow after CA approval decision",
)
async def resume_workflow(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    workflow_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("workflow:execute")),
) -> WorkflowRunOut:
    await get_accessible_client(session, principal, client_id)
    orch = WorkflowOrchestrator()
    run = await orch.resume_after_ca_approval(session, workflow_id)
    await session.refresh(run)
    return WorkflowRunOut.model_validate(run)


# ----------------------------------------------------------------------------- Complete CA Workflow
@router.post(
    "/complete/start",
    response_model=MultiModuleWorkflowRunOut,
    status_code=201,
    summary="Start Complete CA Multi-Module Workflow (Accounting -> Shared Layer -> Taxation)",
)
async def start_complete_workflow(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("workflow:execute")),
    tax_year: int = Query(default=2025),
) -> MultiModuleWorkflowRunOut:
    await get_accessible_client(session, principal, client_id)
    orch = CompleteCAWorkflowOrchestrator()
    run = await orch.initiate_complete_workflow(
        session,
        firm_id=principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        principal=principal,
        tax_year=tax_year,
    )
    await session.refresh(run)
    return MultiModuleWorkflowRunOut.model_validate(run)


@router.get(
    "/complete",
    response_model=list[MultiModuleWorkflowRunOut],
    summary="List Complete CA Workflow runs",
)
async def list_complete_workflows(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("workflow:read")),
) -> list[MultiModuleWorkflowRunOut]:
    await get_accessible_client(session, principal, client_id)
    runs = await session.scalars(
        select(MultiModuleWorkflowRun)
        .where(
            MultiModuleWorkflowRun.firm_id == principal.firm_id,
            MultiModuleWorkflowRun.client_id == client_id,
            MultiModuleWorkflowRun.period_id == period_id,
        )
        .order_by(MultiModuleWorkflowRun.created_at.desc())
    )
    return [MultiModuleWorkflowRunOut.model_validate(r) for r in runs.all()]


@router.get(
    "/complete/{run_id}",
    response_model=MultiModuleWorkflowRunOut,
    summary="Get Complete CA Workflow run state",
)
async def get_complete_workflow(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    run_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("workflow:read")),
) -> MultiModuleWorkflowRunOut:
    await get_accessible_client(session, principal, client_id)
    run = await session.get(MultiModuleWorkflowRun, run_id)
    if not run or run.firm_id != principal.firm_id:
        raise ValueError("Complete CA Workflow run not found")
    return MultiModuleWorkflowRunOut.model_validate(run)


@router.post(
    "/complete/{run_id}/resume",
    response_model=MultiModuleWorkflowRunOut,
    summary="Resume Complete CA Workflow at human approval checkpoint",
)
async def resume_complete_workflow(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    run_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("workflow:execute")),
    notes: str | None = Query(default=None),
) -> MultiModuleWorkflowRunOut:
    await get_accessible_client(session, principal, client_id)
    orch = CompleteCAWorkflowOrchestrator()
    run = await orch.resume_complete_workflow(
        session,
        workflow_id=run_id,
        principal=principal,
        notes=notes,
    )
    await session.refresh(run)
    return MultiModuleWorkflowRunOut.model_validate(run)

