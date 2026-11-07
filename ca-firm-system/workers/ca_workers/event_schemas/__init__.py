"""Versioned event schemas for Kafka messages.

Rules (enforced here and in consumers):
- Payloads carry IDs and object keys only — never document contents or secrets.
- Every envelope has a stable event_id (UUID) used for consumer-side idempotency.
- schema_version allows non-breaking evolution (add optional fields only).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Topic constants
# ---------------------------------------------------------------------------

FILE_UPLOADED = "file-uploaded"
FILE_PROCESSING = "file-processing"
DATA_STRUCTURED = "data-structured"
ACCOUNTING_REVIEW_REQUESTED = "accounting-review-requested"
RECONCILIATION_REQUESTED = "reconciliation-requested"
ADJUSTMENT_CALCULATION_REQUESTED = "adjustment-calculation-requested"
CA_APPROVAL_EVENTS = "ca-approval-events"
REPORT_GENERATION_REQUESTED = "report-generation-requested"
WORKFLOW_STATUS = "workflow-status"

# Dead-letter queues: topic + DLQ_SUFFIX
DLQ_SUFFIX = "-dlq"

ALL_TOPICS = [
    FILE_UPLOADED,
    FILE_PROCESSING,
    DATA_STRUCTURED,
    ACCOUNTING_REVIEW_REQUESTED,
    RECONCILIATION_REQUESTED,
    ADJUSTMENT_CALCULATION_REQUESTED,
    CA_APPROVAL_EVENTS,
    REPORT_GENERATION_REQUESTED,
    WORKFLOW_STATUS,
]

# ---------------------------------------------------------------------------
# Generic envelope
# ---------------------------------------------------------------------------

P = TypeVar("P", bound=BaseModel)


class EventEnvelope(BaseModel, Generic[P]):
    """Every Kafka message is wrapped in this envelope.

    Consumers must deduplicate on ``event_id`` before processing the payload.
    """

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: str
    schema_version: int = 1
    tenant_id: uuid.UUID          # firm_id
    client_id: uuid.UUID | None = None
    accounting_period_id: uuid.UUID | None = None
    correlation_id: str | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    payload: P


# ---------------------------------------------------------------------------
# Payload models
# ---------------------------------------------------------------------------

class FileUploadedPayload(BaseModel):
    document_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    firm_id: uuid.UUID
    object_key: str
    category: str
    original_filename: str
    content_type: str
    sha256: str


class DataStructuredPayload(BaseModel):
    extraction_run_id: uuid.UUID
    document_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    firm_id: uuid.UUID
    table_count: int = 0
    finding_count: int = 0
    status: str  # "completed" | "failed"


class AccountingReviewRequestedPayload(BaseModel):
    review_run_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    firm_id: uuid.UUID


REVIEW_MODULES = (
    "sales_receivables",
    "purchases_payables",
    "bank_cash",
    "inventory",
    "fixed_assets",
    "payroll",
)


class ReconciliationRequestedPayload(BaseModel):
    review_run_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    firm_id: uuid.UUID
    module: str  # one of REVIEW_MODULES


class WorkflowStatusPayload(BaseModel):
    workflow_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    firm_id: uuid.UUID
    status: str
    step: str
    message: str = ""


# ---------------------------------------------------------------------------
# Typed aliases (convenience)
# ---------------------------------------------------------------------------

FileUploadedEvent = EventEnvelope[FileUploadedPayload]
DataStructuredEvent = EventEnvelope[DataStructuredPayload]
AccountingReviewRequestedEvent = EventEnvelope[AccountingReviewRequestedPayload]
ReconciliationRequestedEvent = EventEnvelope[ReconciliationRequestedPayload]
WorkflowStatusEvent = EventEnvelope[WorkflowStatusPayload]


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def envelope_to_bytes(envelope: EventEnvelope) -> bytes:  # type: ignore[type-arg]
    """Serialise envelope to UTF-8 JSON bytes for Kafka producers."""
    import json
    return json.dumps(envelope.model_dump(mode="json")).encode()


def bytes_to_envelope(data: bytes) -> EventEnvelope:  # type: ignore[type-arg]
    """Deserialise raw Kafka message bytes to an untyped envelope dict.

    Callers validate the payload against the concrete payload model after
    reading ``event_type``.
    """
    import json
    parsed = json.loads(data.decode())
    # Return as a generic envelope with payload as plain dict
    return EventEnvelope[dict](  # type: ignore[type-arg]
        event_id=parsed["event_id"],
        event_type=parsed["event_type"],
        schema_version=parsed.get("schema_version", 1),
        tenant_id=parsed["tenant_id"],
        client_id=parsed.get("client_id"),
        accounting_period_id=parsed.get("accounting_period_id"),
        correlation_id=parsed.get("correlation_id"),
        occurred_at=parsed["occurred_at"],
        payload=parsed["payload"],
    )
