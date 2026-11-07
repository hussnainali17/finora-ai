# ruff: noqa: E501
"""The ONLY code in this application that talks to a language model.

Every AI call goes: resolve an approved, enabled, capable alias -> LiteLLM proxy (OpenAI-compatible HTTP) ->
bounded retries -> optional explicitly-configured fallback alias -> one usage-log row. Provider SDKs are
never imported anywhere (a test enforces it) and provider credentials never reach this process: the proxy
holds them. Only the LiteLLM master key (server-side) authenticates to the proxy.

Logs hold metadata only (alias, provider, tokens, latency, cost if reported, ids) - never prompts or
completions."""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.logging import correlation_id_var
from app.llm.catalog import AGENTS, MODELS, TASKS, ModelSpec, unsupported_reasons
from app.llm.errors import InputTooLargeError, LlmCallFailedError, LlmError, ModelUnavailableError
from app.llm.resolver import Resolution, resolve
from app.models import LlmCallLog

logger = logging.getLogger("app.llm")
CHARS_PER_TOKEN = (
    3  # deliberately pessimistic estimate used only to refuse obviously oversized input
)
RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
# After these the alias itself is unusable right now, so the configured fallback is tried.
FALLBACK_STATUS = RETRYABLE_STATUS | {401, 402, 403, 404}


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class LlmResult:
    text: str
    alias: str
    provider: str
    fallback_used: bool
    attempts: int
    latency_ms: int
    usage: Usage
    cost_usd: Decimal | None
    request_id: str | None


class _AttemptFailed(Exception):
    def __init__(self, error_class: str, *, fallback_ok: bool, retryable: bool) -> None:
        super().__init__(error_class)
        self.error_class, self.fallback_ok, self.retryable = error_class, fallback_ok, retryable


def estimate_tokens(messages: list[dict[str, str]]) -> int:
    return sum(len(m.get("content", "")) for m in messages) // CHARS_PER_TOKEN + 1


