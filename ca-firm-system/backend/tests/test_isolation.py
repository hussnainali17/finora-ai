"""Tenant (firm) and client isolation. These are the Phase 1 acceptance tests:
one client - or one firm - must never be able to reach another's records."""

import uuid

import httpx

from tests.conftest import ACCOUNTANT, CA_REVIEWER, CLIENT_USER, FIRM_ADMIN, World, login

API = "/api/v1"
PERIOD = {"label": "FY2025", "start_date": "2025-01-01", "end_date": "2025-12-31"}


async def _period(api: httpx.AsyncClient, hdr: dict[str, str], client_id: uuid.UUID) -> str:
    r = await api.post(f"{API}/clients/{client_id}/periods", json=PERIOD, headers=hdr)
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


# ------------------------------------------------------------------ client-level isolation


async def test_user_cannot_access_a_client_they_are_not_assigned_to(
    api: httpx.AsyncClient, world: World
) -> None:
    firm = await world.firm()
    acc = await world.user(firm, ACCOUNTANT)
    mine, other = await world.client(firm, "Mine"), await world.client(firm, "Other")
    await world.assign(acc, mine)
    hdr = await login(api, acc)

    assert (await api.get(f"{API}/clients/{mine.id}", headers=hdr)).status_code == 200
    # Not-assigned client: indistinguishable from "does not exist".
    denied = await api.get(f"{API}/clients/{other.id}", headers=hdr)
    missing = await api.get(f"{API}/clients/{uuid.uuid4()}", headers=hdr)
    assert denied.status_code == missing.status_code == 404
    assert denied.json() == missing.json()


async def test_client_list_is_limited_to_assigned_clients(
    api: httpx.AsyncClient, world: World
) -> None:
    firm = await world.firm()
    acc = await world.user(firm, ACCOUNTANT)
    mine, other = await world.client(firm, "Mine"), await world.client(firm, "Other")
    await world.assign(acc, mine)

    items = (await api.get(f"{API}/clients", headers=await login(api, acc))).json()
    assert [c["id"] for c in items["items"]] == [str(mine.id)]
    assert items["total"] == 1
    assert str(other.id) not in str(items)


async def test_unassigned_user_cannot_read_modify_or_create_under_other_client(
    api: httpx.AsyncClient, world: World
) -> None:
    firm = await world.firm()
    admin = await world.user(firm, FIRM_ADMIN)
    # A reviewer HAS client:update / period:close permissions, but is not assigned to this client.
    acc = await world.user(firm, CA_REVIEWER)
    secret = await world.client(firm, "Secret")
    period_id = await _period(api, await login(api, admin), secret.id)
    hdr = await login(api, acc)

    base = f"{API}/clients/{secret.id}"
    assert (await api.patch(base, json={"name": "x"}, headers=hdr)).status_code == 404
    assert (await api.get(f"{base}/periods", headers=hdr)).status_code == 404
    assert (await api.get(f"{base}/periods/{period_id}", headers=hdr)).status_code == 404
    assert (await api.post(f"{base}/periods", json=PERIOD, headers=hdr)).status_code == 404
    assert (
        await api.patch(f"{base}/periods/{period_id}", json={"label": "x"}, headers=hdr)
    ).status_code == 404
    assert (await api.post(f"{base}/periods/{period_id}/close", headers=hdr)).status_code == 404


async def test_period_cannot_be_reached_through_another_clients_path(
    api: httpx.AsyncClient, world: World
) -> None:
    """Pairing client A's id with client B's period id must not leak B's period."""
    firm = await world.firm()
    admin = await world.user(firm, FIRM_ADMIN)
    acc = await world.user(firm, ACCOUNTANT)
    a, b = await world.client(firm, "A"), await world.client(firm, "B")
    await world.assign(acc, a)
    b_period = await _period(api, await login(api, admin), b.id)

    r = await api.get(f"{API}/clients/{a.id}/periods/{b_period}", headers=await login(api, acc))
    assert r.status_code == 404


