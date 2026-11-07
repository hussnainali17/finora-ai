"""Pydantic schemas for the Accounting Review API (Phase 6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class TriggerReviewIn(BaseModel):
    """Request body for POST /review — trigger a new review run."""

    # Optionally restrict to specific modules (empty = run all)
    modules: list[str] = Field(default_factory=list)


class FindingStatusUpdate(BaseModel):
    status: str  # "open" | "explained" | "resolved" | "escalated"
    reviewer_note: str | None = None


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class ModuleSummaryOut(BaseModel):
    status: str
    finding_count: int
    exception_count: int
    error: str | None = None


class ReviewRunOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    firm_id: uuid.UUID
    status: str
    trigger: str
    triggered_by: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    module_summary: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewRunListOut(BaseModel):
    items: list[ReviewRunOut]
    total: int


class EvidenceRefOut(BaseModel):
    document_id: str | None = None
    table_id: str | None = None
    row_index: int | None = None
    description: str = ""


class ReviewFindingOut(BaseModel):
    id: uuid.UUID
    review_run_id: uuid.UUID
    firm_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    module: str
    finding_type: str
    severity: str
    title: str
    description: str
    source_ref: dict[str, Any]
    amount: Decimal | None
    currency: str | None
    status: str
    reviewer_id: uuid.UUID | None
    reviewed_at: datetime | None
    reviewer_note: str | None
    evidence_refs: list[Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewFindingListOut(BaseModel):
    items: list[ReviewFindingOut]
    total: int


class ReconciliationScheduleOut(BaseModel):
    id: uuid.UUID
    review_run_id: uuid.UUID
    firm_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    module: str
    schedule_type: str
    label: str
    data: dict[str, Any]
    generated_at: datetime
    source_refs: list[Any]

    model_config = {"from_attributes": True}
