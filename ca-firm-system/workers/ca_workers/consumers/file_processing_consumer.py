"""Consumer for 'file-uploaded' events.

Responsibilities:
1. Validate tenant/client context from the envelope.
2. Mark the document status as 'processing' in the database.
3. Enqueue the document for Agent 1 extraction by updating its status so the
   FastAPI outbox loop or a future dedicated extraction worker picks it up.
   (In Phase 5 the extraction is driven by the FastAPI intake loop; here we
   ensure the document record reflects that it has been claimed.)
4. Publish a 'file-processing' event so downstream consumers know work started.

Idempotency: the base class checks worker_jobs before calling process_event.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ca_workers.consumers import BaseConsumer
from ca_workers.event_schemas import (
    FILE_PROCESSING,
    FILE_UPLOADED,
    FileUploadedPayload,
    EventEnvelope,
    envelope_to_bytes,
)

logger = logging.getLogger("worker.file_processing")

CONSUMER_GROUP = "ca-firm-file-processing"


class FileProcessingConsumer(BaseConsumer):
    topic = FILE_UPLOADED
    consumer_group = CONSUMER_GROUP

    async def process_event(
        self, envelope: EventEnvelope, session: AsyncSession  # type: ignore[type-arg]
    ) -> None:
        payload_dict = envelope.payload  # still a plain dict at this layer
        # Validate required fields
        try:
            payload = FileUploadedPayload.model_validate(payload_dict)
        except Exception as exc:
            raise ValueError(f"Invalid FileUploadedPayload: {exc}") from exc

        log_ctx = {
            "event_id": str(envelope.event_id),
            "document_id": str(payload.document_id),
            "client_id": str(payload.client_id),
            "firm_id": str(payload.firm_id),
        }

        # Advance document status from 'queued' -> 'processing'.
        # Only advance if still in 'queued' - never regress.
        result = await session.execute(
            text(
                "UPDATE documents "
                "SET status = 'processing', updated_at = now() "
                "WHERE id = :doc_id "
                "  AND firm_id = :firm_id "
                "  AND status = 'queued' "
                "RETURNING id"
            ),
            {"doc_id": str(payload.document_id), "firm_id": str(payload.firm_id)},
        )
        updated = result.fetchone()
        if updated is None:
            # Already past 'queued' (extracted or failed) - treat as success
            logger.info("document already beyond queued state -- no-op", extra=log_ctx)
            return

        await session.commit()
        logger.info("document marked processing", extra=log_ctx)

        # Publish a file-processing event so the monitoring/status streams know.
        await self._publish_file_processing(envelope, payload)

    async def _publish_file_processing(
        self,
        source_envelope: EventEnvelope,  # type: ignore[type-arg]
        payload: FileUploadedPayload,
    ) -> None:
        processing_envelope = EventEnvelope[FileUploadedPayload](
            event_type="file.processing",
            schema_version=1,
            tenant_id=source_envelope.tenant_id,
            client_id=payload.client_id,
            accounting_period_id=source_envelope.accounting_period_id,
            correlation_id=source_envelope.correlation_id,
            payload=payload,
        )
        try:
            await self._producer.send_and_wait(
                FILE_PROCESSING,
                value=envelope_to_bytes(processing_envelope),
                key=str(payload.document_id).encode(),
            )
        except Exception:
            # Non-fatal - the status update already committed
            logger.exception(
                "failed to publish file-processing event",
                extra={"document_id": str(payload.document_id)},
            )