async def test_revoking_access_takes_effect_immediately(
    api: httpx.AsyncClient, world: World
) -> None:
    firm = await world.firm()
    admin, acc = await world.user(firm, FIRM_ADMIN), await world.user(firm, ACCOUNTANT)
    c = await world.client(firm)
    admin_hdr, acc_hdr = await login(api, admin), await login(api, acc)

    assert (await api.get(f"{API}/clients/{c.id}", headers=acc_hdr)).status_code == 404
    r = await api.post(
        f"{API}/clients/{c.id}/access", json={"user_id": str(acc.id)}, headers=admin_hdr
    )
    assert r.status_code == 201
    assert (
        await api.get(f"{API}/clients/{c.id}", headers=acc_hdr)
    ).status_code == 200  # same token
    r = await api.delete(f"{API}/clients/{c.id}/access/{acc.id}", headers=admin_hdr)
    assert r.status_code == 204
    assert (await api.get(f"{API}/clients/{c.id}", headers=acc_hdr)).status_code == 404


async def test_firm_admin_reaches_every_client_in_their_firm(
    api: httpx.AsyncClient, world: World
) -> None:
    firm = await world.firm()
    admin = await world.user(firm, FIRM_ADMIN)
    clients = [await world.client(firm) for _ in range(3)]
    hdr = await login(api, admin)
    listed = (await api.get(f"{API}/clients", headers=hdr)).json()
    assert {c["id"] for c in listed["items"]} == {str(c.id) for c in clients}


async def test_creator_automatically_gets_access_to_the_client_they_create(
    api: httpx.AsyncClient, world: World
) -> None:
    firm = await world.firm()
    reviewer = await world.user(firm, CA_REVIEWER)
    other_reviewer = await world.user(firm, CA_REVIEWER, label="b")
    hdr = await login(api, reviewer)
    r = await api.post(
        f"{API}/clients",
        json={"code": "NEW-1", "name": "New Co", "base_currency": "PKR"},
        headers=hdr,
    )
    assert r.status_code == 201
    cid = r.json()["id"]
    assert (await api.get(f"{API}/clients/{cid}", headers=hdr)).status_code == 200
    assert (
        await api.get(f"{API}/clients/{cid}", headers=await login(api, other_reviewer))
    ).status_code == 404


async def test_read_only_client_user_cannot_write(api: httpx.AsyncClient, world: World) -> None:
    firm = await world.firm()
    cu = await world.user(firm, CLIENT_USER)
    c = await world.client(firm)
    await world.assign(cu, c)
    hdr = await login(api, cu)
    assert (await api.get(f"{API}/clients/{c.id}", headers=hdr)).status_code == 200
    assert (await api.get(f"{API}/clients/{c.id}/periods", headers=hdr)).status_code == 200
    assert (
        await api.patch(f"{API}/clients/{c.id}", json={"name": "x"}, headers=hdr)
    ).status_code == 403
    assert (
        await api.post(f"{API}/clients/{c.id}/periods", json=PERIOD, headers=hdr)
    ).status_code == 403
    assert (
        await api.post(
            f"{API}/clients", json={"code": "Z", "name": "Z", "base_currency": "PKR"}, headers=hdr
        )
    ).status_code == 403
    assert (await api.get(f"{API}/users", headers=hdr)).status_code == 403
    assert (await api.get(f"{API}/audit-events", headers=hdr)).status_code == 403
    assert (await api.get(f"{API}/clients/{c.id}/access", headers=hdr)).status_code == 403


# ------------------------------------------------------------------ firm (tenant) isolation


async def test_firm_b_cannot_access_any_firm_a_record(api: httpx.AsyncClient, world: World) -> None:
    firm_a, firm_b = await world.firm("Alpha"), await world.firm("Beta")
    admin_a = await world.user(firm_a, FIRM_ADMIN)
    admin_b = await world.user(firm_b, FIRM_ADMIN)  # even a Firm Admin of ANOTHER firm
    client_a = await world.client(firm_a)
    hdr_a, hdr_b = await login(api, admin_a), await login(api, admin_b)
    period_a = await _period(api, hdr_a, client_a.id)

    base = f"{API}/clients/{client_a.id}"
    for method, url, kwargs in [
        ("GET", base, {}),
        ("PATCH", base, {"json": {"name": "pwned"}}),
        ("GET", f"{base}/periods", {}),
        ("GET", f"{base}/periods/{period_a}", {}),
        ("POST", f"{base}/periods", {"json": {**PERIOD, "label": "FY2026"}}),
        ("POST", f"{base}/periods/{period_a}/close", {}),
        ("GET", f"{base}/access", {}),
        ("POST", f"{base}/access", {"json": {"user_id": str(admin_b.id)}}),
    ]:
        r = await api.request(method, url, headers=hdr_b, **kwargs)  # type: ignore[arg-type]
        assert r.status_code == 404, f"{method} {url} -> {r.status_code} {r.text}"

    assert (await api.get(f"{API}/clients", headers=hdr_b)).json()["total"] == 0
    # ...and firm A's data is untouched.
    assert (await api.get(base, headers=hdr_a)).json()["name"] == client_a.name


