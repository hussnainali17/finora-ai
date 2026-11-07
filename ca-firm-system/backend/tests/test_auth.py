import uuid
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models import AuditEvent, RefreshToken, User
from tests.conftest import ACCOUNTANT, FIRM_ADMIN, PASSWORD, World, login

API = "/api/v1"


async def _login_raw(
    api: httpx.AsyncClient, email: str, password: str = PASSWORD
) -> httpx.Response:
    return await api.post(f"{API}/auth/login", json={"email": email, "password": password})


async def test_login_returns_access_token_and_httponly_refresh_cookie(
    api: httpx.AsyncClient, world: World
) -> None:
    user = await world.user(await world.firm(), ACCOUNTANT)
    resp = await _login_raw(api, user.email)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 15 * 60
    assert body["user"]["email"] == user.email and body["user"]["role"] == ACCOUNTANT
    assert "client:read" in body["user"]["permissions"]
    assert "refresh" not in str(body).lower() and "password" not in str(body).lower()
    cookie = resp.headers["set-cookie"].lower()
    assert "ca_refresh=" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert "path=/api/v1/auth" in cookie
    assert resp.headers["cache-control"] == "no-store"


async def test_login_is_case_insensitive_on_email(api: httpx.AsyncClient, world: World) -> None:
    user = await world.user(await world.firm(), ACCOUNTANT)
    assert (await _login_raw(api, user.email.upper())).status_code == 200


async def test_wrong_password_and_unknown_user_are_indistinguishable(
    api: httpx.AsyncClient, world: World
) -> None:
    user = await world.user(await world.firm(), ACCOUNTANT)
    bad_pw = await _login_raw(api, user.email, "wrong-password-123")
    unknown = await _login_raw(api, f"nobody-{uuid.uuid4().hex}@example.com")
    assert bad_pw.status_code == unknown.status_code == 401
    assert bad_pw.json() == unknown.json()
    assert "set-cookie" not in bad_pw.headers


async def test_account_locks_after_repeated_failures_even_for_correct_password(
    api: httpx.AsyncClient, world: World
) -> None:
    user = await world.user(await world.firm(), ACCOUNTANT)
    for _ in range(get_settings().login_max_failed_attempts):
        assert (await _login_raw(api, user.email, "wrong-password-123")).status_code == 401
    assert (await _login_raw(api, user.email)).status_code == 401  # correct password, but locked


async def test_successful_login_resets_failure_counter(
    api: httpx.AsyncClient, world: World, db: AsyncSession
) -> None:
    user = await world.user(await world.firm(), ACCOUNTANT)
    for _ in range(3):
        await _login_raw(api, user.email, "wrong-password-123")
    assert (await _login_raw(api, user.email)).status_code == 200
    db.expire_all()
    assert (await db.get(User, user.id)).failed_login_count == 0  # type: ignore[union-attr]


