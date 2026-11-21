"""Pydantic schemas for the Central Shared Data Layer."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApprovedModuleOutputOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    firm_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    module: str
    output_type: str
    version: int
    status: str
    data: dict[str, Any]
    summary: dict[str, Any]
    source_version_refs: dict[str, Any]
    validation_results: dict[str, Any]
    is_outdated: bool
    stale_reason: str | None = None
    signed_off_by: uuid.UUID | None = None
    signed_off_at: datetime | None = None
    sign_off_notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ApprovedModuleOutputListOut(BaseModel):
    items: list[ApprovedModuleOutputOut]
    total: int


class PublishAccountingOutputIn(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)
