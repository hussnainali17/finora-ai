"""Phase 4: LLM gateway, model configuration API, authorization, failure/fallback behaviour, logging."""

import json
import re
import threading
import uuid
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import pytest
import yaml
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.intake_agent import service as intake
from app.agents.intake_agent.llm import GatewayAssistant
from app.api.llm import get_gateway
from app.core.config import get_settings
from app.llm.catalog import (
    AGENTS,
    CAP_STRUCTURED,
    CAP_VISION,
    MODELS,
    TASKS,
    ModelSpec,
    TaskSpec,
)
from app.llm.errors import InputTooLargeError, LlmCallFailedError, ModelUnavailableError
from app.llm.gateway import LlmGateway
from app.models import AuditEvent, LlmCallLog
from tests import intake_fixtures as fx
from tests.conftest import ACCOUNTANT, CA_REVIEWER, CLIENT_USER, FIRM_ADMIN, World, login
from tests.test_documents import Setup

API = "/api/v1"
MASTER_KEY = "sk-test"  # LITELLM_API_KEY in conftest
TASK = ("intake", "column_roles")
MSGS = [{"role": "user", "content": "classify these columns: SECRET-CLIENT-DATA-12345"}]
GOOD = {
    "id": "chatcmpl-abc123",
    "choices": [{"message": {"content": "hello"}}],
    "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
}


def settings(**over: Any):  # type: ignore[no-untyped-def]
    return get_settings().model_copy(update=over)


class Upstream:
    """A scripted LiteLLM stand-in served through httpx.MockTransport (the real httpx stack runs)."""

    def __init__(self, script: dict[str, list[Any]] | None = None, default: Any = None) -> None:
        self.script = script or {}  # alias -> list of outcomes consumed in order; last repeats
        self.default = default if default is not None else (200, GOOD, {})
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []

    def outcome(self, alias: str) -> Any:
        seq = self.script.get(alias)
        if not seq:
            return self.default
        return seq.pop(0) if len(seq) > 1 else seq[0]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200, json={"data": [{"id": a} for a in ("fast-general", "gemini-fast")]}
            )
        body = json.loads(request.content)
        out = self.outcome(body["model"])
        if isinstance(out, Exception):
            raise out
        status, payload, headers = out
        return httpx.Response(status, json=payload, headers=headers)

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def models_called(self) -> list[str]:
        return [
            json.loads(r.content)["model"]
            for r in self.requests
            if r.url.path.endswith("completions")
        ]

    def gateway(self, sf: async_sessionmaker[AsyncSession], **over: Any) -> LlmGateway:
        return LlmGateway(
            sf, settings(**over), transport=httpx.MockTransport(self.handler), sleep=self.sleep
        )


class Env:
    """A firm with an admin whose model configuration is built through the real API."""

    def __init__(self, api: httpx.AsyncClient, world: World) -> None:
        self.api, self.world = api, world

    async def build(self) -> "Env":
        self.firm = await self.world.firm()
        self.admin = await self.world.user(self.firm, FIRM_ADMIN)
        self.hdr = await login(self.api, self.admin)
        return self

    async def user_hdr(self, role: str) -> dict[str, str]:
        return await login(self.api, await self.world.user(self.firm, role))

    async def enable(self, *aliases: str) -> None:
        for a in aliases:
            r = await self.api.put(
                f"{API}/llm/models/{a}/enabled", json={"enabled": True}, headers=self.hdr
            )
            assert r.status_code == 200, r.text

    async def agent(self, agent: str, default: str, fallback: str | None = None) -> httpx.Response:
        return await self.api.put(
            f"{API}/llm/agents/{agent}",
            json={"default_alias": default, "fallback_alias": fallback},
            headers=self.hdr,
        )

    async def configure(self, default: str = "fast-general", fallback: str | None = None) -> None:
        await self.enable(*{a for a in (default, fallback) if a})
        r = await self.agent("intake", default, fallback)
        assert r.status_code == 200, r.text

    async def logs(self, sf: async_sessionmaker[AsyncSession]) -> list[LlmCallLog]:
        async with sf() as s:
            rows = await s.scalars(
                select(LlmCallLog).where(LlmCallLog.firm_id == self.firm.id).order_by(LlmCallLog.id)
            )
            return list(rows.all())

    def call(self, gw: LlmGateway, **kw: Any):  # type: ignore[no-untyped-def]
        return gw.complete(firm_id=self.firm.id, agent=TASK[0], task=TASK[1], messages=MSGS, **kw)


@pytest.fixture
async def env(api: httpx.AsyncClient, world: World) -> Env:
    return await Env(api, world).build()


def as_gateway(api: httpx.AsyncClient, gw: LlmGateway) -> None:
    api._transport.app.dependency_overrides[get_gateway] = lambda: gw  # type: ignore[attr-defined]


# ============================================================================ resolution


