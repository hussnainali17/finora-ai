"""Schemas for Central Document Intelligence layer."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ModuleType = Literal["accounting", "taxation", "audit", "general"]


class DocumentIntelligenceMetadata(BaseModel):
    document_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    firm_id: uuid.UUID
    module: str = "accounting"
    category: str
    user_category: str
    detected_category: str | None = None
    category_confidence: float = 0.0
    category_mismatch: bool = False
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    ocr_applied: bool = False
    tables_count: int = 0
    rows_count: int = 0
    findings_count: int = 0
    created_at: datetime
    updated_at: datetime


class ModuleRoutingRequest(BaseModel):
    document_id: uuid.UUID
    target_module: ModuleType
    target_category: str | None = None
    notes: str | None = None


class SharedDocumentReferenceOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    firm_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    module: str
    module_category: str
    status: str
    original_filename: str | None = None
    created_at: datetime
    notes: str | None = None


class CategoryMismatchReport(BaseModel):
    document_id: uuid.UUID
    filename: str
    selected_category: str
    detected_category: str
    confidence: float
    is_mismatch: bool
    explanation: str
    warnings: list[str] = Field(default_factory=list)


class IngestionBatchSummary(BaseModel):
    total_files: int
    successful_files: int
    failed_files: int
    mismatches_detected: int
    documents: list[DocumentIntelligenceMetadata] = Field(default_factory=list)
