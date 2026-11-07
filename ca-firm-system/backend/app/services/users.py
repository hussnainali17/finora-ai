"""User administration (firm-scoped; requires ``user:read`` / ``user:manage``)."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, DomainValidationError, NotFoundError
from app.core.permissions import ASSIGNABLE_ROLE_KEYS, FIRM_ADMIN
from app.core.security import hash_password, validate_password_strength
from app.models import User
from app.services.audit import record_audit
from app.services.auth import revoke_all_sessions
from app.services.authz import Principal, require_permission


async def list_users(
    session: AsyncSession, principal: Principal, *, limit: int, offset: int
) -> tuple[list[User], int]:
    require_permission(principal, "user:read")
    base = select(User).where(User.firm_id == principal.firm_id)
    total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (await session.scalars(base.order_by(User.email).limit(limit).offset(offset))).all()
    return list(rows), total


async def _get_user(session: AsyncSession, principal: Principal, user_id: uuid.UUID) -> User:
    user = await session.scalar(
        select(User).where(User.id == user_id, User.firm_id == principal.firm_id)
    )
    if user is None:
        raise NotFoundError("User not found")
    return user


async def get_user(session: AsyncSession, principal: Principal, user_id: uuid.UUID) -> User:
    require_permission(principal, "user:read")
    return await _get_user(session, principal, user_id)


async def create_user(
    session: AsyncSession,
    principal: Principal,
    *,
    email: str,
    full_name: str,
    role_key: str,
    password: str,
) -> User:
    require_permission(principal, "user:manage")
    if role_key not in ASSIGNABLE_ROLE_KEYS:
        raise DomainValidationError("Unknown role")
    validate_password_strength(password)
    user = User(
        firm_id=principal.firm_id,  # always the caller's firm - never taken from input
        email=email.strip().lower(),
        full_name=full_name,
        role_key=role_key,
        password_hash=hash_password(password),
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("A user with this email already exists") from exc
    record_audit(
        session,
        action="user.created",
        actor=principal,
        target_type="user",
        target_id=user.id,
        metadata={"email": user.email, "role": role_key},
    )
    await session.commit()
    return await _get_user(session, principal, user.id)


async def _active_admin_count(session: AsyncSession, firm_id: uuid.UUID) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.firm_id == firm_id, User.role_key == FIRM_ADMIN, User.is_active.is_(True))
        )
        or 0
    )


async def update_user(
    session: AsyncSession,
    principal: Principal,
    user_id: uuid.UUID,
    *,
    changes: dict[str, Any],
) -> User:
    require_permission(principal, "user:manage")
    user = await _get_user(session, principal, user_id)
    if "role_key" in changes and changes["role_key"] not in ASSIGNABLE_ROLE_KEYS:
        raise DomainValidationError("Unknown role")

    was_admin = user.role_key == FIRM_ADMIN and user.is_active
    will_be_admin = (changes.get("role_key", user.role_key) == FIRM_ADMIN) and changes.get(
        "is_active", user.is_active
    )
    if was_admin and not will_be_admin and await _active_admin_count(session, user.firm_id) <= 1:
        raise ConflictError("The firm must keep at least one active Firm Admin")

    before = {k: getattr(user, k) for k in changes}
    for key, value in changes.items():
        if value is not None:
            setattr(user, key, value)
    deactivated = "is_active" in changes and changes["is_active"] is False
    role_changed = "role_key" in changes and changes["role_key"] != before["role_key"]
    if deactivated:
        await revoke_all_sessions(session, user.id)
    record_audit(
        session,
        action="user.deactivated" if deactivated else "user.updated",
        actor=principal,
        target_type="user",
        target_id=user.id,
        metadata={"before": before, "after": {k: getattr(user, k) for k in changes}},
    )
    if role_changed:
        record_audit(
            session,
            action="user.role_changed",
            actor=principal,
            target_type="user",
            target_id=user.id,
            metadata={"from": before["role_key"], "to": user.role_key},
        )
    await session.commit()
    return await _get_user(session, principal, user.id)