def _int(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def _cost(headers: httpx.Headers, body: dict[str, Any]) -> Decimal | None:
    raw = headers.get("x-litellm-response-cost")
    if raw is None:
        raw = (body.get("usage") or {}).get("cost") if isinstance(body.get("usage"), dict) else None
    try:
        d = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        return None
    return d if d.is_finite() and d >= 0 else None


class LlmGateway:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Any = asyncio.sleep,
    ) -> None:
        self._sm = sessionmaker
        self._s = settings
        self._transport = transport
        self._sleep = sleep
        self._base = settings.litellm_base_url.rstrip("/")

    # ------------------------------------------------------------------ public

    async def complete(
        self,
        *,
        firm_id: uuid.UUID,
        agent: str,
        task: str,
        messages: list[dict[str, str]],
        client_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        max_tokens: int | None = None,
    ) -> LlmResult:
        async with self._sm() as session:
            res = await resolve(session, firm_id, agent, task)
        return await self._run(res, firm_id, agent, task, messages, client_id, user_id, max_tokens)

    async def test_alias(self, *, firm_id: uuid.UUID, user_id: uuid.UUID, alias: str) -> LlmResult:
        """Admin connectivity check of ONE approved alias (enabled or not). Sends a fixed harmless prompt."""
        model = MODELS.get(alias)
        if model is None:
            raise ModelUnavailableError("Unknown model")
        task = TASKS["intake.column_roles"]  # any registered task: used only for logging/limits
        res = Resolution(task, model, None, 0, "admin_test")
        msgs = [{"role": "user", "content": "Reply with the single word: ok"}]
        return await self._run(res, firm_id, "intake", "gateway_test", msgs, None, user_id, 8)

    async def served_aliases(self) -> set[str] | None:
        """Aliases the proxy reports as configured; None if the proxy cannot be reached."""
        try:
            async with self._client(self._s.llm_availability_timeout_seconds) as c:
                r = await c.get("/models", headers=self._auth())
            r.raise_for_status()
            return {
                str(m["id"]) for m in r.json().get("data", []) if isinstance(m, dict) and "id" in m
            }
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None

    # ------------------------------------------------------------------ internals

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._s.litellm_api_key.get_secret_value()}"}

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base, timeout=timeout, transport=self._transport)

    async def _run(
        self,
        res: Resolution,
        firm_id: uuid.UUID,
        agent: str,
        task: str,
        messages: list[dict[str, str]],
        client_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        max_tokens: int | None,
    ) -> LlmResult:
        out_tokens = min(max_tokens or res.task.max_output_tokens, res.task.max_output_tokens)
        need = estimate_tokens(messages) + out_tokens
        chain: list[ModelSpec] = [res.model] + ([res.fallback] if res.fallback else [])
        chain = [m for m in chain if m.context_window >= need]
        if not chain:
            raise InputTooLargeError("The input is too large for the configured AI model")
        started = time.monotonic()
        attempts, last_error, last_alias = 0, "unknown", chain[0].alias
        try:
            for position, model in enumerate(chain):
                last_alias = model.alias
                for attempt in range(1 + self._s.llm_max_retries):
                    attempts += 1
                    try:
                        text, usage, cost, rid = await self._attempt(
                            model, messages, out_tokens, agent, task
                        )
                    except _AttemptFailed as exc:
                        last_error = exc.error_class
                        if exc.retryable and attempt < self._s.llm_max_retries:
                            await self._sleep(self._s.llm_retry_backoff_seconds * (2**attempt))
                            continue
                        if exc.fallback_ok and position + 1 < len(chain):
                            break  # next alias in the chain
                        raise LlmCallFailedError(
                            "The AI model could not complete the request"
                        ) from None
                    latency = int((time.monotonic() - started) * 1000)
                    result = LlmResult(
                        text,
                        model.alias,
                        model.provider,
                        position > 0,
                        attempts,
                        latency,
                        usage,
                        cost,
                        rid,
                    )
                    await self._log(res, firm_id, agent, task, client_id, user_id, result, None)
                    return result
            raise LlmCallFailedError("The AI model could not complete the request")
        except LlmError as exc:
            latency = int((time.monotonic() - started) * 1000)
            failed = LlmResult(
                "", last_alias, MODELS[last_alias].provider, last_alias != res.model.alias,
                attempts, latency, Usage(), None, None,
            )  # fmt: skip
            await self._log(res, firm_id, agent, task, client_id, user_id, failed, last_error)
            raise exc

    async def _attempt(
        self,
        model: ModelSpec,
        messages: list[dict[str, str]],
        max_tokens: int,
        agent: str,
        task: str,
    ) -> tuple[str, Usage, Decimal | None, str | None]:
        body = {
            "model": model.alias,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            "metadata": {"agent": agent, "task": task, "correlation_id": correlation_id_var.get()},
        }
        headers = {**self._auth(), "X-Request-ID": correlation_id_var.get() or ""}
        try:
            async with self._client(self._s.llm_timeout_seconds) as c:
                r = await c.post("/chat/completions", json=body, headers=headers)
        except httpx.TimeoutException:
            raise _AttemptFailed("timeout", fallback_ok=True, retryable=True) from None
        except httpx.HTTPError as exc:
            raise _AttemptFailed(type(exc).__name__, fallback_ok=True, retryable=True) from None
        if r.status_code != 200:
            raise _AttemptFailed(
                f"http_{r.status_code}",
                fallback_ok=r.status_code in FALLBACK_STATUS,
                retryable=r.status_code in RETRYABLE_STATUS,
            )
        try:
            data = r.json()
            text = data["choices"][0]["message"]["content"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError("empty")
        except (ValueError, KeyError, IndexError, TypeError):
            raise _AttemptFailed("bad_response", fallback_ok=True, retryable=False) from None
        u = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        usage = Usage(
            _int(u.get("prompt_tokens")),
            _int(u.get("completion_tokens")),
            _int(u.get("total_tokens")),
        )
        rid = (
            data.get("id")
            if isinstance(data.get("id"), str)
            else r.headers.get("x-litellm-call-id")
        )
        return text, usage, _cost(r.headers, data), (rid[:128] if rid else None)

    async def _log(
        self,
        res: Resolution,
        firm_id: uuid.UUID,
        agent: str,
        task: str,
        client_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        r: LlmResult,
        error: str | None,
    ) -> None:
        try:
            async with self._sm() as session, session.begin():
                session.add(
                    LlmCallLog(
                        firm_id=firm_id, client_id=client_id, user_id=user_id, agent=agent, task=task,
                        requested_alias=res.model.alias, alias=r.alias, provider=r.provider,
                        status="error" if error else "ok", fallback_used=r.fallback_used,
                        attempts=max(r.attempts, 1), latency_ms=r.latency_ms,
                        prompt_tokens=r.usage.prompt_tokens, completion_tokens=r.usage.completion_tokens,
                        total_tokens=r.usage.total_tokens, cost_usd=r.cost_usd, request_id=r.request_id,
                        correlation_id=correlation_id_var.get(), config_version=res.config_version,
                        error_class=error,
                    )
                )  # fmt: skip
        except Exception:  # a logging failure must never turn a good answer into an error
            logger.exception("could not write llm usage log")


__all__ = ["AGENTS", "LlmGateway", "LlmResult", "Usage", "unsupported_reasons"]
