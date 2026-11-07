"""Users, periods, audit trail, database constraints and migration integrity."""

import subprocess
import sys
import uuid

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import PERMISSIONS, ROLES
from app.models import AuditEvent
from app.services.audit import sanitize_metadata
from tests.conftest import ACCOUNTANT, BACKEND_DIR, CA_REVIEWER, FIRM_ADMIN, PASSWORD, World, login

API = "/api/v1"
PERIOD = {"label": "FY2025", "start_date": "2025-01-01", "end_date": "2025-12-31"}


# ----------------------------------------------------------------------------- users


async def test_admin_creates_user_in_own_firm_and_new_user_can_log_in(
    api: httpx.AsyncClient, world: World
) -> None:
    firm = await world.firm()
    hdr = await login(api, await world.user(firm, FIRM_ADMIN))
    body = {
        "email": "New.Person@Example.com",
        "full_name": "New Person",
        "role_key": ACCOUNTANT,
        "password": PASSWORD,
    }
    r = await api.post(f"{API}/users", json=body, headers=hdr)
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "new.person@example.com"
    assert "password" not in r.text
    login_resp = await api.post(
        f"{API}/auth/login", json={"email": "new.person@example.com", "password": PASSWORD}
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["user"]["firm_id"] == str(firm.id)
    # duplicate (case-insensitive)
    assert (await api.post(f"{API}/users", json=body, headers=hdr)).status_code == 409


async def test_user_management_requires_permission(api: httpx.AsyncClient, world: World) -> None:
    firm = await world.firm()
    reviewer = await world.user(firm, CA_REVIEWER)
    hdr = await login(api, reviewer)
    body = {
        "email": "x@example.com",
        "full_name": "X",
        "role_key": ACCOUNTANT,
        "password": PASSWORD,
    }
    assert (await api.post(f"{API}/users", json=body, headers=hdr)).status_code == 403
    assert (
        await api.patch(f"{API}/users/{reviewer.id}", json={"role_key": FIRM_ADMIN}, headers=hdr)
    ).status_code == 403


async def test_create_user_validates_role_and_password(
    api: httpx.AsyncClient, world: World
) -> None:
    hdr = await login(api, await world.user(await world.firm(), FIRM_ADMIN))
    base = {
        "email": "y@example.com",
        "full_name": "Y",
        "role_key": ACCOUNTANT,
        "password": PASSWORD,
    }
    assert (
        await api.post(f"{API}/users", json={**base, "role_key": "root"}, headers=hdr)
    ).status_code == 422
    assert (
        await api.post(f"{API}/users", json={**base, "password": "short"}, headers=hdr)
    ).status_code == 422
    assert (
        await api.post(f"{API}/users", json={**base, "password": "aaaaaaaaaaaaaaaa"}, headers=hdr)
    ).status_code == 422


async def test_firm_must_keep_one_active_admin(api: httpx.AsyncClient, world: World) -> None:
    firm = await world.firm()
    only_admin = await world.user(firm, FIRM_ADMIN)
    hdr = await login(api, only_admin)
    for change in ({"is_active": False}, {"role_key": ACCOUNTANT}):
        assert (
            await api.patch(f"{API}/users/{only_admin.id}", json=change, headers=hdr)
        ).status_code == 409


async def test_roles_endpoint_lists_the_four_system_roles(
    api: httpx.AsyncClient, world: World
) -> None:
    hdr = await login(api, await world.user(await world.firm(), ACCOUNTANT))
    roles = {r["key"] for r in (await api.get(f"{API}/roles", headers=hdr)).json()}
    assert roles == {"firm_admin", "ca_reviewer", "accountant", "client_user"}


# ----------------------------------------------------------------------------- periods


async def test_period_lifecycle_and_permissions(api: httpx.AsyncClient, world: World) -> None:
    firm = await world.firm()
    reviewer, acc = await world.user(firm, CA_REVIEWER), await world.user(firm, ACCOUNTANT)
    c = await world.client(firm)
    await world.assign(reviewer, c)
    await world.assign(acc, c)
    rev_hdr, acc_hdr = await login(api, reviewer), await login(api, acc)

    p = await api.post(f"{API}/clients/{c.id}/periods", json=PERIOD, headers=acc_hdr)
    assert p.status_code == 201 and p.json()["status"] == "open"
    pid = p.json()["id"]
    base = f"{API}/clients/{c.id}/periods/{pid}"

    assert (
        await api.post(f"{base}/close", headers=acc_hdr)
    ).status_code == 403  # staff cannot close
    closed = await api.post(f"{base}/close", headers=rev_hdr)
    assert (
        closed.status_code == 200
        and closed.json()["status"] == "closed"
        and closed.json()["closed_at"]
    )
    assert (await api.post(f"{base}/close", headers=rev_hdr)).status_code == 409
    assert (
        await api.patch(base, json={"label": "renamed"}, headers=rev_hdr)
    ).status_code == 409  # closed => frozen
    assert (await api.post(f"{base}/reopen", headers=acc_hdr)).status_code == 403
    assert (await api.post(f"{base}/reopen", headers=rev_hdr)).json()["status"] == "open"
    assert (await api.patch(base, json={"label": "FY25 final"}, headers=rev_hdr)).json()[
        "label"
    ] == "FY25 final"


async def test_overlapping_and_duplicate_periods_are_rejected_per_client_only(
    api: httpx.AsyncClient, world: World
) -> None:
    firm = await world.firm()
    admin = await world.user(firm, FIRM_ADMIN)
    c1, c2 = await world.client(firm), await world.client(firm)
    hdr = await login(api, admin)
    assert (
        await api.post(f"{API}/clients/{c1.id}/periods", json=PERIOD, headers=hdr)
    ).status_code == 201
    overlap = {"label": "H2", "start_date": "2025-07-01", "end_date": "2026-06-30"}
    assert (
        await api.post(f"{API}/clients/{c1.id}/periods", json=overlap, headers=hdr)
    ).status_code == 409
    dup_label = {**PERIOD, "start_date": "2026-01-01", "end_date": "2026-12-31"}
    assert (
        await api.post(f"{API}/clients/{c1.id}/periods", json=dup_label, headers=hdr)
    ).status_code == 409
    adjacent = {"label": "FY2026", "start_date": "2026-01-01", "end_date": "2026-12-31"}
    assert (
        await api.post(f"{API}/clients/{c1.id}/periods", json=adjacent, headers=hdr)
    ).status_code == 201
    # Same dates for a DIFFERENT client are fine.
    assert (
        await api.post(f"{API}/clients/{c2.id}/periods", json=PERIOD, headers=hdr)
    ).status_code == 201


async def test_period_date_order_and_archived_client(api: httpx.AsyncClient, world: World) -> None:
    firm = await world.firm()
    hdr = await login(api, await world.user(firm, FIRM_ADMIN))
    c = await world.client(firm)
    bad = {"label": "bad", "start_date": "2025-12-31", "end_date": "2025-01-01"}
    assert (
        await api.post(f"{API}/clients/{c.id}/periods", json=bad, headers=hdr)
    ).status_code == 422
    assert (
        await api.patch(f"{API}/clients/{c.id}", json={"status": "archived"}, headers=hdr)
    ).status_code == 200
    assert (
        await api.post(f"{API}/clients/{c.id}/periods", json=PERIOD, headers=hdr)
    ).status_code == 409


async def test_client_validation_search_and_pagination(
    api: httpx.AsyncClient, world: World
) -> None:
    firm = await world.firm()
    hdr = await login(api, await world.user(firm, FIRM_ADMIN))
    for i in range(3):
        r = await api.post(
            f"{API}/clients",
            json={"code": f"P{i}", "name": f"Pager {i}", "base_currency": "USD"},
            headers=hdr,
        )
        assert r.status_code == 201
    page = (await api.get(f"{API}/clients?limit=2&offset=0", headers=hdr)).json()
    assert page["total"] == 3 and len(page["items"]) == 2 and page["limit"] == 2
    assert (await api.get(f"{API}/clients?q=pager 1", headers=hdr)).json()["total"] == 1
    assert (await api.get(f"{API}/clients?q=%25", headers=hdr)).json()[
        "total"
    ] == 0  # LIKE wildcards escaped
    assert (await api.get(f"{API}/clients?limit=1000", headers=hdr)).status_code == 422
    for bad in (
        {"code": "x y", "name": "n", "base_currency": "USD"},
        {"code": "ok", "name": "n", "base_currency": "usd"},
    ):
        assert (await api.post(f"{API}/clients", json=bad, headers=hdr)).status_code == 422


# ----------------------------------------------------------------------------- audit


async def test_sensitive_actions_are_audited_with_actor_target_and_metadata(
    api: httpx.AsyncClient, world: World
) -> None:
    firm = await world.firm()
    admin, acc = await world.user(firm, FIRM_ADMIN), await world.user(firm, ACCOUNTANT)
    hdr = await login(api, admin)
    cid = (
        await api.post(
            f"{API}/clients",
            json={"code": "AUD", "name": "Audited", "base_currency": "PKR"},
            headers=hdr,
        )
    ).json()["id"]
    await api.post(f"{API}/clients/{cid}/access", json={"user_id": str(acc.id)}, headers=hdr)
    pid = (await api.post(f"{API}/clients/{cid}/periods", json=PERIOD, headers=hdr)).json()["id"]
    await api.post(f"{API}/clients/{cid}/periods/{pid}/close", headers=hdr)
    await api.patch(f"{API}/users/{acc.id}", json={"role_key": CA_REVIEWER}, headers=hdr)
    await api.delete(f"{API}/clients/{cid}/access/{acc.id}", headers=hdr)

    events = (await api.get(f"{API}/audit-events?limit=200", headers=hdr)).json()["items"]
    actions = {e["action"] for e in events}
    assert {
        "auth.login",
        "client.created",
        "client_access.granted",
        "period.created",
        "period.closed",
        "user.role_changed",
        "client_access.revoked",
    } <= actions
    granted = next(e for e in events if e["action"] == "client_access.granted")
    assert granted["actor_user_id"] == str(admin.id) and granted["actor_email"] == admin.email
    assert granted["target_type"] == "user" and granted["target_id"] == str(acc.id)
    assert granted["client_id"] == cid and granted["created_at"] and granted["request_id"]
    role_evt = next(e for e in events if e["action"] == "user.role_changed")
    assert role_evt["metadata"] == {"from": ACCOUNTANT, "to": CA_REVIEWER}
    # filters
    only = (await api.get(f"{API}/audit-events?action=period.closed", headers=hdr)).json()
    assert only["total"] == 1 and only["items"][0]["target_id"] == pid


async def test_failed_action_leaves_no_audit_event(
    api: httpx.AsyncClient, world: World, db: AsyncSession
) -> None:
    firm = await world.firm()
    hdr = await login(api, await world.user(firm, FIRM_ADMIN))
    body = {"code": "DUP", "name": "Dup", "base_currency": "PKR"}
    await api.post(f"{API}/clients", json=body, headers=hdr)
    await api.post(f"{API}/clients", json=body, headers=hdr)  # 409
    n = len(
        (
            await db.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "client.created", AuditEvent.firm_id == firm.id
                )
            )
        ).all()
    )
    assert n == 1


