"""Dependency health checks used by the readiness endpoint.

Error details intentionally contain only the exception class name so that
connection strings or credentials can never leak through a health response.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import asyncpg
import httpx
import redis.asyncio as aioredis

from app.core.config import Settings


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    ok: bool
    latency_ms: float
    detail: str | None = None


async def check_postgres(settings: Settings) -> None:
    conn = await asyncpg.connect(
        settings.database_url.get_secret_value(), timeout=settings.health_check_timeout_seconds
    )
    try:
        await conn.fetchval("SELECT 1")
    finally:
        await conn.close()


async def check_redis(settings: Settings) -> None:
    client = aioredis.from_url(settings.redis_url.get_secret_value())  # type: ignore[no-untyped-call]
    try:
        await client.ping()
    finally:
        await client.aclose()


async def check_kafka(settings: Settings) -> None:
    # Phase 0: TCP reachability of the first bootstrap server.
    # Phase 5 upgrades this to a real Kafka metadata request.
    host, _, port = settings.kafka_bootstrap_servers.split(",")[0].strip().rpartition(":")
    _, writer = await asyncio.open_connection(host, int(port))
    writer.close()
    await writer.wait_closed()


async def check_minio(settings: Settings) -> None:
    async with httpx.AsyncClient(timeout=settings.health_check_timeout_seconds) as client:
        resp = await client.get(f"{settings.minio_endpoint.rstrip('/')}/minio/health/live")
        resp.raise_for_status()


async def check_litellm(settings: Settings) -> None:
    async with httpx.AsyncClient(timeout=settings.health_check_timeout_seconds) as client:
        resp = await client.get(f"{settings.litellm_base_url.rstrip('/')}/health/liveliness")
        resp.raise_for_status()


CHECKS: dict[str, Callable[[Settings], Awaitable[None]]] = {
    "postgres": check_postgres,
    "redis": check_redis,
    "kafka": check_kafka,
    "minio": check_minio,
    "litellm": check_litellm,
}


async def _run_one(
    name: str, check: Callable[[Settings], Awaitable[None]], settings: Settings
) -> DependencyStatus:
    start = time.perf_counter()
    try:
        await asyncio.wait_for(check(settings), timeout=settings.health_check_timeout_seconds)
        return DependencyStatus(name, True, round((time.perf_counter() - start) * 1000, 1))
    except Exception as exc:
        return DependencyStatus(
            name, False, round((time.perf_counter() - start) * 1000, 1), type(exc).__name__
        )


async def run_dependency_checks(settings: Settings) -> list[DependencyStatus]:
    return list(await asyncio.gather(*(_run_one(n, c, settings) for n, c in CHECKS.items())))
