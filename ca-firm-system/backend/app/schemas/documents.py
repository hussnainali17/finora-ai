import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

DocumentCategory = Literal[
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
DocumentStatus = Literal["uploaded", "queued", "processing", "processed", "failed"]


class DocumentOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    category: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    uploaded_by: uuid.UUID
    uploaded_by_email: str | None
    created_at: datetime
