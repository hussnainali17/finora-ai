"""Pydantic schemas for Financial Reporting API (Phase 8)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GenerateReportIn(BaseModel):
    currency: str = "PKR"


class ReportSignOffIn(BaseModel):
    notes: str | None = None


class FinancialReportOut(BaseModel):
    id: uuid.UUID
    firm_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    report_type: str
    status: str
    version: int
    data: dict[str, Any]
    validation_results: dict[str, Any]
    excel_object_key: str | None
    pdf_object_key: str | None
    signed_off_by: uuid.UUID | None
    signed_off_at: datetime | None
    sign_off_notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FinancialReportListOut(BaseModel):
    items: list[FinancialReportOut]
    total: int
