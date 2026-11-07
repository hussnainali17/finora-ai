"""Consumer for 'accounting-review-requested' events."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ca_workers.consumers import BaseConsumer
from ca_workers.event_schemas import (
    ACCOUNTING_REVIEW_REQUESTED,
    AccountingReviewRequestedPayload,
    EventEnvelope,
)

logger = logging.getLogger("worker.review")

CONSUMER_GROUP = "ca-firm-accounting-review"


class ReviewConsumer(BaseConsumer):
    topic = ACCOUNTING_REVIEW_REQUESTED
    consumer_group = CONSUMER_GROUP

    async def process_event(
        self, envelope: EventEnvelope, session: AsyncSession  # type: ignore[type-arg]
    ) -> None:
        try:
            payload = AccountingReviewRequestedPayload.model_validate(envelope.payload)
        except Exception as exc:
            raise ValueError(f"Invalid AccountingReviewRequestedPayload: {exc}") from exc

        log_ctx = {
            "event_id": str(envelope.event_id),
            "review_run_id": str(payload.review_run_id),
            "client_id": str(payload.client_id),
            "firm_id": str(payload.firm_id),
        }
        logger.info("review event received", extra=log_ctx)

        # Advance review_run from 'pending' to 'running'.
        result = await session.execute(
            text(
                "UPDATE review_runs "
                "SET status = 'running', started_at = now(), updated_at = now() "
                "WHERE id = :run_id AND firm_id = :firm_id AND status = 'pending' "
                "RETURNING id"
            ),
            {"run_id": str(payload.review_run_id), "firm_id": str(payload.firm_id)},
        )
        if result.fetchone() is None:
            logger.info("review_run not in pending state - skipping", extra=log_ctx)
            return

        await session.commit()
        logger.info("review_run marked running -- backend agent loop will execute", extra=log_ctx)
