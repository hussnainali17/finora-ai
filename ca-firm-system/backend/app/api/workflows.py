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
from app.models.workflows import WorkflowRun
from app.services.authz import get_accessible_client
from app.workflows.orchestrator import WorkflowOrchestrator

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
