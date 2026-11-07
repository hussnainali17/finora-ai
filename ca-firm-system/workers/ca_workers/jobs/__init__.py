"""Durable job state for idempotent consumer processing.

The ``worker_jobs`` table (created in migration 0005) stores one row per
``event_id``. Consumers call ``is_already_processed`` before doing any work
and ``mark_job_*`` to record the outcome.  Duplicate Kafka delivery of the
same event_id is detected here and silently skipped.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


async def is_already_processed(session: AsyncSession, event_id: uuid.UUID) -> bool:
    """Return True if this event_id was already completed or is running."""
    result = await session.execute(
        text(
            "SELECT status FROM worker_jobs WHERE event_id = :eid LIMIT 1"
        ),
        {"eid": str(event_id)},
    )
    row = result.fetchone()
    if row is None:
        return False
    return row[0] in (JobStatus.COMPLETED, JobStatus.RUNNING)


async def upsert_job(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    event_type: str,
    tenant_id: uuid.UUID,
    client_id: uuid.UUID | None = None,
    accounting_period_id: uuid.UUID | None = None,
    status: JobStatus = JobStatus.PENDING,
    error_class: str | None = None,
    error_message: str | None = None,
    attempts: int = 0,
) -> None:
    """Insert or update a worker_jobs row (upsert on event_id)."""
    now = datetime.now(UTC)
    stmt = pg_insert(
        # Reference the table by name to avoid a circular import with backend models
        text("worker_jobs")  # type: ignore[arg-type]
    )
    # Use raw SQL for the upsert to keep workers independent of backend models
    await session.execute(
        text("""
        INSERT INTO worker_jobs
            (id, event_id, event_type, tenant_id, client_id, accounting_period_id,
             status, error_class, error_message, attempts, started_at, created_at)
        VALUES
            (:id, :event_id, :event_type, :tenant_id, :client_id, :period_id,
             :status, :error_class, :error_message, :attempts, :started_at, :created_at)
        ON CONFLICT (event_id) DO UPDATE
            SET status        = EXCLUDED.status,
                error_class   = EXCLUDED.error_class,
                error_message = EXCLUDED.error_message,
                attempts      = EXCLUDED.attempts
        """),
        {
            "id": str(uuid.uuid4()),
            "event_id": str(event_id),
            "event_type": event_type,
            "tenant_id": str(tenant_id),
            "client_id": str(client_id) if client_id else None,
            "period_id": str(accounting_period_id) if accounting_period_id else None,
            "status": status.value,
            "error_class": error_class,
            "error_message": error_message,
            "attempts": attempts,
            "started_at": now,
            "created_at": now,
        },
    )
    await session.commit()


async def mark_job_running(session: AsyncSession, event_id: uuid.UUID) -> None:
    await session.execute(
        text("UPDATE worker_jobs SET status = 'running' WHERE event_id = :eid"),
        {"eid": str(event_id)},
    )
    await session.commit()


async def mark_job_completed(session: AsyncSession, event_id: uuid.UUID) -> None:
    await session.execute(
        text(
            "UPDATE worker_jobs "
            "SET status = 'completed', finished_at = now() "
            "WHERE event_id = :eid"
        ),
        {"eid": str(event_id)},
    )
    await session.commit()


async def mark_job_failed(
    session: AsyncSession,
    event_id: uuid.UUID,
    *,
    error_class: str,
    error_message: str,
    attempts: int,
) -> None:
    await session.execute(
        text(
            "UPDATE worker_jobs "
            "SET status = 'failed', finished_at = now(), "
            "    error_class = :ec, error_message = :em, attempts = :att "
            "WHERE event_id = :eid"
        ),
        {
            "eid": str(event_id),
            "ec": error_class,
            "em": error_message,
            "att": attempts,
        },
    )
    await session.commit()
