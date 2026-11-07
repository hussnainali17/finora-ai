"""Reading the audit trail, scoped to what the caller may see."""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent
from app.services.authz import Principal, assigned_client_ids, require_permission


async def list_audit_events(
    session: AsyncSession,
    principal: Principal,
    *,
    limit: int,
    offset: int,
    action: str | None = None,
    client_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> tuple[list[AuditEvent], int]:
    require_permission(principal, "audit:read")
    stmt = select(AuditEvent).where(AuditEvent.firm_id == principal.firm_id)
    if not principal.can_access_all_clients:
        # Reviewers see only events tied to clients they are assigned to - never firm-level or
        # other clients' events.
        stmt = stmt.where(AuditEvent.client_id.in_(assigned_client_ids(principal)))
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if client_id:
        stmt = stmt.where(AuditEvent.client_id == client_id)
    if actor_user_id:
        stmt = stmt.where(AuditEvent.actor_user_id == actor_user_id)
    if since:
        stmt = stmt.where(AuditEvent.created_at >= since)
    if until:
        stmt = stmt.where(AuditEvent.created_at <= until)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.scalars(
        stmt.order_by(AuditEvent.created_at.desc(), AuditEvent.id).limit(limit).offset(offset)
    )
    return list(rows), total