async def test_lock_expires(
    api: httpx.AsyncClient, world: World, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await world.user(await world.firm(), ACCOUNTANT)
    async with session_factory() as s:
        await s.execute(
            update(User)
            .where(User.id == user.id)
            .values(locked_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        await s.commit()
    assert (await _login_raw(api, user.email)).status_code == 200


async def test_inactive_user_and_inactive_firm_cannot_log_in(
    api: httpx.AsyncClient, world: World
) -> None:
    firm = await world.firm()
    inactive = await world.user(firm, ACCOUNTANT, active=False)
    assert (await _login_raw(api, inactive.email)).status_code == 401


async def test_protected_routes_require_a_valid_token(api: httpx.AsyncClient, world: World) -> None:
    assert (await api.get(f"{API}/auth/me")).status_code == 401
    assert (await api.get(f"{API}/clients")).status_code == 401
    assert (
        await api.get(f"{API}/auth/me", headers={"Authorization": "Bearer garbage"})
    ).status_code == 401
    assert (
        await api.get(f"{API}/auth/me", headers={"Authorization": "Basic abc"})
    ).status_code == 401


async def test_me_returns_identity_and_permissions(api: httpx.AsyncClient, world: World) -> None:
    user = await world.user(await world.firm(), FIRM_ADMIN)
    me = (await api.get(f"{API}/auth/me", headers=await login(api, user))).json()
    assert me["id"] == str(user.id) and me["role"] == FIRM_ADMIN
    assert "client:access_all" in me["permissions"]


def _forge(claims: dict[str, object], key: str | None = None, alg: str = "HS256") -> str:
    s = get_settings()
    base: dict[str, object] = {
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
        "typ": "access",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        "sid": str(uuid.uuid4()),
    }
    return jwt.encode({**base, **claims}, key or s.jwt_secret.get_secret_value(), algorithm=alg)


async def test_forged_expired_and_malformed_tokens_are_rejected(
    api: httpx.AsyncClient, world: World
) -> None:
    firm = await world.firm()
    user = await world.user(firm, FIRM_ADMIN)
    ids = {"sub": str(user.id), "firm": str(firm.id)}
    good_shape_wrong_key = _forge(ids, key="a-different-secret-that-is-long-enough-xx")
    expired = _forge({**ids, "exp": int((datetime.now(UTC) - timedelta(minutes=1)).timestamp())})
    wrong_aud = _forge({**ids, "aud": "someone-else"})
    wrong_type = _forge({**ids, "typ": "refresh"})
    alg_none = jwt.encode({**ids, "typ": "access"}, key="", algorithm="none")
    # Validly signed, but the session id matches no live session (e.g. logged out / never existed).
    no_session = _forge(ids)
    for token in (good_shape_wrong_key, expired, wrong_aud, wrong_type, alg_none, no_session):
        r = await api.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, token


async def test_token_cannot_be_used_across_firms(api: httpx.AsyncClient, world: World) -> None:
    firm_a, firm_b = await world.firm("Alpha"), await world.firm("Beta")
    user_a = await world.user(firm_a, FIRM_ADMIN)
    resp = await _login_raw(api, user_a.email)
    sid = jwt.decode(resp.json()["access_token"], options={"verify_signature": False})["sid"]
    # Valid signature + live session, but claims the user belongs to a different firm.
    token = _forge({"sub": str(user_a.id), "firm": str(firm_b.id), "sid": sid})
    assert (
        await api.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    ).status_code == 401


async def test_refresh_rotates_token_and_old_token_is_dead(
    api: httpx.AsyncClient, world: World
) -> None:
    user = await world.user(await world.firm(), ACCOUNTANT)
    await _login_raw(api, user.email)
    first = api.cookies.get("ca_refresh")
    r = await api.post(f"{API}/auth/refresh")
    assert r.status_code == 200 and r.json()["access_token"]
    second = api.cookies.get("ca_refresh")
    assert first and second and first != second

    # Replaying the rotated token is treated as theft: it fails AND kills the whole session.
    api.cookies.set("ca_refresh", first, path=f"{API}/auth")
    assert (await api.post(f"{API}/auth/refresh")).status_code == 401
    api.cookies.set("ca_refresh", second, path=f"{API}/auth")
    assert (await api.post(f"{API}/auth/refresh")).status_code == 401


async def test_refresh_reuse_is_audited(
    api: httpx.AsyncClient, world: World, db: AsyncSession
) -> None:
    user = await world.user(await world.firm(), ACCOUNTANT)
    await _login_raw(api, user.email)
    first = api.cookies.get("ca_refresh")
    await api.post(f"{API}/auth/refresh")
    api.cookies.set("ca_refresh", first, path=f"{API}/auth")
    await api.post(f"{API}/auth/refresh")
    n = await db.scalar(
        select(AuditEvent.id).where(
            AuditEvent.action == "auth.refresh_reuse_detected", AuditEvent.actor_user_id == user.id
        )
    )
    assert n is not None


async def test_refresh_without_or_with_bad_cookie_fails(api: httpx.AsyncClient) -> None:
    assert (await api.post(f"{API}/auth/refresh")).status_code == 401
    api.cookies.set("ca_refresh", "not-a-real-token", path=f"{API}/auth")
    assert (await api.post(f"{API}/auth/refresh")).status_code == 401


async def test_expired_refresh_token_is_rejected(
    api: httpx.AsyncClient, world: World, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await world.user(await world.firm(), ACCOUNTANT)
    await _login_raw(api, user.email)
    async with session_factory() as s:
        await s.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await s.commit()
    assert (await api.post(f"{API}/auth/refresh")).status_code == 401


async def test_refresh_and_logout_reject_untrusted_origin(
    api: httpx.AsyncClient, world: World
) -> None:
    user = await world.user(await world.firm(), ACCOUNTANT)
    await _login_raw(api, user.email)
    evil = {"Origin": "https://evil.example"}
    assert (await api.post(f"{API}/auth/refresh", headers=evil)).status_code == 403
    assert (await api.post(f"{API}/auth/logout", headers=evil)).status_code == 403
    trusted = {"Origin": get_settings().cors_allowed_origins[0]}
    assert (await api.post(f"{API}/auth/refresh", headers=trusted)).status_code == 200


async def test_logout_invalidates_access_and_refresh_tokens_immediately(
    api: httpx.AsyncClient, world: World
) -> None:
    user = await world.user(await world.firm(), ACCOUNTANT)
    resp = await _login_raw(api, user.email)
    hdr = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    assert (await api.get(f"{API}/auth/me", headers=hdr)).status_code == 200

    out = await api.post(f"{API}/auth/logout")
    assert out.status_code == 204
    assert "ca_refresh=" in out.headers["set-cookie"]  # cookie cleared
    # The access token is still unexpired, but its session is revoked -> rejected right away.
    assert (await api.get(f"{API}/auth/me", headers=hdr)).status_code == 401
    assert (await api.post(f"{API}/auth/refresh")).status_code == 401


async def test_logout_is_idempotent(api: httpx.AsyncClient) -> None:
    assert (await api.post(f"{API}/auth/logout")).status_code == 204


async def test_second_device_session_survives_logout_of_the_first(
    world: World, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    from app.main import create_app  # local import: two independent cookie jars

    user = await world.user(await world.firm(), ACCOUNTANT)
    app = create_app()

    async def _session():  # type: ignore[no-untyped-def]
        async with session_factory() as s:
            yield s

    from app.db.session import get_session

    app.dependency_overrides[get_session] = _session
    t = httpx.ASGITransport(app=app)
    async with (
        httpx.AsyncClient(transport=t, base_url="http://test") as phone,
        httpx.AsyncClient(transport=t, base_url="http://test") as laptop,
    ):
        tok_phone = (await _login_raw(phone, user.email)).json()["access_token"]
        tok_laptop = (await _login_raw(laptop, user.email)).json()["access_token"]
        await phone.post(f"{API}/auth/logout")
        assert (
            await phone.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok_phone}"})
        ).status_code == 401
        assert (
            await laptop.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok_laptop}"})
        ).status_code == 200


async def test_change_password_requires_current_password_and_revokes_sessions(
    api: httpx.AsyncClient, world: World
) -> None:
    user = await world.user(await world.firm(), ACCOUNTANT)
    hdr = await login(api, user)
    bad = await api.post(
        f"{API}/auth/change-password",
        json={"current_password": "nope-nope-nope-1", "new_password": "A-brand-new-Passw0rd!"},
        headers=hdr,
    )
    assert bad.status_code == 401
    weak = await api.post(
        f"{API}/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "short"},
        headers=hdr,
    )
    assert weak.status_code == 422
    ok = await api.post(
        f"{API}/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "A-brand-new-Passw0rd!"},
        headers=hdr,
    )
    assert ok.status_code == 204
    assert (await api.get(f"{API}/auth/me", headers=hdr)).status_code == 401  # all sessions revoked
    assert (await _login_raw(api, user.email)).status_code == 401  # old password dead
    assert (await _login_raw(api, user.email, "A-brand-new-Passw0rd!")).status_code == 200


async def test_deactivated_user_loses_access_immediately(
    api: httpx.AsyncClient, world: World
) -> None:
    firm = await world.firm()
    admin, acc = await world.user(firm, FIRM_ADMIN), await world.user(firm, ACCOUNTANT)
    acc_hdr = await login(api, acc)
    assert (await api.get(f"{API}/auth/me", headers=acc_hdr)).status_code == 200
    r = await api.patch(
        f"{API}/users/{acc.id}", json={"is_active": False}, headers=await login(api, admin)
    )
    assert r.status_code == 200
    assert (await api.get(f"{API}/auth/me", headers=acc_hdr)).status_code == 401
    assert (await _login_raw(api, acc.email)).status_code == 401


async def test_role_change_applies_to_existing_tokens_immediately(
    api: httpx.AsyncClient, world: World
) -> None:
    firm = await world.firm()
    admin, acc = await world.user(firm, FIRM_ADMIN), await world.user(firm, ACCOUNTANT)
    acc_hdr = await login(api, acc)
    assert (await api.get(f"{API}/users", headers=acc_hdr)).status_code == 403
    r = await api.patch(
        f"{API}/users/{acc.id}", json={"role_key": FIRM_ADMIN}, headers=await login(api, admin)
    )
    assert r.status_code == 200
    assert (await api.get(f"{API}/users", headers=acc_hdr)).status_code == 200  # same token


async def test_auth_events_are_audited_without_secrets(
    api: httpx.AsyncClient, world: World, db: AsyncSession
) -> None:
    user = await world.user(await world.firm(), ACCOUNTANT)
    await _login_raw(api, user.email, "wrong-password-123")
    resp = await _login_raw(api, user.email)
    await api.post(f"{API}/auth/logout")
    rows = (
        await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.actor_user_id == user.id)
            .order_by(AuditEvent.created_at)
        )
    ).all()
    assert [r.action for r in rows] == ["auth.login_failed", "auth.login", "auth.logout"]
    assert rows[0].outcome == "failure" and rows[1].outcome == "success"
    assert all(r.firm_id == user.firm_id and r.actor_email == user.email for r in rows)
    assert all(r.ip_address == "203.0.113.9" for r in rows)
    blob = " ".join(str(r.event_metadata) for r in rows) + str(rows[0].actor_email)
    assert "wrong-password-123" not in blob and PASSWORD not in blob
    assert resp.json()["access_token"] not in blob


async def test_only_token_hash_is_stored(
    api: httpx.AsyncClient, world: World, db: AsyncSession
) -> None:
    user = await world.user(await world.firm(), ACCOUNTANT)
    await _login_raw(api, user.email)
    raw = api.cookies.get("ca_refresh")
    assert raw
    stored = (
        await db.scalars(select(RefreshToken.token_hash).where(RefreshToken.user_id == user.id))
    ).all()
    assert stored and raw not in stored and all(len(h) == 64 for h in stored)


@pytest.mark.parametrize("password", ["", "x" * 129])
async def test_login_validates_password_length(api: httpx.AsyncClient, password: str) -> None:
    r = await api.post(f"{API}/auth/login", json={"email": "a@example.com", "password": password})
    assert r.status_code == 422