async def test_user_directory_and_user_ids_are_firm_scoped(
    api: httpx.AsyncClient, world: World
) -> None:
    firm_a, firm_b = await world.firm("Alpha"), await world.firm("Beta")
    admin_a, admin_b = await world.user(firm_a, FIRM_ADMIN), await world.user(firm_b, FIRM_ADMIN)
    hdr_a = await login(api, admin_a)

    listed = (await api.get(f"{API}/users", headers=hdr_a)).json()["items"]
    assert str(admin_b.id) not in {u["id"] for u in listed}
    assert (await api.get(f"{API}/users/{admin_b.id}", headers=hdr_a)).status_code == 404
    assert (
        await api.patch(f"{API}/users/{admin_b.id}", json={"is_active": False}, headers=hdr_a)
    ).status_code == 404


async def test_cannot_assign_another_firms_user_to_a_client(
    api: httpx.AsyncClient, world: World
) -> None:
    firm_a, firm_b = await world.firm("Alpha"), await world.firm("Beta")
    admin_a = await world.user(firm_a, FIRM_ADMIN)
    outsider = await world.user(firm_b, ACCOUNTANT)
    c = await world.client(firm_a)
    r = await api.post(
        f"{API}/clients/{c.id}/access",
        json={"user_id": str(outsider.id)},
        headers=await login(api, admin_a),
    )
    assert r.status_code == 404
    # The outsider still sees nothing.
    assert (
        await api.get(f"{API}/clients/{c.id}", headers=await login(api, outsider))
    ).status_code == 404


async def test_same_client_code_allowed_in_different_firms(
    api: httpx.AsyncClient, world: World
) -> None:
    firm_a, firm_b = await world.firm("Alpha"), await world.firm("Beta")
    body = {"code": "ACME", "name": "Acme Ltd", "base_currency": "PKR"}
    for firm in (firm_a, firm_b):
        hdr = await login(api, await world.user(firm, FIRM_ADMIN))
        assert (await api.post(f"{API}/clients", json=body, headers=hdr)).status_code == 201
        assert (await api.post(f"{API}/clients", json=body, headers=hdr)).status_code == 409


async def test_firm_id_in_request_body_is_rejected_not_trusted(
    api: httpx.AsyncClient, world: World
) -> None:
    firm_a, firm_b = await world.firm("Alpha"), await world.firm("Beta")
    hdr = await login(api, await world.user(firm_a, FIRM_ADMIN))
    r = await api.post(
        f"{API}/clients",
        json={"code": "X", "name": "X", "base_currency": "PKR", "firm_id": str(firm_b.id)},
        headers=hdr,
    )
    assert r.status_code == 422  # extra="forbid": a caller can never choose the tenant


async def test_audit_trail_is_isolated_by_firm_and_by_client(
    api: httpx.AsyncClient, world: World
) -> None:
    firm_a, firm_b = await world.firm("Alpha"), await world.firm("Beta")
    admin_a, admin_b = await world.user(firm_a, FIRM_ADMIN), await world.user(firm_b, FIRM_ADMIN)
    reviewer = await world.user(firm_a, CA_REVIEWER)
    mine, other = await world.client(firm_a, "Mine"), await world.client(firm_a, "Other")
    await world.assign(reviewer, mine)
    hdr_admin = await login(api, admin_a)
    await _period(api, hdr_admin, mine.id)
    other_period = await _period(api, hdr_admin, other.id)

    # Firm B's admin sees none of firm A's events.
    b_events = (await api.get(f"{API}/audit-events", headers=await login(api, admin_b))).json()
    assert all(e["actor_user_id"] != str(admin_a.id) for e in b_events["items"])
    assert not any(e["client_id"] in (str(mine.id), str(other.id)) for e in b_events["items"])

    # A reviewer sees only events for clients assigned to them.
    items = (
        await api.get(f"{API}/audit-events?limit=200", headers=await login(api, reviewer))
    ).json()["items"]
    assert items, "reviewer should see events for their assigned client"
    assert {e["client_id"] for e in items} == {str(mine.id)}
    assert str(other_period) not in str(items)
    # Filtering by a client they cannot access yields nothing, not an error leak.
    r = await api.get(
        f"{API}/audit-events?client_id={other.id}", headers=await login(api, reviewer)
    )
    assert r.json()["total"] == 0
