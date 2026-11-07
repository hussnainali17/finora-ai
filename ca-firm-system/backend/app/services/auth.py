"""Login, refresh-token rotation, logout, password change and principal loading."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AuthenticationError
from app.core.security import (
    AccessClaims,
    burn_dummy_verification,
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    password_needs_rehash,
    validate_password_strength,
    verify_password,
)
from app.models import RefreshToken, User
from app.services.audit import record_audit
from app.services.authz import Principal

INVALID_CREDENTIALS = "Invalid email or password"


@dataclass(frozen=True)
class SessionTokens:
    access_token: str
    expires_in: int
    refresh_token: str
    user: User


def _now() -> datetime:
    return datetime.now(UTC)


async def _issue_tokens(
    session: AsyncSession, settings: Settings, user: User, family_id: uuid.UUID, now: datetime
) -> SessionTokens:
    raw, digest = new_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            family_id=family_id,
            token_hash=digest,
            expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    access, ttl = create_access_token(
        settings, user_id=user.id, firm_id=user.firm_id, session_id=family_id, now=now
    )
    return SessionTokens(access_token=access, expires_in=ttl, refresh_token=raw, user=user)


async def login(
    session: AsyncSession, settings: Settings, *, email: str, password: str
) -> SessionTokens:
    now = _now()
    normalized = email.strip().lower()
    user = await session.scalar(
        select(User).where(User.email == normalized).with_for_update(of=User)
    )

    async def fail(reason: str, *, lock: bool = False) -> AuthenticationError:
        record_audit(
            session,
            action="auth.login_failed",
            actor_user_id=user.id if user else None,
            actor_email=normalized[:320],
            firm_id=user.firm_id if user else None,
            target_type="user",
            target_id=user.id if user else None,
            outcome="failure",
            metadata={"reason": reason, "account_locked": lock},
        )
        await session.commit()  # persist failure counters + audit even though we raise
        return AuthenticationError(INVALID_CREDENTIALS)

    if user is None:
        burn_dummy_verification(password)
        raise await fail("unknown_user")
    if user.locked_until is not None and user.locked_until > now:
        burn_dummy_verification(password)
        raise await fail("account_locked")
    if not user.is_active or not user.firm.is_active:
        burn_dummy_verification(password)
        raise await fail("account_inactive")

    if not verify_password(user.password_hash, password):
        user.failed_login_count += 1
        locked = user.failed_login_count >= settings.login_max_failed_attempts
        if locked:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_login_count = 0
        raise await fail("bad_password", lock=locked)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    tokens = await _issue_tokens(session, settings, user, uuid.uuid4(), now)
    record_audit(
        session,
        action="auth.login",
        actor_user_id=user.id,
        actor_email=user.email,
        firm_id=user.firm_id,
        target_type="user",
        target_id=user.id,
    )
    await session.commit()
    return tokens


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID, now: datetime) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def refresh(session: AsyncSession, settings: Settings, *, raw_token: str) -> SessionTokens:
    now = _now()
    token = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw_token))
        .with_for_update()
    )
    if token is None:
        raise AuthenticationError("Invalid or expired session")
    user = await session.get(User, token.user_id)
    if token.revoked_at is not None:
        # A rotated token was replayed: assume theft and kill the whole session family.
        await _revoke_family(session, token.family_id, now)
        record_audit(
            session,
            action="auth.refresh_reuse_detected",
            actor_user_id=token.user_id,
            actor_email=user.email if user else None,
            firm_id=user.firm_id if user else None,
            outcome="failure",
            metadata={"session_id": token.family_id},
        )
        await session.commit()
        raise AuthenticationError("Invalid or expired session")
    if token.expires_at <= now or user is None or not user.is_active or not user.firm.is_active:
        await _revoke_family(session, token.family_id, now)
        await session.commit()
        raise AuthenticationError("Invalid or expired session")

    token.revoked_at = now
    tokens = await _issue_tokens(session, settings, user, token.family_id, now)
    await session.commit()
    return tokens


async def logout(session: AsyncSession, *, raw_token: str | None) -> None:
    """Idempotent. Revokes the whole session family so its access tokens stop working too."""
    if not raw_token:
        return
    now = _now()
    token = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
    )
    if token is None:
        return
    user = await session.get(User, token.user_id)
    await _revoke_family(session, token.family_id, now)
    record_audit(
        session,
        action="auth.logout",
        actor_user_id=token.user_id,
        actor_email=user.email if user else None,
        firm_id=user.firm_id if user else None,
        target_type="user",
        target_id=token.user_id,
    )
    await session.commit()


async def revoke_all_sessions(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Revokes every live refresh token for a user (caller commits)."""
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


async def change_password(
    session: AsyncSession, principal: Principal, *, current_password: str, new_password: str
) -> None:
    user = await session.get(User, principal.user_id)
    if user is None or not verify_password(user.password_hash, current_password):
        record_audit(
            session,
            action="auth.password_change_failed",
            actor=principal,
            target_type="user",
            target_id=principal.user_id,
            outcome="failure",
        )
        await session.commit()
        raise AuthenticationError("Current password is incorrect")
    validate_password_strength(new_password)
    user.password_hash = hash_password(new_password)
    await revoke_all_sessions(session, user.id)  # signs out every device, including this one
    record_audit(
        session,
        action="auth.password_changed",
        actor=principal,
        target_type="user",
        target_id=user.id,
    )
    await session.commit()


async def load_principal(session: AsyncSession, claims: AccessClaims) -> Principal:
    """Builds the Principal from the DATABASE (never from token claims) and verifies that the
    user, firm and session are all still valid."""
    now = _now()
    session_alive = exists().where(
        RefreshToken.family_id == claims.session_id,
        RefreshToken.user_id == claims.user_id,
        RefreshToken.revoked_at.is_(None),
        RefreshToken.expires_at > now,
    )
    user = await session.scalar(
        select(User).where(User.id == claims.user_id, User.firm_id == claims.firm_id, session_alive)
    )
    if user is None or not user.is_active or not user.firm.is_active:
        raise AuthenticationError("Invalid or expired token")
    return Principal(
        user_id=user.id,
        firm_id=user.firm_id,
        email=user.email,
        full_name=user.full_name,
        role_key=user.role_key,
        permissions=frozenset(rp.permission_key for rp in user.role.permissions),
        session_id=claims.session_id,
    )
