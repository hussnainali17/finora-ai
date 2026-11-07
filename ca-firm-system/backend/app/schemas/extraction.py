import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import StrictModel

Role = Literal[
    "account_code", "account_name", "description", "date", "value_date", "debit", "credit",
    "withdrawal", "deposit", "amount", "balance", "quantity", "unit_cost", "reference", "party",
    "currency", "item_code", "cost", "depreciation", "accumulated_depreciation",
    "net_book_value", "gross_pay", "deductions", "net_pay", "other", "ignore",
]  # fmt: skip
DocType = Literal[
    "trial_balance", "general_ledger", "bank_statement", "sales_ledger", "purchase_ledger",
    "fixed_asset_register", "inventory_report", "payroll_schedule", "text_document", "unknown",
]  # fmt: skip


class ColumnOut(BaseModel):
    col_index: int
    letter: str | None
    header: str | None
    header_synthetic: bool
    suggested_role: str
    confidence: float
    role_source: str
    confirmed_role: str | None
    effective_role: str


class TableOut(BaseModel):
    id: uuid.UUID
    ordinal: int
    name: str
    kind: str
    n_rows: int
    n_cols: int
    header_row: int | None
    has_header: bool
    detected_type: str
    type_confidence: float
    type_source: str
    confirmed_type: str | None
    effective_type: str
    currency: str | None
    period_start: date | None
    period_end: date | None
    status: str
    columns: list[ColumnOut]
    open_findings: int


class RunOut(BaseModel):
    id: uuid.UUID
    version: int
    status: str
    trigger: str
    started_at: datetime
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    summary: dict[str, Any]
    llm_used: bool
    parser_version: str


class ExtractionOut(BaseModel):
    document_id: uuid.UUID
    document_status: str
    run: RunOut | None
    tables: list[TableOut]
    open_findings: dict[str, int]


class RowOut(BaseModel):
    row_index: int
    source_ref: dict[str, Any]
    raw: dict[str, Any]
    normalized: dict[str, Any]
    flags: list[dict[str, Any]]


class FindingOut(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID | None
    row_index: int | None
    col_index: int | None
    code: str
    severity: str
    message: str
    details: dict[str, Any]
    origin: str
    status: str
    resolution_note: str | None
    created_at: datetime


class ColumnRoleIn(StrictModel):
    role: Role


class TableTypeIn(StrictModel):
    confirmed_type: DocType


class FindingUpdateIn(StrictModel):
    status: Literal["open", "resolved", "dismissed"]
    note: str | None = Field(default=None, max_length=1000)