def test_audit_metadata_never_contains_credentials() -> None:
    clean = sanitize_metadata(
        {
            "email": "a@b.c",
            "password": "p",
            "new_password": "p",
            "access_token": "t",
            "nested": {"api_key": "k", "ok": 1},
            "id": uuid.UUID(int=1),
        }
    )
    assert clean == {"email": "a@b.c", "nested": {"ok": 1}, "id": str(uuid.UUID(int=1))}


async def test_audit_trail_is_append_only_at_the_database_level(
    world: World, db: AsyncSession
) -> None:
    firm = await world.firm()
    await world.user(firm, FIRM_ADMIN)
    db.add(AuditEvent(firm_id=firm.id, action="test.event"))
    await db.commit()
    for stmt in (
        "UPDATE audit_events SET action = 'tampered' WHERE action = 'test.event'",
        "DELETE FROM audit_events WHERE action = 'test.event'",
        "TRUNCATE audit_events",
    ):
        with pytest.raises((DBAPIError, IntegrityError), match="append-only"):
            await db.execute(text(stmt))
        await db.rollback()


# ----------------------------------------------------------------------------- database integrity


async def test_database_rejects_cross_firm_rows_even_if_application_code_is_bypassed(
    world: World, db: AsyncSession
) -> None:
    """Composite FKs: a row whose firm differs from its parent's firm cannot exist."""
    firm_a, firm_b = await world.firm("Alpha"), await world.firm("Beta")
    client_a = await world.client(firm_a)
    user_b = await world.user(firm_b, ACCOUNTANT)

    with pytest.raises(IntegrityError, match="fk_accounting_periods_client_firm_clients"):
        await db.execute(
            text(
                "INSERT INTO accounting_periods (firm_id, client_id, label, start_date, end_date) "
                "VALUES (:f, :c, 'x', '2025-01-01', '2025-12-31')"
            ),
            {"f": firm_b.id, "c": client_a.id},
        )
    await db.rollback()
    with pytest.raises(IntegrityError, match="fk_user_client_access"):
        await db.execute(
            text(
                "INSERT INTO user_client_access (user_id, client_id, firm_id) VALUES (:u, :c, :f)"
            ),
            {"u": user_b.id, "c": client_a.id, "f": firm_a.id},
        )
    await db.rollback()


