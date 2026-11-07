"""Transactional outbox relay.

``enqueue_event`` runs inside the caller's transaction, so an event row exists if and only if the
business change committed (an upload that fails never produces an event). The relay then publishes
pending rows to Kafka. It is safe to run in many processes (``FOR UPDATE SKIP LOCKED``) and is
at-least-once: if a crash happens after Kafka accepted a message but before ``published_at`` is
written, the same ``event_id`` is sent again - consumers deduplicate on it."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import correlation_id_var
from app.integrations.kafka.publisher import EventEnvelope, EventPublisher
from app.models import Document, OutboxEvent

logger = logging.getLogger("app.outbox")
MAX_BACKOFF_SECONDS = 300


def enqueue_event(
    session: AsyncSession,
    *,
    topic: str,
    event_type: str,
    partition_key: str,
    firm_id: uuid.UUID,
    client_id: uuid.UUID | None,
    period_id: uuid.UUID | None,
    payload: dict[str, Any],
    schema_version: int = 1,
) -> OutboxEvent:
    event = OutboxEvent(
        id=uuid.uuid4(),
        topic=topic,
        event_type=event_type,
        schema_version=schema_version,
        partition_key=partition_key,
        firm_id=firm_id,
        client_id=client_id,
        accounting_period_id=period_id,
        correlation_id=correlation_id_var.get(),
        payload=payload,
    )
    session.add(event)
    return event


def _envelope(row: OutboxEvent) -> EventEnvelope:
    return EventEnvelope(
        event_id=row.id,
        event_type=row.event_type,
        schema_version=row.schema_version,
        tenant_id=row.firm_id,
        client_id=row.client_id,
        accounting_period_id=row.accounting_period_id,
        correlation_id=row.correlation_id,
        occurred_at=row.occurred_at,
        payload=row.payload,
    )


async def publish_pending(
    session_factory: async_sessionmaker[AsyncSession],
    publisher: EventPublisher,
    *,
    batch_size: int = 50,
) -> int:
    """Publishes due outbox rows. Returns how many were published."""
    published = 0
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.published_at.is_(None),
                    OutboxEvent.next_attempt_at <= datetime.now(UTC),
                )
                .order_by(OutboxEvent.occurred_at)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for row in rows:
            try:
                await publisher.publish(row.topic, row.partition_key, _envelope(row))
            except Exception as exc:
                row.attempts += 1
                row.last_error = f"{type(exc).__name__}"  # class only: no endpoints/secrets
                delay = min(2**row.attempts, MAX_BACKOFF_SECONDS)
                row.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
                logger.warning(
                    "outbox publish failed",
                    extra={
                        "event_id": str(row.id),
                        "attempts": row.attempts,
                        "error": row.last_error,
                    },
                )
                continue
            now = datetime.now(UTC)
            row.published_at = now
            row.last_error = None
            if row.event_type == "file.uploaded":
                # Only advance a document that is still waiting; never regress later states.
                await session.execute(
                    update(Document)
                    .where(
                        Document.id == uuid.UUID(row.payload["document_id"]),
                        Document.status == "uploaded",
                    )
                    .values(status="queued")
                )
            published += 1
        await session.commit()
    return published


async def run_relay(
    session_factory: async_sessionmaker[AsyncSession],
    publisher: EventPublisher,
    *,
    interval_seconds: float,
    stop: asyncio.Event,
) -> None:
    """Background loop owned by the FastAPI lifespan."""
    while not stop.is_set():
        try:
            await publish_pending(session_factory, publisher)
        except Exception:
            logger.exception("outbox relay iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
