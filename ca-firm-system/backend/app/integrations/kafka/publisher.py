"""Event publishing. Phase 2 needs only a producer; consumers, topic management, retries and
dead-lettering are Phase 5. Delivery is AT-LEAST-ONCE: consumers must dedupe on ``event_id``."""

import json
import uuid
from datetime import datetime
from functools import lru_cache
from typing import Any, Protocol

from pydantic import BaseModel

from app.core.config import get_settings


class EventEnvelope(BaseModel):
    """Versioned event envelope (the shape Phase 5 standardises on). Payloads carry IDs and object
    keys only - never document contents or secrets."""

    event_id: uuid.UUID
    event_type: str
    schema_version: int
    tenant_id: uuid.UUID
    client_id: uuid.UUID | None
    accounting_period_id: uuid.UUID | None
    correlation_id: str | None
    occurred_at: datetime
    payload: dict[str, Any]


class EventPublisher(Protocol):
    async def publish(self, topic: str, key: str, event: EventEnvelope) -> None: ...


class KafkaEventPublisher:
    """aiokafka producer with acks=all and idempotence (broker retries cannot duplicate)."""

    def __init__(self, bootstrap_servers: str) -> None:
        self._bootstrap = bootstrap_servers
        self._producer: Any = None

    async def _ensure(self) -> Any:
        if self._producer is None:
            from aiokafka import AIOKafkaProducer

            producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap,
                acks="all",
                enable_idempotence=True,
                request_timeout_ms=10_000,
            )
            await producer.start()
            self._producer = producer
        return self._producer

    async def publish(self, topic: str, key: str, event: EventEnvelope) -> None:
        producer = await self._ensure()
        try:
            await producer.send_and_wait(
                topic,
                value=json.dumps(event.model_dump(mode="json")).encode(),
                key=key.encode(),
                headers=[
                    ("event_id", str(event.event_id).encode()),
                    ("event_type", event.event_type.encode()),
                    ("schema_version", str(event.schema_version).encode()),
                ],
            )
        except Exception:
            # Drop the producer so the next attempt reconnects after a broker outage.
            self._producer = None
            try:
                await producer.stop()
            except Exception:  # noqa: S110
                pass
            raise

    async def close(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None


@lru_cache
def get_event_publisher() -> EventPublisher:
    return KafkaEventPublisher(get_settings().kafka_bootstrap_servers)
