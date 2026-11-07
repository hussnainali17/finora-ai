import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import PrincipalDep, SessionDep
from app.schemas.audit import AuditEventOut
from app.schemas.common import Page
from app.services.audit_query import list_audit_events

router = APIRouter(prefix="/audit-events", tags=["audit"])


@router.get("", response_model=Page[AuditEventOut])
async def get_audit_events(
    principal: PrincipalDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    action: Annotated[str | None, Query(max_length=80)] = None,
    client_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Page[AuditEventOut]:
    rows, total = await list_audit_events(
        session,
        principal,
        limit=limit,
        offset=offset,
        action=action,
        client_id=client_id,
        actor_user_id=actor_user_id,
        since=since,
        until=until,
    )
    return Page(
        items=[AuditEventOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
