"""Base Kafka consumer with idempotency, bounded retries and dead-letter routing.

Design:
- One AIOKafkaConsumer per subclass instance.
- ``process_event`` is the single override point for business logic.
- Idempotency: ``worker_jobs`` table (via ``jobs`` module) ensures duplicate
  Kafka delivery of the same event_id is a no-op.
- Retries: up to ``max_retries`` attempts with exponential back-off (pure Python
  asyncio.sleep — no tenacity dependency needed).
- Dead-letter: after max retries the raw message bytes are published to
  ``{topic}-dlq`` using an AIOKafkaProducer so the bad message is never lost.
- Graceful shutdown: ``stop`` asyncio.Event signals the run loop to exit cleanly
  after the current batch, then the consumer is committed and closed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ca_workers.event_schemas import DLQ_SUFFIX, EventEnvelope, bytes_to_envelope
from ca_workers.jobs import (
    JobStatus,
    is_already_processed,
    mark_job_completed,
    mark_job_failed,
    mark_job_running,
    upsert_job,
)

logger = logging.getLogger("worker.consumer")


class BaseConsumer(ABC):
    """Abstract base for all Kafka consumers in the workers package."""

    topic: str  # subclass must set at class level
    consumer_group: str  # subclass must set at class level

    def __init__(
        self,
        bootstrap_servers: str,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_retries: int = 3,
        retry_backoff_ms: int = 500,
        auto_offset_reset: str = "earliest",
        session_timeout_ms: int = 30_000,
        max_poll_interval_ms: int = 300_000,
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._session_factory = session_factory
        self._max_retries = max_retries
        self._retry_backoff_ms = retry_backoff_ms
        self._auto_offset_reset = auto_offset_reset
        self._session_timeout_ms = session_timeout_ms
        self._max_poll_interval_ms = max_poll_interval_ms
        self._consumer: Any = None
        self._producer: Any = None  # for DLQ publishing

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

        self._consumer = AIOKafkaConsumer(
            self.topic,
            bootstrap_servers=self._bootstrap,
            group_id=self.consumer_group,
            auto_offset_reset=self._auto_offset_reset,
            enable_auto_commit=False,
            session_timeout_ms=self._session_timeout_ms,
            max_poll_interval_ms=self._max_poll_interval_ms,
        )
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap,
            acks="all",
            enable_idempotence=True,
        )
        await self._consumer.start()
        await self._producer.start()
        logger.info(
            "consumer started",
            extra={"topic": self.topic, "group": self.consumer_group},
        )

    async def stop(self) -> None:
        if self._consumer is not None:
            try:
                await self._consumer.stop()
            except Exception:
                logger.exception("error stopping consumer")
        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception:
                logger.exception("error stopping dlq producer")
        logger.info("consumer stopped", extra={"topic": self.topic})

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    async def run(self, stop: asyncio.Event) -> None:
        """Poll Kafka until ``stop`` is set, then commit and exit."""
        await self.start()
        try:
            while not stop.is_set():
                try:
                    # Short timeout so we can check stop frequently
                    result = await asyncio.wait_for(
                        self._consumer.getmany(timeout_ms=1_000, max_records=10),
                        timeout=2.0,
                    )
                except TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break

                for _tp, messages in result.items():
                    for msg in messages:
                        await self._handle_message(msg)

                # Manual commit after the batch is processed
                try:
                    await self._consumer.commit()
                except Exception:
                    logger.exception("offset commit failed")
        finally:
            await self.stop()

    # ------------------------------------------------------------------
    # Internal message dispatch
    # ------------------------------------------------------------------

    async def _handle_message(self, msg: Any) -> None:
        """Parse, deduplicate and dispatch one Kafka message."""
        raw: bytes = msg.value
        try:
            envelope = bytes_to_envelope(raw)
        except Exception as exc:
            logger.error(
                "malformed event — routing to DLQ immediately",
                extra={"topic": self.topic, "error": str(exc)},
            )
            await self._publish_dlq(raw, reason=f"parse_error:{type(exc).__name__}")
            return

        event_id = uuid.UUID(str(envelope.event_id))
        log_ctx = {
            "event_id": str(event_id),
            "event_type": envelope.event_type,
            "topic": self.topic,
            "tenant_id": str(envelope.tenant_id),
        }

        async with self._session_factory() as session:
            if await is_already_processed(session, event_id):
                logger.info("duplicate event skipped", extra=log_ctx)
                return

            await upsert_job(
                session,
                event_id=event_id,
                event_type=envelope.event_type,
                tenant_id=uuid.UUID(str(envelope.tenant_id)),
                client_id=uuid.UUID(str(envelope.client_id)) if envelope.client_id else None,
                accounting_period_id=(
                    uuid.UUID(str(envelope.accounting_period_id))
                    if envelope.accounting_period_id
                    else None
                ),
                status=JobStatus.PENDING,
            )

        for attempt in range(1, self._max_retries + 1):
            async with self._session_factory() as session:
                try:
                    await mark_job_running(session, event_id)
                    await self.process_event(envelope, session)
                    await mark_job_completed(session, event_id)
                    logger.info("event processed", extra={**log_ctx, "attempt": attempt})
                    return
                except Exception as exc:
                    error_cls = type(exc).__name__
                    logger.warning(
                        "event processing failed",
                        extra={**log_ctx, "attempt": attempt, "error": error_cls},
                    )
                    if attempt >= self._max_retries:
                        async with self._session_factory() as s2:
                            await mark_job_failed(
                                s2,
                                event_id,
                                error_class=error_cls,
                                error_message=str(exc)[:500],
                                attempts=attempt,
                            )
                        await self._publish_dlq(
                            raw, reason=f"{error_cls}:{str(exc)[:200]}"
                        )
                        return

            backoff = (self._retry_backoff_ms / 1000) * (2 ** (attempt - 1))
            await asyncio.sleep(backoff)

    async def _publish_dlq(self, raw: bytes, *, reason: str) -> None:
        dlq_topic = self.topic + DLQ_SUFFIX
        try:
            await self._producer.send_and_wait(
                dlq_topic,
                value=raw,
                headers=[("dlq_reason", reason.encode()[:200])],
            )
            logger.warning(
                "event routed to DLQ", extra={"dlq_topic": dlq_topic, "reason": reason[:200]}
            )
        except Exception:
            logger.exception("failed to publish to DLQ", extra={"dlq_topic": dlq_topic})

    # ------------------------------------------------------------------
    # Override point
    # ------------------------------------------------------------------

    @abstractmethod
    async def process_event(
        self, envelope: EventEnvelope, session: AsyncSession  # type: ignore[type-arg]
    ) -> None:
        """Business logic. Raise on failure; the base class handles retries."""
        ...

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def is_healthy(self) -> bool:
        return self._consumer is not None
