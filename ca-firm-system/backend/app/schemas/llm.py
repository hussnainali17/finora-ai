import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import StrictModel

AgentKey = Literal["intake", "accounting_review", "adjustments", "reporting"]


class ModelOut(BaseModel):
    alias: str
    display_name: str
    provider: str
    description: str
    context_window: int
    capabilities: list[str]
    tier: str
    enabled: bool
    available: bool | None
    used_by: list[str]


class ModelsOut(BaseModel):
    models: list[ModelOut]
    config_version: int


class EnableIn(StrictModel):
    enabled: bool


class TaskOut(BaseModel):
    task: str
    description: str
    requires: list[str]
    min_context: int
    effective_alias: str | None
    source: str | None
    override_alias: str | None
    eligible: list[str]


class AgentOut(BaseModel):
    key: str
    label: str
    default_alias: str | None
    fallback_alias: str | None
    eligible: list[str]
    tasks: list[TaskOut]


class AgentsOut(BaseModel):
    agents: list[AgentOut]
    allow_task_overrides: bool
    config_version: int


class AgentConfigIn(StrictModel):
    default_alias: str = Field(min_length=1, max_length=64)
    fallback_alias: str | None = Field(default=None, max_length=64)


class TaskOverrideIn(StrictModel):
    alias: str = Field(min_length=1, max_length=64)


class PolicyIn(StrictModel):
    allow_task_overrides: bool


class VersionOut(BaseModel):
    config_version: int


class UsageOut(BaseModel):
    id: int
    created_at: datetime
    agent: str
    task: str
    requested_alias: str
    alias: str
    provider: str | None
    status: str
    fallback_used: bool
    attempts: int
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cost_usd: Decimal | None
    request_id: str | None
    correlation_id: str | None
    config_version: int | None
    error_class: str | None
    user_id: uuid.UUID | None
    client_id: uuid.UUID | None


class UsageSummaryRow(BaseModel):
    alias: str
    agent: str
    calls: int
    errors: int
    fallbacks: int
    tokens: int
    cost_usd: Decimal | None
    avg_latency_ms: float | None


class ModelTestOut(BaseModel):
    ok: bool
    alias: str
    latency_ms: int | None
    attempts: int | None
    error_code: str | None