async def test_seeded_roles_and_permissions_match_the_code_catalog(db: AsyncSession) -> None:
    perms = dict((await db.execute(text("SELECT key, description FROM permissions"))).all())
    assert perms == PERMISSIONS
    rows = (await db.execute(text("SELECT role_key, permission_key FROM role_permissions"))).all()
    by_role: dict[str, set[str]] = {}
    for role, perm in rows:
        by_role.setdefault(role, set()).add(perm)
    assert by_role == {k: set(v[2]) for k, v in ROLES.items()}
    names = dict((await db.execute(text("SELECT key, name FROM roles"))).all())
    assert names == {k: v[0] for k, v in ROLES.items()}


async def test_no_ledger_or_bookkeeping_tables_exist(db: AsyncSession) -> None:
    tables = {
        r[0]
        for r in (
            await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        ).all()
    }
    assert tables == {
        "documents",
        "outbox_events",
        "firms",
        "users",
        "roles",
        "permissions",
        "role_permissions",
        "clients",
        "accounting_periods",
        "user_client_access",
        "refresh_tokens",
        "audit_events",
        "alembic_version",
    }
    assert not any(w in t for t in tables for w in ("ledger", "journal", "posting", "transaction"))


def test_models_and_migrations_have_not_drifted(migrated_db_url: str) -> None:
    """`alembic check` fails if the ORM models differ from what the migrations create."""
    import os

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "check"],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": migrated_db_url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


async def test_bootstrap_cli_creates_firm_and_admin_who_can_log_in(
    api: httpx.AsyncClient,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[no-untyped-def]
) -> None:
    from app import cli

    monkeypatch.setattr(cli, "get_sessionmaker", lambda: session_factory)

    class _E:
        async def dispose(self) -> None: ...

    monkeypatch.setattr(cli, "get_engine", lambda: _E())
    slug = f"cli-{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    await cli.bootstrap_firm(
        firm_name="CLI Firm", slug=slug, admin_email=email, admin_name="Root", password=PASSWORD
    )
    r = await api.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200 and r.json()["user"]["role"] == FIRM_ADMIN
    with pytest.raises(SystemExit):  # same slug again
        await cli.bootstrap_firm(
            firm_name="CLI Firm",
            slug=slug,
            admin_email="o@example.com",
            admin_name="R",
            password=PASSWORD,
        )
    with pytest.raises(SystemExit):  # weak password path
        await cli.bootstrap_firm(
            firm_name="F",
            slug=f"{slug}-2",
            admin_email="z@example.com",
            admin_name="R",
            password="short",
        )
