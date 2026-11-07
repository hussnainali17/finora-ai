"""Clients, accounting periods and client-access assignments - all scoped through ``authz``."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, DomainValidationError, NotFoundError
from app.models import AccountingPeriod, Client, User, UserClientAccess
from app.services.audit import record_audit
from app.services.authz import (
    Principal,
    client_scope,
    get_accessible_client,
    require_permission,
)

# ----------------------------------------------------------------------------- clients


async def list_clients(
    session: AsyncSession,
    principal: Principal,
    *,
    limit: int,
    offset: int,
    status: str | None = None,
    q: str | None = None,
) -> tuple[list[Client], int]:
    require_permission(principal, "client:read")
    stmt = select(Client).where(*client_scope(principal))
    if status:
        stmt = stmt.where(Client.status == status)
    if q:
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        stmt = stmt.where(or_(Client.name.ilike(like), Client.code.ilike(like)))
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (await session.scalars(stmt.order_by(Client.name).limit(limit).offset(offset))).all()
    return list(rows), total


async def get_client(session: AsyncSession, principal: Principal, client_id: uuid.UUID) -> Client:
    require_permission(principal, "client:read")
    return await get_accessible_client(session, principal, client_id)


async def create_client(
    session: AsyncSession,
    principal: Principal,
    *,
    code: str,
    name: str,
    legal_name: str | None,
    base_currency: str,
    fiscal_year_end_month: int,
    notes: str | None,
) -> Client:
    require_permission(principal, "client:create")
    client = Client(
        firm_id=principal.firm_id,
        code=code,
        name=name,
        legal_name=legal_name,
        base_currency=base_currency,
        fiscal_year_end_month=fiscal_year_end_month,
        notes=notes,
        created_by=principal.user_id,
    )
    session.add(client)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("A client with this code already exists") from exc
    if not principal.can_access_all_clients:
        # The creator must be able to see what they just created.
        session.add(
            UserClientAccess(
                user_id=principal.user_id,
                client_id=client.id,
                firm_id=principal.firm_id,
                granted_by=principal.user_id,
            )
        )
    record_audit(
        session,
        action="client.created",
        actor=principal,
        target_type="client",
        target_id=client.id,
        client_id=client.id,
        metadata={"code": code, "name": name},
    )
    await session.commit()
    return client


async def update_client(
    session: AsyncSession, principal: Principal, client_id: uuid.UUID, *, changes: dict[str, Any]
) -> Client:
    require_permission(principal, "client:update")
    client = await get_accessible_client(session, principal, client_id)
    before = {k: getattr(client, k) for k in changes}
    for key, value in changes.items():
        setattr(client, key, value)
    status_changed = "status" in changes and before["status"] != client.status
    record_audit(
        session,
        action=f"client.{client.status}" if status_changed else "client.updated",
        actor=principal,
        target_type="client",
        target_id=client.id,
        client_id=client.id,
        metadata={"before": before, "after": {k: getattr(client, k) for k in changes}},
    )
    await session.commit()
    await session.refresh(client)
    return client


# ----------------------------------------------------------------------------- periods


async def list_periods(
    session: AsyncSession, principal: Principal, client_id: uuid.UUID
) -> list[AccountingPeriod]:
    require_permission(principal, "period:read")
    client = await get_accessible_client(session, principal, client_id)
    rows = await session.scalars(
        select(AccountingPeriod)
        .where(
            AccountingPeriod.client_id == client.id, AccountingPeriod.firm_id == principal.firm_id
        )
        .order_by(AccountingPeriod.start_date.desc())
    )
    return list(rows)


async def _get_period(
    session: AsyncSession, principal: Principal, client_id: uuid.UUID, period_id: uuid.UUID
) -> AccountingPeriod:
    client = await get_accessible_client(session, principal, client_id)
    period = await session.scalar(
        select(AccountingPeriod).where(
            AccountingPeriod.id == period_id,
            AccountingPeriod.client_id == client.id,
            AccountingPeriod.firm_id == principal.firm_id,
        )
    )
    if period is None:
        raise NotFoundError("Accounting period not found")
    return period


async def get_period(
    session: AsyncSession, principal: Principal, client_id: uuid.UUID, period_id: uuid.UUID
) -> AccountingPeriod:
    require_permission(principal, "period:read")
    return await _get_period(session, principal, client_id, period_id)


def _overlap_conflict(exc: IntegrityError) -> ConflictError | None:
    if "ex_accounting_periods_no_overlap" in str(exc.orig):
        return ConflictError("Period overlaps an existing period for this client")
    if "uq_accounting_periods_client_id_label" in str(exc.orig):
        return ConflictError("A period with this label already exists for this client")
    return None


async def create_period(
    session: AsyncSession,
    principal: Principal,
    client_id: uuid.UUID,
    *,
    label: str,
    start_date: Any,
    end_date: Any,
) -> AccountingPeriod:
    require_permission(principal, "period:create")
    client = await get_accessible_client(session, principal, client_id)
    if client.status != "active":
        raise ConflictError("Cannot add periods to an archived client")
    period = AccountingPeriod(
        firm_id=client.firm_id,
        client_id=client.id,
        label=label,
        start_date=start_date,
        end_date=end_date,
        created_by=principal.user_id,
    )
    session.add(period)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        if (conflict := _overlap_conflict(exc)) is not None:
            raise conflict from exc
        raise
    record_audit(
        session,
        action="period.created",
        actor=principal,
        target_type="accounting_period",
        target_id=period.id,
        client_id=client.id,
        metadata={"label": label, "start_date": start_date, "end_date": end_date},
    )
    await session.commit()
    return period


async def update_period(
    session: AsyncSession,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    *,
    changes: dict[str, Any],
) -> AccountingPeriod:
    require_permission(principal, "period:update")
    period = await _get_period(session, principal, client_id, period_id)
    if period.status != "open":
        raise ConflictError("A closed period cannot be edited; reopen it first")
    before = {k: getattr(period, k) for k in changes}
    for key, value in changes.items():
        setattr(period, key, value)
    if period.end_date < period.start_date:
        await session.rollback()
        raise DomainValidationError("end_date must be on or after start_date")
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        if (conflict := _overlap_conflict(exc)) is not None:
            raise conflict from exc
        raise
    record_audit(
        session,
        action="period.updated",
        actor=principal,
        target_type="accounting_period",
        target_id=period.id,
        client_id=period.client_id,
        metadata={"before": before, "after": {k: getattr(period, k) for k in changes}},
    )
    await session.commit()
    await session.refresh(period)
    return period


async def set_period_status(
    session: AsyncSession,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    *,
    close: bool,
) -> AccountingPeriod:
    require_permission(principal, "period:close")
    period = await _get_period(session, principal, client_id, period_id)
    target = "closed" if close else "open"
    if period.status == target:
        raise ConflictError(f"Period is already {target}")
    period.status = target
    period.closed_at = datetime.now(UTC) if close else None
    period.closed_by = principal.user_id if close else None
    record_audit(
        session,
        action="period.closed" if close else "period.reopened",
        actor=principal,
        target_type="accounting_period",
        target_id=period.id,
        client_id=period.client_id,
        metadata={"label": period.label},
    )
    await session.commit()
    await session.refresh(period)
    return period


# ----------------------------------------------------------------------------- access


async def list_access(
    session: AsyncSession, principal: Principal, client_id: uuid.UUID
) -> list[tuple[UserClientAccess, User]]:
    require_permission(principal, "client:access_manage")
    client = await get_accessible_client(session, principal, client_id)
    rows = await session.execute(
        select(UserClientAccess, User)
        .join(
            User,
            (User.id == UserClientAccess.user_id) & (User.firm_id == UserClientAccess.firm_id),
        )
        .where(
            UserClientAccess.client_id == client.id, UserClientAccess.firm_id == principal.firm_id
        )
        .order_by(User.email)
    )
    return [(a, u) for a, u in rows.all()]


async def grant_access(
    session: AsyncSession, principal: Principal, client_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[UserClientAccess, User]:
    require_permission(principal, "client:access_manage")
    client = await get_accessible_client(session, principal, client_id)
    user = await session.scalar(
        select(User).where(User.id == user_id, User.firm_id == principal.firm_id)
    )
    if user is None:  # also covers users belonging to another firm
        raise NotFoundError("User not found")
    if not user.is_active:
        raise ConflictError("Cannot assign an inactive user")
    existing = await session.get(UserClientAccess, (user.id, client.id))
    if existing is not None:
        return existing, user  # idempotent
    access = UserClientAccess(
        user_id=user.id,
        client_id=client.id,
        firm_id=principal.firm_id,
        granted_by=principal.user_id,
    )
    session.add(access)
    record_audit(
        session,
        action="client_access.granted",
        actor=principal,
        target_type="user",
        target_id=user.id,
        client_id=client.id,
        metadata={"user_email": user.email},
    )
    await session.commit()
    await session.refresh(access)
    return access, user


async def revoke_access(
    session: AsyncSession, principal: Principal, client_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    require_permission(principal, "client:access_manage")
    client = await get_accessible_client(session, principal, client_id)
    access = await session.get(UserClientAccess, (user_id, client.id))
    if access is None or access.firm_id != principal.firm_id:
        raise NotFoundError("Assignment not found")
    await session.delete(access)
    record_audit(
        session,
        action="client_access.revoked",
        actor=principal,
        target_type="user",
        target_id=user_id,
        client_id=client.id,
    )
    await session.commit()
