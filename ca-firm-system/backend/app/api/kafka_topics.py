"""Kafka topic and consumer group inspection endpoint (Phase 5)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import PrincipalDep, requires
from app.integrations.kafka import (
    ACCOUNTING_REVIEW_REQUESTED,
    ADJUSTMENT_CALCULATION_REQUESTED,
    CA_APPROVAL_EVENTS,
    DATA_STRUCTURED,
    DLQ_SUFFIX,
    FILE_PROCESSING,
    FILE_UPLOADED,
    RECONCILIATION_REQUESTED,
    REPORT_GENERATION_REQUESTED,
    WORKFLOW_STATUS,
)

router = APIRouter(prefix="/kafka", tags=["kafka"])


class KafkaTopicInfo(BaseModel):
    name: str
    description: str
    dlq_topic: str


class KafkaConfigOut(BaseModel):
    topics: list[KafkaTopicInfo]
    consumer_groups: list[str]


TOPIC_CATALOG = [
    KafkaTopicInfo(
        name=FILE_UPLOADED,
        description="Fired after client file upload completes and metadata is persisted in PostgreSQL",
        dlq_topic=f"{FILE_UPLOADED}{DLQ_SUFFIX}",
    ),
    KafkaTopicInfo(
        name=FILE_PROCESSING,
        description="Emitted when a worker claims a document for Agent 1 processing",
        dlq_topic=f"{FILE_PROCESSING}{DLQ_SUFFIX}",
    ),
    KafkaTopicInfo(
        name=DATA_STRUCTURED,
        description="Emitted when Agent 1 finishes table extraction and structuring",
        dlq_topic=f"{DATA_STRUCTURED}{DLQ_SUFFIX}",
    ),
    KafkaTopicInfo(
        name=ACCOUNTING_REVIEW_REQUESTED,
        description="Triggers Agent 2 accounting review and reconciliation",
        dlq_topic=f"{ACCOUNTING_REVIEW_REQUESTED}{DLQ_SUFFIX}",
    ),
    KafkaTopicInfo(
        name=RECONCILIATION_REQUESTED,
        description="Triggers module-specific reconciliation (e.g. AR ageing, bank recon)",
        dlq_topic=f"{RECONCILIATION_REQUESTED}{DLQ_SUFFIX}",
    ),
    KafkaTopicInfo(
        name=ADJUSTMENT_CALCULATION_REQUESTED,
        description="Triggers Agent 3 period-end adjustment calculations",
        dlq_topic=f"{ADJUSTMENT_CALCULATION_REQUESTED}{DLQ_SUFFIX}",
    ),
    KafkaTopicInfo(
        name=CA_APPROVAL_EVENTS,
        description="Audit events for CA approval or rejection of period-end adjustments",
        dlq_topic=f"{CA_APPROVAL_EVENTS}{DLQ_SUFFIX}",
    ),
    KafkaTopicInfo(
        name=REPORT_GENERATION_REQUESTED,
        description="Triggers Agent 4 financial reporting generation",
        dlq_topic=f"{REPORT_GENERATION_REQUESTED}{DLQ_SUFFIX}",
    ),
    KafkaTopicInfo(
        name=WORKFLOW_STATUS,
        description="Workflow progress events for LangGraph and UI coordination",
        dlq_topic=f"{WORKFLOW_STATUS}{DLQ_SUFFIX}",
    ),
]

CONSUMER_GROUPS = [
    "ca-firm-file-processing",
    "ca-firm-accounting-review",
    "ca-firm-reporting",
]


@router.get(
    "/topics",
    response_model=KafkaConfigOut,
    summary="Get Kafka topics and consumer groups configuration",
)
async def get_kafka_topics(
    principal: PrincipalDep = Depends(requires("user:manage")),
) -> KafkaConfigOut:
    return KafkaConfigOut(
        topics=TOPIC_CATALOG,
        consumer_groups=CONSUMER_GROUPS,
    )
