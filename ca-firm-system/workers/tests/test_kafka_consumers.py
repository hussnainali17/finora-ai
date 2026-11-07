"""Tests for Phase 5: Kafka consumer infrastructure.

Tests verify:
- Idempotency: duplicate events are silently skipped
- Malformed events go to DLQ immediately
- Worker job state correctly transitions
- Consumer health check
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ca_workers.event_schemas import (
    FileUploadedPayload,
    EventEnvelope,
    FILE_UPLOADED,
    envelope_to_bytes,
    bytes_to_envelope,
)
from ca_workers.jobs import JobStatus


# ---------------------------------------------------------------------------
# Event schema serialisation
# ---------------------------------------------------------------------------


class TestEventSchemas:
    def test_roundtrip_serialisation(self):
        payload = FileUploadedPayload(
            document_id=uuid.uuid4(),
            client_id=uuid.uuid4(),
            period_id=uuid.uuid4(),
            firm_id=uuid.uuid4(),
            object_key="firms/abc/docs/file.pdf",
            category="trial_balance",
            original_filename="TB_2024.pdf",
            content_type="application/pdf",
            sha256="a" * 64,
        )
        envelope = EventEnvelope[FileUploadedPayload](
            event_type="file.uploaded",
            schema_version=1,
            tenant_id=payload.firm_id,
            client_id=payload.client_id,
            accounting_period_id=payload.period_id,
            payload=payload,
        )
        raw = envelope_to_bytes(envelope)
        parsed = json.loads(raw.decode())
        assert parsed["event_type"] == "file.uploaded"
        assert parsed["schema_version"] == 1
        assert "event_id" in parsed
        assert parsed["payload"]["category"] == "trial_balance"

    def test_bytes_to_envelope_parses_correctly(self):
        event_id = uuid.uuid4()
        firm_id = uuid.uuid4()
        raw = json.dumps({
            "event_id": str(event_id),
            "event_type": "file.uploaded",
            "schema_version": 1,
            "tenant_id": str(firm_id),
            "client_id": None,
            "accounting_period_id": None,
            "correlation_id": "corr-123",
            "occurred_at": datetime.utcnow().isoformat(),
            "payload": {"key": "value"},
        }).encode()
        envelope = bytes_to_envelope(raw)
        assert str(envelope.event_id) == str(event_id)
        assert envelope.event_type == "file.uploaded"
        assert str(envelope.tenant_id) == str(firm_id)

    def test_malformed_bytes_raises(self):
        with pytest.raises(Exception):
            bytes_to_envelope(b"not-valid-json}")

    def test_topic_constants_defined(self):
        from ca_workers.event_schemas import (
            FILE_UPLOADED, FILE_PROCESSING, DATA_STRUCTURED,
            ACCOUNTING_REVIEW_REQUESTED, WORKFLOW_STATUS, DLQ_SUFFIX
        )
        assert FILE_UPLOADED == "file-uploaded"
        assert DLQ_SUFFIX == "-dlq"
        assert ACCOUNTING_REVIEW_REQUESTED == "accounting-review-requested"


# ---------------------------------------------------------------------------
# Job state helpers (unit tests with mocked DB)
# ---------------------------------------------------------------------------


class TestJobState:
    @pytest.mark.asyncio
    async def test_is_already_processed_returns_false_for_unknown_event(self):
        """An event not in worker_jobs is not already processed."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_session.execute.return_value = mock_result

        from ca_workers.jobs import is_already_processed
        result = await is_already_processed(mock_session, uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_is_already_processed_returns_true_for_completed(self):
        """A completed event must not be processed again."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ("completed",)
        mock_session.execute.return_value = mock_result

        from ca_workers.jobs import is_already_processed
        result = await is_already_processed(mock_session, uuid.uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_is_already_processed_returns_true_for_running(self):
        """A running event (in-progress) is treated as already claimed."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ("running",)
        mock_session.execute.return_value = mock_result

        from ca_workers.jobs import is_already_processed
        result = await is_already_processed(mock_session, uuid.uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_is_already_processed_returns_false_for_failed(self):
        """Failed events can be retried (not treated as already processed)."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ("failed",)
        mock_session.execute.return_value = mock_result

        from ca_workers.jobs import is_already_processed
        result = await is_already_processed(mock_session, uuid.uuid4())
        assert result is False


# ---------------------------------------------------------------------------
# BaseConsumer idempotency (unit tests)
# ---------------------------------------------------------------------------


class TestBaseConsumerIdempotency:
    """Verify the base consumer skips already-processed events."""

    @pytest.mark.asyncio
    async def test_duplicate_event_is_skipped(self):
        """When is_already_processed returns True, process_event must NOT be called."""
        from ca_workers.consumers import BaseConsumer

        class _MockConsumer(BaseConsumer):
            topic = FILE_UPLOADED
            consumer_group = "test-group"

            async def process_event(self, envelope, session):
                raise AssertionError("process_event must not be called for duplicate")

        consumer = _MockConsumer(
            bootstrap_servers="localhost:9092",
            session_factory=MagicMock(),
        )

        event_id = uuid.uuid4()
        payload = {
            "document_id": str(uuid.uuid4()),
            "client_id": str(uuid.uuid4()),
            "period_id": str(uuid.uuid4()),
            "firm_id": str(uuid.uuid4()),
            "object_key": "key",
            "category": "trial_balance",
            "original_filename": "f.xlsx",
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "sha256": "a" * 64,
        }
        raw = json.dumps({
            "event_id": str(event_id),
            "event_type": "file.uploaded",
            "schema_version": 1,
            "tenant_id": str(uuid.uuid4()),
            "client_id": str(uuid.uuid4()),
            "accounting_period_id": None,
            "correlation_id": None,
            "occurred_at": datetime.utcnow().isoformat(),
            "payload": payload,
        }).encode()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        # Simulate already processed
        mock_result.fetchone.return_value = ("completed",)
        mock_session.execute.return_value = mock_result

        mock_session_factory = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_ctx.__aexit__.return_value = None
        mock_session_factory.return_value = mock_ctx

        consumer._session_factory = mock_session_factory

        # Create a mock message
        mock_msg = MagicMock()
        mock_msg.value = raw

        # Must not raise because process_event is never called
        await consumer._handle_message(mock_msg)

    @pytest.mark.asyncio
    async def test_malformed_event_goes_to_dlq(self):
        """Non-JSON bytes must be routed to DLQ without calling process_event."""
        from ca_workers.consumers import BaseConsumer

        dlq_calls = []

        class _MockConsumer(BaseConsumer):
            topic = FILE_UPLOADED
            consumer_group = "test-group"

            async def process_event(self, envelope, session):
                raise AssertionError("Must not reach process_event for malformed events")

            async def _publish_dlq(self, raw, *, reason):
                dlq_calls.append(reason)

        consumer = _MockConsumer(
            bootstrap_servers="localhost:9092",
            session_factory=MagicMock(),
        )

        mock_msg = MagicMock()
        mock_msg.value = b"totally {not valid} json!!!"

        await consumer._handle_message(mock_msg)

        assert len(dlq_calls) == 1
        assert "parse_error" in dlq_calls[0]


# ---------------------------------------------------------------------------
# Worker health check
# ---------------------------------------------------------------------------


class TestWorkerHealth:
    def test_consumer_is_unhealthy_before_start(self):
        from ca_workers.consumers import BaseConsumer

        class _MockConsumer(BaseConsumer):
            topic = FILE_UPLOADED
            consumer_group = "test"

            async def process_event(self, envelope, session):
                pass

        consumer = _MockConsumer("localhost:9092", MagicMock())
        assert consumer.is_healthy() is False

    def test_consumer_is_healthy_after_start(self):
        from ca_workers.consumers import BaseConsumer

        class _MockConsumer(BaseConsumer):
            topic = FILE_UPLOADED
            consumer_group = "test"

            async def process_event(self, envelope, session):
                pass

        consumer = _MockConsumer("localhost:9092", MagicMock())
        consumer._consumer = MagicMock()  # simulate started
        assert consumer.is_healthy() is True
