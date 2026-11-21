"""Central Shared Data Layer API.

Provides controlled access to published approved outputs, versions,
cross-module data sharing, and invalidation tracking.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import Principal, SessionDep, requires
from app.schemas.shared_data import (
    ApprovedModuleOutputListOut,
    ApprovedModuleOutputOut,
    PublishAccountingOutputIn,
)
from app.services import shared_data as shared_svc

router = APIRouter(
    prefix="/clients/{client_id}/periods/{period_id}/shared",
    tags=["shared-data"],
)


@router.post(
    "/publish-accounting",
    response_model=ApprovedModuleOutputOut,
    status_code=201,
    summary="Publish approved accounting outputs to the Central Shared Data Layer",
)
async def publish_accounting_output(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    body: PublishAccountingOutputIn,
    session: SessionDep,
    principal: Principal = Depends(requires("shared:publish")),
) -> ApprovedModuleOutputOut:
    out = await shared_svc.publish_approved_accounting_output(
        session,
        principal,
        client_id=client_id,
        period_id=period_id,
        notes=body.notes,
    )
    return ApprovedModuleOutputOut.model_validate(out)


@router.get(
    "/outputs",
    response_model=ApprovedModuleOutputListOut,
    summary="List published approved module outputs",
)
async def list_outputs(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("shared:read")),
    module: str | None = Query(default=None),
) -> ApprovedModuleOutputListOut:
    items = await shared_svc.list_approved_outputs(
        session,
        principal,
        client_id=client_id,
        period_id=period_id,
        module=module,
    )
    return ApprovedModuleOutputListOut(
        items=[ApprovedModuleOutputOut.model_validate(i) for i in items],
        total=len(items),
    )


@router.get(
    "/outputs/latest-accounting",
    response_model=ApprovedModuleOutputOut | None,
    summary="Get latest approved accounting output version",
)
async def get_latest_accounting(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(requires("shared:read")),
    version: int | None = Query(default=None),
) -> ApprovedModuleOutputOut | None:
    out = await shared_svc.get_latest_approved_accounting_output(
        session,
        principal,
        client_id=client_id,
        period_id=period_id,
        version=version,
    )
    return ApprovedModuleOutputOut.model_validate(out) if out else None
