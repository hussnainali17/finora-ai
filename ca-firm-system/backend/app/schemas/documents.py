import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DocumentModule = Literal["accounting", "taxation", "audit", "general"]

# Accounting Categories (10 categories preserved)
AccountingCategory = Literal[
    "trial_balance",
    "general_ledger",
    "bank_statement",
    "invoice",
    "receipt",
    "contract",
    "fixed_asset_schedule",
    "inventory_report",
    "payroll_schedule",
    "other",
]

# Taxation Categories (7 categories)
TaxationCategory = Literal[
    "tax_return",
    "withholding_certificate",
    "sales_tax_return",
    "tax_payment_challan",
    "tax_notice",
    "tax_exemption_certificate",
    "tax_other",
    "other",
]

# Combined category type
DocumentCategory = str
DocumentStatus = Literal["uploaded", "queued", "processing", "processed", "failed"]


class DocumentOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    module: str = "accounting"
    category: str
    user_category: str | None = None
    detected_category: str | None = None
    category_confidence: float | None = None
    category_mismatch: bool = False
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    uploaded_by: uuid.UUID
    uploaded_by_email: str | None = None
    created_at: datetime


class DocumentCategoryItem(BaseModel):
    value: str
    label: str


class ModuleCategoriesResponse(BaseModel):
    module: str
    categories: list[DocumentCategoryItem]


class DocumentShareRequest(BaseModel):
    target_module: DocumentModule
    target_category: str | None = None
    notes: str | None = None


class DocumentShareResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    module: str
    module_category: str
    status: str
    notes: str | None = None
    created_at: datetime


class BatchUploadResponse(BaseModel):
    uploaded: list[DocumentOut] = Field(default_factory=list)
    failed: list[dict[str, str]] = Field(default_factory=list)
    total_uploaded: int = 0
    total_failed: int = 0
