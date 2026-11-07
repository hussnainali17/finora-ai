"""Pydantic schemas for Period-End Adjustments API (Phase 7)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class AdjustmentCreateIn(BaseModel):
    category: str = Field(description="accruals, prepayments, depreciation, provisions, or other")
    debit_account_code: str
    debit_account_name: str
    credit_account_code: str
    credit_account_name: str
    amount: Decimal = Field(gt=Decimal("0"))
    currency: str = "PKR"
    accounting_rationale: str
    calculation_details: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)


class AdjustmentUpdateIn(BaseModel):
    debit_account_code: str | None = None
    debit_account_name: str | None = None
    credit_account_code: str | None = None
    credit_account_name: str | None = None
    amount: Decimal | None = Field(default=None, gt=Decimal("0"))
    accounting_rationale: str | None = None
    calculation_details: dict[str, Any] | None = None


class AdjustmentDecisionIn(BaseModel):
    decision: str = Field(description="'approved' or 'rejected'")
    comments: str | None = None


class PeriodAdjustmentOut(BaseModel):
    id: uuid.UUID
    firm_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    category: str
    status: str
    version: int
    debit_account_code: str
    debit_account_name: str
    credit_account_code: str
    credit_account_name: str
    amount: Decimal
    currency: str
    accounting_rationale: str
    calculation_details: dict[str, Any]
    source_refs: list[Any]
    prepared_by_agent: str
    created_by: uuid.UUID | None
    reviewer_id: uuid.UUID | None
    reviewed_at: datetime | None
    reviewer_decision: str | None
    reviewer_comments: str | None
    history: list[Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdjustmentListOut(BaseModel):
    items: list[PeriodAdjustmentOut]
    total: int
