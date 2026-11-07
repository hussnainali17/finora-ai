"""Kafka integration utilities and topic definitions."""

from app.integrations.kafka.publisher import EventEnvelope, EventPublisher, KafkaEventPublisher, get_event_publisher

FILE_UPLOADED = "file-uploaded"
FILE_PROCESSING = "file-processing"
DATA_STRUCTURED = "data-structured"
ACCOUNTING_REVIEW_REQUESTED = "accounting-review-requested"
RECONCILIATION_REQUESTED = "reconciliation-requested"
ADJUSTMENT_CALCULATION_REQUESTED = "adjustment-calculation-requested"
CA_APPROVAL_EVENTS = "ca-approval-events"
REPORT_GENERATION_REQUESTED = "report-generation-requested"
WORKFLOW_STATUS = "workflow-status"
DLQ_SUFFIX = "-dlq"

__all__ = [
    "EventEnvelope",
    "EventPublisher",
    "KafkaEventPublisher",
    "get_event_publisher",
    "FILE_UPLOADED",
    "FILE_PROCESSING",
    "DATA_STRUCTURED",
    "ACCOUNTING_REVIEW_REQUESTED",
    "RECONCILIATION_REQUESTED",
    "ADJUSTMENT_CALCULATION_REQUESTED",
    "CA_APPROVAL_EVENTS",
    "REPORT_GENERATION_REQUESTED",
    "WORKFLOW_STATUS",
    "DLQ_SUFFIX",
]