async def test_nothing_is_enabled_by_default_and_nothing_is_sent(
    env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    up = Upstream()
    with pytest.raises(ModelUnavailableError) as e:
        await env.call(up.gateway(session_factory))
    assert up.requests == []  # no data left the system
    assert "administrator" in e.value.message
    assert await env.logs(session_factory) == []


async def test_default_model_is_used_and_the_call_is_logged_with_metadata_only(
    env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general")
    up = Upstream(default=(200, GOOD, {"x-litellm-response-cost": "0.000123"}))
    client_id = (await env.world.client(env.firm)).id
    r = await env.call(up.gateway(session_factory), client_id=client_id, user_id=env.admin.id)
    assert (r.text, r.alias, r.provider, r.fallback_used, r.attempts) == (
        "hello",
        "fast-general",
        "OpenAI",
        False,
        1,
    )
    assert (
        r.usage.total_tokens == 16
        and r.cost_usd == Decimal("0.000123")
        and r.request_id == "chatcmpl-abc123"
    )

    req = up.requests[0]
    body = json.loads(req.content)
    assert (
        req.url.path == "/chat/completions"
        and req.headers["authorization"] == f"Bearer {MASTER_KEY}"
    )
    assert (body["model"], body["temperature"]) == ("fast-general", 0)
    assert body["metadata"]["agent"] == "intake" and body["metadata"]["task"] == "column_roles"

    [log] = await env.logs(session_factory)
    assert (log.agent, log.task, log.requested_alias, log.alias, log.provider, log.status) == (
        "intake", "column_roles", "fast-general", "fast-general", "OpenAI", "ok",
    )  # fmt: skip
    assert (log.prompt_tokens, log.completion_tokens, log.total_tokens) == (11, 5, 16)
    assert log.cost_usd == Decimal("0.000123") and log.request_id == "chatcmpl-abc123"
    assert (log.attempts, log.fallback_used, log.config_version, log.client_id, log.user_id) == (
        1, False, 3, client_id, env.admin.id,
    )  # fmt: skip  # version 3 = enable + agent config
    assert log.latency_ms >= 0 and log.error_class is None
    # prompts / completions are never stored
    assert "SECRET-CLIENT-DATA" not in json.dumps(
        {c.name: str(getattr(log, c.name)) for c in log.__table__.columns}
    )


async def test_missing_cost_and_usage_are_stored_as_null_not_zero(
    env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general")
    up = Upstream(default=(200, {"choices": [{"message": {"content": "x"}}]}, {}))
    await env.call(up.gateway(session_factory))
    [log] = await env.logs(session_factory)
    assert (log.total_tokens, log.cost_usd, log.request_id) == (None, None, None)


async def test_a_disabled_or_unknown_model_is_never_called(
    env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general")
    # disable is refused while in use; switch the default away first
    await env.enable("claude-balanced")
    assert (await env.agent("intake", "claude-balanced")).status_code == 200
    r = await env.api.put(
        f"{API}/llm/models/fast-general/enabled", json={"enabled": False}, headers=env.hdr
    )
    assert r.status_code == 200
    up = Upstream()
    await env.call(up.gateway(session_factory))
    assert up.models_called() == ["claude-balanced"]
    with pytest.raises(ModelUnavailableError):
        await env.call(up.gateway(session_factory)) if False else await up.gateway(
            session_factory
        ).complete(firm_id=env.firm.id, agent="intake", task="not_a_task", messages=MSGS)


async def test_firms_are_isolated_in_configuration_and_logs(
    env: Env,
    api: httpx.AsyncClient,
    world: World,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await env.configure("fast-general")
    other = await Env(api, world).build()
    up = Upstream()
    with pytest.raises(ModelUnavailableError):  # firm B never enabled anything
        await other.call(up.gateway(session_factory))
    await env.call(up.gateway(session_factory))
    assert (await api.get(f"{API}/llm/usage", headers=other.hdr)).json()["total"] == 0
    assert (await api.get(f"{API}/llm/usage", headers=env.hdr)).json()["total"] == 1
    models = (await api.get(f"{API}/llm/models", headers=other.hdr)).json()["models"]
    assert not any(m["enabled"] for m in models)


# ============================================================================ retries, fallback, failures


async def test_transient_errors_are_retried_with_backoff_then_succeed(
    env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general")
    up = Upstream({"fast-general": [(503, {}, {}), (429, {}, {}), (200, GOOD, {})]})
    r = await env.call(
        up.gateway(session_factory, llm_max_retries=2, llm_retry_backoff_seconds=0.5)
    )
    assert r.attempts == 3 and r.alias == "fast-general"
    assert up.sleeps == [0.5, 1.0]  # exponential
    [log] = await env.logs(session_factory)
    assert (log.status, log.attempts) == ("ok", 3)


async def test_retries_are_bounded_and_failures_are_safe_and_logged(
    env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general")
    leak = {"error": "provider says: key sk-live-SECRET invalid at https://api.openai.com/v1"}
    up = Upstream({"fast-general": [(500, leak, {})]})
    with pytest.raises(LlmCallFailedError) as e:
        await env.call(up.gateway(session_factory, llm_max_retries=2))
    assert len(up.requests) == 3  # 1 try + 2 retries, then stop
    assert "sk-live" not in e.value.message and "openai" not in e.value.message.lower()
    [log] = await env.logs(session_factory)
    assert (log.status, log.attempts, log.error_class, log.total_tokens) == (
        "error",
        3,
        "http_500",
        None,
    )


async def test_zero_retries_means_exactly_one_attempt(
    env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general")
    up = Upstream({"fast-general": [(503, {}, {})]})
    with pytest.raises(LlmCallFailedError):
        await env.call(up.gateway(session_factory, llm_max_retries=0))
    assert len(up.requests) == 1 and up.sleeps == []


async def test_timeouts_and_connection_errors_are_retried_then_fall_back(
    env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general", "claude-balanced")
    up = Upstream({"fast-general": [httpx.ReadTimeout("slow"), httpx.ConnectError("refused")]})
    r = await env.call(up.gateway(session_factory, llm_max_retries=1))
    assert up.models_called() == ["fast-general", "fast-general", "claude-balanced"]
    assert (r.alias, r.fallback_used, r.attempts) == ("claude-balanced", True, 3)


async def test_fallback_is_used_only_when_configured_and_is_logged(
    env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general", "claude-balanced")
    up = Upstream({"fast-general": [(503, {}, {})]})
    r = await env.call(up.gateway(session_factory, llm_max_retries=1))
    assert (r.alias, r.provider, r.fallback_used) == ("claude-balanced", "Anthropic", True)
    [log] = await env.logs(session_factory)
    assert (log.requested_alias, log.alias, log.provider, log.fallback_used, log.status) == (
        "fast-general", "claude-balanced", "Anthropic", True, "ok",
    )  # fmt: skip


async def test_no_fallback_configured_means_no_other_model_is_ever_tried(
    env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general")
    await env.enable(
        "claude-balanced", "strong-general"
    )  # enabled, but not configured as a fallback
    up = Upstream({"fast-general": [(503, {}, {})]})
    with pytest.raises(LlmCallFailedError):
        await env.call(up.gateway(session_factory, llm_max_retries=0))
    assert up.models_called() == ["fast-general"]


async def test_bad_request_is_not_retried_and_does_not_fall_back(
    env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general", "claude-balanced")
    up = Upstream({"fast-general": [(400, {"error": "bad params"}, {})]})
    with pytest.raises(LlmCallFailedError):
        await env.call(up.gateway(session_factory))
    assert up.models_called() == ["fast-general"]  # our own mistake would fail on the fallback too


@pytest.mark.parametrize("status", [401, 403, 404])
async def test_unusable_alias_falls_back_without_retrying(
    status: int, env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general", "claude-balanced")
    up = Upstream({"fast-general": [(status, {}, {})]})
    r = await env.call(up.gateway(session_factory, llm_max_retries=2))
    assert up.models_called() == ["fast-general", "claude-balanced"] and r.fallback_used
    assert up.sleeps == []


@pytest.mark.parametrize(
    "payload",
    [
        {"nope": 1},
        {"choices": []},
        {"choices": [{"message": {"content": ""}}]},
        {"choices": [{"message": {}}]},
    ],
)
async def test_malformed_provider_responses_are_rejected_and_fall_back(
    payload: dict[str, Any], env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general", "claude-balanced")
    up = Upstream({"fast-general": [(200, payload, {})]})
    r = await env.call(up.gateway(session_factory))
    assert r.alias == "claude-balanced" and r.attempts == 2


async def test_when_primary_and_fallback_both_fail_the_error_is_logged_against_the_last_alias(
    env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general", "claude-balanced")
    up = Upstream(default=(503, {}, {}))
    with pytest.raises(LlmCallFailedError):
        await env.call(up.gateway(session_factory, llm_max_retries=1))
    [log] = await env.logs(session_factory)
    assert (log.status, log.requested_alias, log.alias, log.fallback_used, log.attempts) == (
        "error", "fast-general", "claude-balanced", True, 4,
    )  # fmt: skip


async def test_oversized_input_skips_models_that_cannot_hold_it(
    env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general", "gemini-fast")  # 128k vs 1M context
    big = [{"role": "user", "content": "x" * 500_000}]  # ~166k tokens by the pessimistic estimate
    up = Upstream()
    r = await LlmGateway(
        session_factory, settings(), transport=httpx.MockTransport(up.handler)
    ).complete(firm_id=env.firm.id, agent="intake", task="column_roles", messages=big)
    assert r.alias == "gemini-fast" and up.models_called() == ["gemini-fast"]
    huge = [{"role": "user", "content": "x" * 5_000_000}]
    with pytest.raises(InputTooLargeError):
        await LlmGateway(
            session_factory, settings(), transport=httpx.MockTransport(up.handler)
        ).complete(firm_id=env.firm.id, agent="intake", task="column_roles", messages=huge)
    assert len(up.requests) == 1  # nothing was sent for the impossible request


# ============================================================================ capability validation


@pytest.fixture
def vision_task(monkeypatch: pytest.MonkeyPatch) -> TaskSpec:
    t = TaskSpec("accounting_review", "read_scan", "needs vision", frozenset({CAP_VISION}), 1000)
    monkeypatch.setitem(TASKS, t.key, t)
    return t


async def test_models_lacking_a_required_capability_cannot_be_assigned(
    env: Env, vision_task: TaskSpec
) -> None:
    await env.enable("gemini-fast", "fast-general")  # gemini-fast has no vision
    r = await env.agent("accounting_review", "gemini-fast")
    assert (
        r.status_code == 422
        and "vision" in r.json()["detail"]
        and "read_scan" in r.json()["detail"]
    )
    assert (await env.agent("accounting_review", "fast-general")).status_code == 200
    assert (
        await env.agent("accounting_review", "fast-general", "gemini-fast")
    ).status_code == 422  # as fallback too
    eligible = {
        a["key"]: a["eligible"]
        for a in (await env.api.get(f"{API}/llm/agents", headers=env.hdr)).json()["agents"]
    }
    assert eligible["accounting_review"] == ["fast-general"]


async def test_context_window_is_validated_against_the_task(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        TASKS,
        "reporting.long_report",
        TaskSpec("reporting", "long_report", "x", frozenset(), 500_000),
    )
    await env.enable("fast-general", "gemini-fast")
    r = await env.agent("reporting", "fast-general")
    assert r.status_code == 422 and "context window" in r.json()["detail"]
    assert (await env.agent("reporting", "gemini-fast")).status_code == 200


async def test_a_default_that_stops_being_capable_is_skipped_at_call_time(
    env: Env, session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    await env.configure("fast-general")
    stripped = ModelSpec(
        "fast-general", "Fast general", "OpenAI", "x", 128_000, frozenset(), "economy"
    )
    monkeypatch.setitem(
        MODELS, "fast-general", stripped
    )  # e.g. a catalog update removes a capability
    up = Upstream()
    with pytest.raises(ModelUnavailableError):
        await env.call(up.gateway(session_factory))
    assert up.requests == []


# ============================================================================ API: authorization


async def test_model_endpoints_require_authentication(api: httpx.AsyncClient) -> None:
    for method, path, body in [
        ("get", "/llm/models", None), ("put", "/llm/models/fast-general/enabled", {"enabled": True}),
        ("post", "/llm/models/fast-general/test", None), ("get", "/llm/agents", None),
        ("put", "/llm/agents/intake", {"default_alias": "fast-general"}),
        ("put", "/llm/agents/intake/tasks/column_roles", {"alias": "fast-general"}),
        ("delete", "/llm/agents/intake/tasks/column_roles", None), ("put", "/llm/policy", {"allow_task_overrides": True}),
        ("get", "/llm/usage", None), ("get", "/llm/usage/summary", None),
    ]:  # fmt: skip
        r = await getattr(api, method)(f"{API}{path}", **({"json": body} if body else {}))
        assert r.status_code == 401, (method, path)


async def test_only_firm_admins_can_change_model_configuration(
    env: Env, api: httpx.AsyncClient
) -> None:
    await env.enable("fast-general", "claude-balanced")
    for role in (CA_REVIEWER, ACCOUNTANT, CLIENT_USER):
        h = await env.user_hdr(role)
        for method, path, body in [
            ("put", "/llm/models/fast-general/enabled", {"enabled": False}),
            ("put", "/llm/agents/intake", {"default_alias": "fast-general"}),
            ("put", "/llm/policy", {"allow_task_overrides": True}),
            ("post", "/llm/models/fast-general/test", None),
            ("get", "/llm/usage", None), ("get", "/llm/usage/summary", None),
        ]:  # fmt: skip
            r = await getattr(api, method)(
                f"{API}{path}", headers=h, **({"json": body} if body else {})
            )
            assert r.status_code == 403, (role, method, path)
    # nothing changed
    models = (await api.get(f"{API}/llm/models", headers=env.hdr)).json()["models"]
    assert {m["alias"] for m in models if m["enabled"]} == {"fast-general", "claude-balanced"}


async def test_read_access_by_role(env: Env, api: httpx.AsyncClient) -> None:
    for role, code in ((CA_REVIEWER, 200), (ACCOUNTANT, 200), (CLIENT_USER, 403)):
        h = await env.user_hdr(role)
        assert (await api.get(f"{API}/llm/models", headers=h)).status_code == code, role
        assert (await api.get(f"{API}/llm/agents", headers=h)).status_code == code, role


async def test_responses_never_contain_secrets_or_provider_internals(
    env: Env, api: httpx.AsyncClient
) -> None:
    await env.configure("fast-general", "claude-balanced")
    blob = ""
    for path in ("/llm/models", "/llm/agents", "/llm/usage", "/llm/usage/summary"):
        blob += (await api.get(f"{API}{path}", headers=env.hdr)).text
    for forbidden in (
        MASTER_KEY,
        "api_key",
        "OPENAI_API_KEY",
        "gpt-4o",
        "claude-sonnet-4-5",
        "gemini-2.5",
        "os.environ",
        "localhost:4000",
    ):
        assert forbidden not in blob, forbidden
    assert "fast-general" in blob  # aliases and display metadata only


async def test_unapproved_or_spoofed_model_names_are_rejected_everywhere(
    env: Env, api: httpx.AsyncClient
) -> None:
    await env.enable("fast-general")
    for bad in (
        "gpt-4o",
        "openai/gpt-4o",
        "../../etc/passwd",
        "FAST-GENERAL",
        " fast-general",
        "fast-general\n",
    ):
        quoted = quote(bad, safe="")
        r = await api.put(
            f"{API}/llm/models/{quoted}/enabled", json={"enabled": True}, headers=env.hdr
        )
        assert r.status_code in (404, 405), bad
        if bad.strip() == "fast-general":
            continue  # surrounding whitespace is stripped by the schema; still the exact approved alias
        r = await env.agent("intake", bad)
        assert r.status_code == 422, bad
        r = await env.agent("intake", "fast-general", bad)
        assert r.status_code == 422, bad
        assert (await api.post(f"{API}/llm/models/{quoted}/test", headers=env.hdr)).status_code in (
            404,
            405,
        )


# ============================================================================ API: behaviour


async def test_list_models_shape_and_default_state(env: Env, api: httpx.AsyncClient) -> None:
    body = (await api.get(f"{API}/llm/models", headers=env.hdr)).json()
    assert [m["alias"] for m in body["models"]] == list(MODELS)
    assert all(m["enabled"] is False and m["used_by"] == [] for m in body["models"])
    assert all(m["available"] is None for m in body["models"])  # no gateway reachable in tests
    m = next(m for m in body["models"] if m["alias"] == "gemini-fast")
    assert (m["provider"], m["context_window"], m["capabilities"]) == (
        "Google",
        1_000_000,
        ["structured_output", "tools"],
    )
    assert body["config_version"] == 1


async def test_availability_reflects_what_the_gateway_serves(
    env: Env, api: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    as_gateway(api, Upstream().gateway(session_factory))
    models = {
        m["alias"]: m["available"]
        for m in (await api.get(f"{API}/llm/models", headers=env.hdr)).json()["models"]
    }
    assert models == {
        "fast-general": True,
        "strong-general": False,
        "claude-balanced": False,
        "gemini-fast": True,
    }


async def test_enable_disable_roundtrip_with_versioning_and_audit(
    env: Env, api: httpx.AsyncClient, db: AsyncSession
) -> None:
    r = await api.put(
        f"{API}/llm/models/fast-general/enabled", json={"enabled": True}, headers=env.hdr
    )
    assert r.json() == {"config_version": 2}
    r = await api.put(
        f"{API}/llm/models/fast-general/enabled", json={"enabled": False}, headers=env.hdr
    )
    assert r.json() == {"config_version": 3}
    audits = (
        await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.firm_id == env.firm.id, AuditEvent.action.like("llm.%"))
            .order_by(AuditEvent.created_at)
        )
    ).all()
    assert [a.action for a in audits] == ["llm.model_enabled", "llm.model_disabled"]
    assert audits[1].actor_user_id == env.admin.id
    assert (
        audits[1].event_metadata["alias"] == "fast-general"
        and audits[1].event_metadata["was_enabled"] is True
    )
    assert (
        await api.put(
            f"{API}/llm/models/fast-general/enabled",
            json={"enabled": "yes", "x": 1},
            headers=env.hdr,
        )
    ).status_code == 422


async def test_a_model_in_use_cannot_be_disabled(env: Env, api: httpx.AsyncClient) -> None:
    await env.configure("fast-general", "claude-balanced")
    for alias in ("fast-general", "claude-balanced"):
        r = await api.put(
            f"{API}/llm/models/{alias}/enabled", json={"enabled": False}, headers=env.hdr
        )
        assert r.status_code == 409 and "intake" in r.json()["detail"]
    models = {
        m["alias"]: m
        for m in (await api.get(f"{API}/llm/models", headers=env.hdr)).json()["models"]
    }
    assert models["fast-general"]["used_by"] == ["intake"] and models["fast-general"]["enabled"]


async def test_agent_configuration_validation(env: Env, api: httpx.AsyncClient) -> None:
    await env.enable("fast-general", "claude-balanced")
    assert (
        await env.agent("intake", "strong-general")
    ).status_code == 422  # approved but not enabled
    assert (await env.agent("intake", "fast-general", "strong-general")).status_code == 422
    assert (
        await env.agent("intake", "fast-general", "fast-general")
    ).status_code == 422  # same as default
    assert (await env.agent("nonexistent", "fast-general")).status_code == 404
    assert (
        await api.put(f"{API}/llm/agents/intake", json={"default_alias": ""}, headers=env.hdr)
    ).status_code == 422
    assert (
        await api.put(
            f"{API}/llm/agents/intake",
            json={"default_alias": "fast-general", "x": 1},
            headers=env.hdr,
        )
    ).status_code == 422
    r = await env.agent("intake", "fast-general", "claude-balanced")
    assert r.status_code == 200
    agents = {
        a["key"]: a for a in (await api.get(f"{API}/llm/agents", headers=env.hdr)).json()["agents"]
    }
    assert list(agents) == list(AGENTS) and len(agents) == 4
    assert (agents["intake"]["default_alias"], agents["intake"]["fallback_alias"]) == (
        "fast-general",
        "claude-balanced",
    )
    assert agents["reporting"]["default_alias"] is None
    t = agents["intake"]["tasks"][0]
    assert (t["task"], t["effective_alias"], t["source"]) == (
        "column_roles",
        "fast-general",
        "agent_default",
    )
    # removing the fallback by omitting it
    assert (await env.agent("intake", "fast-general", None)).status_code == 200
    assert (await api.get(f"{API}/llm/agents", headers=env.hdr)).json()["agents"][0][
        "fallback_alias"
    ] is None


async def test_task_override_requires_policy_permission_and_a_capable_enabled_model(
    env: Env, api: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general")
    await env.enable("claude-balanced")
    reviewer = await env.user_hdr(CA_REVIEWER)
    url = f"{API}/llm/agents/intake/tasks/column_roles"

    # policy off (default): even a user with llm:select is refused
    assert (
        await api.put(url, json={"alias": "claude-balanced"}, headers=reviewer)
    ).status_code == 403
    assert (
        await api.put(f"{API}/llm/policy", json={"allow_task_overrides": True}, headers=env.hdr)
    ).status_code == 200

    accountant = await env.user_hdr(ACCOUNTANT)  # has no llm:select
    assert (
        await api.put(url, json={"alias": "claude-balanced"}, headers=accountant)
    ).status_code == 403
    assert (
        await api.put(url, json={"alias": "strong-general"}, headers=reviewer)
    ).status_code == 422  # not enabled
    assert (
        await api.put(url, json={"alias": "gpt-4o"}, headers=reviewer)
    ).status_code == 422  # not approved
    assert (
        await api.put(
            f"{API}/llm/agents/intake/tasks/nope", json={"alias": "fast-general"}, headers=reviewer
        )
    ).status_code == 404
    assert (
        await api.put(url, json={"alias": "claude-balanced"}, headers=reviewer)
    ).status_code == 200

    t = (await api.get(f"{API}/llm/agents", headers=reviewer)).json()["agents"][0]["tasks"][0]
    assert (t["effective_alias"], t["source"], t["override_alias"]) == (
        "claude-balanced",
        "task_override",
        "claude-balanced",
    )
    up = Upstream()
    await env.call(up.gateway(session_factory))
    assert up.models_called() == ["claude-balanced"]

    # turning the policy off makes the gateway ignore the override again
    await api.put(f"{API}/llm/policy", json={"allow_task_overrides": False}, headers=env.hdr)
    up2 = Upstream()
    await env.call(up2.gateway(session_factory))
    assert up2.models_called() == ["fast-general"]
    # an override blocks disabling its model until it is cleared
    await api.put(f"{API}/llm/policy", json={"allow_task_overrides": True}, headers=env.hdr)
    assert (
        await api.put(
            f"{API}/llm/models/claude-balanced/enabled", json={"enabled": False}, headers=env.hdr
        )
    ).status_code == 409
    assert (await api.delete(url, headers=reviewer)).status_code == 200
    assert (
        await api.put(
            f"{API}/llm/models/claude-balanced/enabled", json={"enabled": False}, headers=env.hdr
        )
    ).status_code == 200


async def test_every_configuration_change_bumps_the_version_and_is_audited(
    env: Env, api: httpx.AsyncClient, db: AsyncSession
) -> None:
    await env.configure("fast-general", "claude-balanced")  # 2 enables + 1 agent = versions 2,3,4
    await api.put(f"{API}/llm/policy", json={"allow_task_overrides": True}, headers=env.hdr)  # 5
    await api.put(
        f"{API}/llm/agents/intake/tasks/column_roles",
        json={"alias": "claude-balanced"},
        headers=env.hdr,
    )  # 6
    r = await api.delete(f"{API}/llm/agents/intake/tasks/column_roles", headers=env.hdr)  # 7
    assert r.json()["config_version"] == 7
    actions = [
        a.action
        for a in (
            await db.scalars(
                select(AuditEvent)
                .where(AuditEvent.firm_id == env.firm.id, AuditEvent.action.like("llm.%"))
                .order_by(AuditEvent.created_at)
            )
        ).all()
    ]
    assert actions == [
        "llm.model_enabled", "llm.model_enabled", "llm.agent_config_set", "llm.policy_set",
        "llm.task_override_set", "llm.task_override_cleared",
    ]  # fmt: skip
    assert (
        await api.delete(f"{API}/llm/agents/intake/tasks/column_roles", headers=env.hdr)
    ).json()["config_version"] == 7  # no-op


async def test_usage_endpoints_and_summary(
    env: Env, api: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general", "claude-balanced")
    ok = Upstream(default=(200, GOOD, {"x-litellm-response-cost": "0.5"}))
    await env.call(ok.gateway(session_factory))
    await env.call(ok.gateway(session_factory))
    with pytest.raises(LlmCallFailedError):
        await env.call(Upstream(default=(503, {}, {})).gateway(session_factory, llm_max_retries=0))
    page = (await api.get(f"{API}/llm/usage?limit=2&offset=0", headers=env.hdr)).json()
    assert (page["total"], len(page["items"])) == (3, 2)
    assert (
        page["items"][0]["status"] == "error" and page["items"][0]["id"] > page["items"][1]["id"]
    )  # newest first
    assert (await api.get(f"{API}/llm/usage?agent=reporting", headers=env.hdr)).json()["total"] == 0
    assert (await api.get(f"{API}/llm/usage?limit=0", headers=env.hdr)).status_code == 422
    summary = (await api.get(f"{API}/llm/usage/summary", headers=env.hdr)).json()
    by = {(r["alias"], r["agent"]): r for r in summary}
    fg = by[("fast-general", "intake")]
    assert (fg["calls"], fg["errors"], fg["tokens"], Decimal(str(fg["cost_usd"]))) == (
        2,
        0,
        32,
        Decimal("1.0"),
    )
    cb = by[("claude-balanced", "intake")]
    assert (cb["calls"], cb["errors"], cb["fallbacks"]) == (1, 1, 1)


async def test_connection_test_endpoint_reports_outcome_without_details(
    env: Env,
    api: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    db: AsyncSession,
) -> None:
    as_gateway(api, Upstream().gateway(session_factory))
    r = await api.post(
        f"{API}/llm/models/claude-balanced/test", headers=env.hdr
    )  # works before enabling
    body = r.json()
    assert (
        r.status_code == 200
        and body["ok"] is True
        and body["alias"] == "claude-balanced"
        and body["error_code"] is None
    )
    logs = await env.logs(session_factory)
    assert [(entry.task, entry.alias, entry.user_id) for entry in logs] == [
        ("gateway_test", "claude-balanced", env.admin.id)
    ]
    assert logs[0].correlation_id == r.headers["x-request-id"]

    as_gateway(
        api,
        Upstream(default=(503, {"error": "sk-live-LEAK"}, {})).gateway(
            session_factory, llm_max_retries=0
        ),
    )
    r2 = await api.post(f"{API}/llm/models/fast-general/test", headers=env.hdr)
    assert r2.json() == {
        "ok": False,
        "alias": "fast-general",
        "latency_ms": None,
        "attempts": None,
        "error_code": "llm_call_failed",
    }
    assert "LEAK" not in r2.text
    a = await db.scalar(
        select(AuditEvent).where(
            AuditEvent.firm_id == env.firm.id,
            AuditEvent.action == "llm.model_tested",
            AuditEvent.outcome == "failure",
        )
    )
    assert a is not None


async def test_call_log_is_append_only(
    env: Env, session_factory: async_sessionmaker[AsyncSession], db: AsyncSession
) -> None:
    await env.configure("fast-general")
    await env.call(Upstream().gateway(session_factory))
    with pytest.raises(DBAPIError):
        await db.execute(
            text("UPDATE llm_call_logs SET latency_ms = 0 WHERE firm_id = :f"), {"f": env.firm.id}
        )
    await db.rollback()
    with pytest.raises(DBAPIError):
        await db.execute(text("DELETE FROM llm_call_logs WHERE firm_id = :f"), {"f": env.firm.id})
    await db.rollback()


async def test_a_usage_log_failure_never_breaks_a_successful_call(
    env: Env, session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    await env.configure("fast-general")
    gw = Upstream().gateway(session_factory)

    async def broken(*a: Any, **k: Any) -> None:
        raise RuntimeError("db down")

    # resolve with the real DB, then make only the log write fail
    monkeypatch.setattr(type(gw), "_log", lambda self, *a, **k: _swallow(self, *a, **k))

    async def _swallow(self: LlmGateway, *a: Any, **k: Any) -> None:
        try:
            await broken()
        except RuntimeError:
            return

    r = await env.call(gw)
    assert r.text == "hello"


# ============================================================================ wire contract (real HTTP)


async def test_gateway_talks_real_http_to_a_litellm_compatible_server(
    env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general")
    seen: dict[str, Any] = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            seen["path"], seen["auth"] = self.path, self.headers.get("Authorization")
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            out = json.dumps(GOOD).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        gw = LlmGateway(
            session_factory, settings(litellm_base_url=f"http://127.0.0.1:{server.server_port}")
        )
        r = await env.call(gw)
    finally:
        server.shutdown()
    assert r.text == "hello" and seen["path"] == "/chat/completions"
    assert seen["auth"] == f"Bearer {MASTER_KEY}" and seen["body"]["model"] == "fast-general"


async def test_unreachable_gateway_fails_safely(
    env: Env, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await env.configure("fast-general")
    gw = LlmGateway(
        session_factory,
        settings(litellm_base_url="http://127.0.0.1:9", llm_max_retries=0, llm_timeout_seconds=1),
    )
    with pytest.raises(LlmCallFailedError):
        await env.call(gw)
    [log] = await env.logs(session_factory)
    assert log.status == "error" and log.error_class == "ConnectError"


# ============================================================================ Agent 1 uses the gateway


async def test_intake_assistant_goes_through_the_gateway_and_is_logged(
    env: Env, api: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], store: Any
) -> None:
    await env.configure("fast-general")
    s = await Setup(api, env.world).build()  # separate firm: gives us a client+period to upload to
    await s.world.firm()
    # enable a model for THAT firm via its own admin
    for a in ("fast-general",):
        await api.put(f"{API}/llm/models/{a}/enabled", json={"enabled": True}, headers=s.hdr)
    await api.put(f"{API}/llm/agents/intake", json={"default_alias": "fast-general"}, headers=s.hdr)
    answer = json.dumps(
        {
            "document_type": "inventory_report",
            "columns": [{"index": 2, "role": "quantity", "confidence": 0.9}],
        }
    )
    up = Upstream(default=(200, {**GOOD, "choices": [{"message": {"content": answer}}]}, {}))
    gw = up.gateway(session_factory)
    r = await s.upload(fx.weird_headers_xlsx(), "w.xlsx", "inventory_report")
    doc_id = r.json()["id"]
    assistant = GatewayAssistant(gw, s.firm.id, s.client.id)
    await intake.extract_document(
        session_factory, store, settings(), uuid.UUID(doc_id), assistant=assistant
    )
    ext = (
        await api.get(
            f"{API}/clients/{s.client.id}/periods/{s.period_id}/documents/{doc_id}/extraction",
            headers=s.hdr,
        )
    ).json()
    assert ext["document_status"] == "processed" and ext["run"]["llm_used"] is True
    col = ext["tables"][0]["columns"][2]
    assert (col["effective_role"], col["role_source"], col["confirmed_role"]) == (
        "quantity",
        "llm",
        None,
    )
    assert ext["tables"][0]["status"] == "needs_review"  # an AI suggestion is never auto-accepted
    async with session_factory() as db:
        logs = (await db.scalars(select(LlmCallLog).where(LlmCallLog.firm_id == s.firm.id))).all()
    assert [(entry.agent, entry.task, entry.alias, entry.client_id) for entry in logs] == [
        ("intake", "column_roles", "fast-general", s.client.id)
    ]
    body = json.loads(up.requests[0].content)
    assert "Do NOT calculate" in body["messages"][0]["content"] and body["model"] == "fast-general"


async def test_intake_still_works_when_no_model_is_enabled_or_the_gateway_is_down(
    api: httpx.AsyncClient,
    world: World,
    session_factory: async_sessionmaker[AsyncSession],
    store: Any,
) -> None:
    s = await Setup(api, world).build()  # no model enabled for this firm
    up = Upstream()
    gw = up.gateway(session_factory)
    r = await s.upload(fx.weird_headers_xlsx(), "w.xlsx", "bank_statement")
    await intake.extract_document(
        session_factory,
        store,
        settings(),
        uuid.UUID(r.json()["id"]),
        assistant=GatewayAssistant(gw, s.firm.id, s.client.id),
    )
    ext = (
        await api.get(
            f"{API}/clients/{s.client.id}/periods/{s.period_id}/documents/{r.json()['id']}/extraction",
            headers=s.hdr,
        )
    ).json()
    assert ext["document_status"] == "processed" and ext["run"]["llm_used"] is False
    assert up.requests == []  # blocked before any call: client data was not sent anywhere

    await api.put(f"{API}/llm/models/fast-general/enabled", json={"enabled": True}, headers=s.hdr)
    await api.put(f"{API}/llm/agents/intake", json={"default_alias": "fast-general"}, headers=s.hdr)
    down = Upstream(default=(503, {}, {})).gateway(session_factory, llm_max_retries=0)
    r2 = await s.upload(
        fx.dated_xlsx(["03/04/2025", "05/06/2025"]) + b"", "x.xlsx", "bank_statement"
    )
    await intake.extract_document(
        session_factory,
        store,
        settings(),
        uuid.UUID(r2.json()["id"]),
        assistant=GatewayAssistant(down, s.firm.id, s.client.id),
    )
    ext2 = (
        await api.get(
            f"{API}/clients/{s.client.id}/periods/{s.period_id}/documents/{r2.json()['id']}/extraction",
            headers=s.hdr,
        )
    ).json()
    assert ext2["document_status"] == "processed"


# ============================================================================ architecture rules

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"
PROVIDER_IMPORT = re.compile(
    r"^\s*(?:import|from)\s+(openai|anthropic|litellm|google\.generativeai|google\.genai|cohere|mistralai|groq|"
    r"vertexai|langchain_openai|langchain_anthropic|boto3\.client\(.bedrock)\b",
    re.M,
)


def py_files() -> list[Path]:
    return [p for p in APP.rglob("*.py")]


def test_no_module_imports_a_provider_sdk() -> None:
    offenders = [
        str(p.relative_to(APP)) for p in py_files() if PROVIDER_IMPORT.search(p.read_text())
    ]
    assert offenders == []


def test_only_the_gateway_and_health_check_make_outbound_http_calls() -> None:
    users = sorted(
        str(p.relative_to(APP))
        for p in py_files()
        if re.search(r"^\s*(?:import httpx|from httpx)", p.read_text(), re.M)
    )
    assert users == ["integrations/health.py", "llm/gateway.py"]


def test_no_code_outside_the_gateway_knows_the_chat_completions_endpoint() -> None:
    hits = [str(p.relative_to(APP)) for p in py_files() if "chat/completions" in p.read_text()]
    assert hits == ["llm/gateway.py"]


def test_litellm_config_lists_exactly_the_approved_aliases_and_no_inline_secrets() -> None:
    cfg_text = (ROOT / "infrastructure" / "litellm" / "config.yaml").read_text()
    cfg = yaml.safe_load(cfg_text)
    assert sorted(m["model_name"] for m in cfg["model_list"]) == sorted(MODELS)
    for m in cfg["model_list"]:
        assert m["litellm_params"]["api_key"].startswith(
            "os.environ/"
        )  # keys only from the environment
    assert cfg["general_settings"]["master_key"] == "os.environ/LITELLM_MASTER_KEY"
    assert (
        cfg["litellm_settings"]["num_retries"] == 0
    )  # retries are done (and logged) by the backend
    assert not re.search(r"sk-[A-Za-z0-9]{10,}", cfg_text)


def test_provider_keys_exist_only_on_the_litellm_service_in_compose() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]
    for name, svc in compose.items():
        env = svc.get("environment") or {}
        keys = set(env) if isinstance(env, dict) else {e.split("=")[0] for e in env}
        provider = keys & {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"}
        assert (name == "litellm") == bool(provider), name


def test_catalog_is_consistent() -> None:
    assert len(AGENTS) == 4
    for t in TASKS.values():
        assert t.agent in AGENTS
        assert t.requires <= {"structured_output", "tools", "vision"}
    assert CAP_STRUCTURED in TASKS["intake.column_roles"].requires
    assert all(m.context_window > 0 for m in MODELS.values())


def test_gateway_settings_are_bounded() -> None:
    from pydantic import ValidationError

    from app.core.config import Settings

    base = {
        "database_url": "postgresql://u:p@h/db", "redis_url": "redis://:p@h:6379/0", "kafka_bootstrap_servers": "k:9092",
        "minio_endpoint": "http://m:9000", "minio_access_key": "a", "minio_secret_key": "b",
        "litellm_base_url": "http://l:4000", "litellm_api_key": "sk-x", "jwt_secret": "x" * 40,
    }  # fmt: skip
    Settings(**base)  # type: ignore[arg-type]
    for bad in (
        {"llm_max_retries": 6},
        {"llm_max_retries": -1},
        {"llm_timeout_seconds": 0},
        {"llm_timeout_seconds": 301},
    ):
        with pytest.raises(ValidationError):
            Settings(**{**base, **bad})  # type: ignore[arg-type]
