"""Plain data types shared by the Agent 1 (Data Intake & Structuring) pipeline.

Everything here is review data. Nothing is a ledger entry or a posting."""

from dataclasses import dataclass, field
from typing import Any

PARSER_VERSION = "1.0.0"

# Cell value types: s=text, n=number, d=date/datetime (ISO), b=boolean, e=spreadsheet error.
CELL_TYPES = ("s", "n", "d", "b", "e")

ROLES = (
    "account_code",
    "account_name",
    "description",
    "date",
    "value_date",
    "debit",
    "credit",
    "withdrawal",
    "deposit",
    "amount",
    "balance",
    "quantity",
    "unit_cost",
    "reference",
    "party",
    "currency",
    "item_code",
    "cost",
    "depreciation",
    "accumulated_depreciation",
    "net_book_value",
    "gross_pay",
    "deductions",
    "net_pay",
    "other",
    "ignore",
)
DATE_ROLES = frozenset({"date", "value_date"})
AMOUNT_ROLES = frozenset(
    {
        "debit", "credit", "withdrawal", "deposit", "amount", "balance", "quantity", "unit_cost",
        "cost", "depreciation", "accumulated_depreciation", "net_book_value", "gross_pay",
        "deductions", "net_pay",
    }
)  # fmt: skip
TEXT_ROLES = frozenset(
    {"account_code", "account_name", "description", "reference", "party", "currency", "item_code"}
)

DOC_TYPES = (
    "trial_balance",
    "general_ledger",
    "bank_statement",
    "sales_ledger",
    "purchase_ledger",
    "fixed_asset_register",
    "inventory_report",
    "payroll_schedule",
    "text_document",
    "unknown",
)
# Phase 2 upload category -> the document type the uploader is claiming.
CATEGORY_TO_TYPE = {
    "trial_balance": "trial_balance",
    "general_ledger": "general_ledger",
    "bank_statement": "bank_statement",
    "fixed_asset_schedule": "fixed_asset_register",
    "inventory_report": "inventory_report",
    "payroll_schedule": "payroll_schedule",
}


@dataclass(frozen=True)
class RawCell:
    """A source value exactly as read (never altered after this point)."""

    v: str
    t: str = "s"

    def to_json(self) -> dict[str, str]:
        return {"v": self.v, "t": self.t}

    @staticmethod
    def from_json(d: dict[str, Any]) -> "RawCell":
        return RawCell(v=str(d.get("v", "")), t=str(d.get("t", "s")))


@dataclass
class FindingDraft:
    code: str
    severity: str  # info | warning | error
    message: str
    row_index: int | None = None
    col_index: int | None = None
    details: dict[str, Any] = field(default_factory=dict)
    source_ref: dict[str, Any] = field(default_factory=dict)
    origin: str = "parse"  # parse | normalize


@dataclass
class SourceGrid:
    """One rectangular block of cells found in a file (a sheet, a CSV, a PDF table or text page)."""

    name: str
    kind: str  # sheet | csv | pdf_table | pdf_text | ocr_table | ocr_text
    rows: list[list[RawCell | None]]
    row_numbers: list[int]  # source row number of each grid row
    row_refs: list[dict[str, Any]] = field(default_factory=list)  # extra per-row source info
    meta: dict[str, Any] = field(default_factory=dict)
    findings: list[FindingDraft] = field(default_factory=list)


@dataclass
class ParsedFile:
    grids: list[SourceGrid]
    findings: list[FindingDraft] = field(default_factory=list)
    ocr_applied: bool = False


class ExtractionError(Exception):
    """A deterministic, user-explainable failure (encrypted PDF, corrupt workbook, ...)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def col_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    n, out = index, ""
    while True:
        n, rem = divmod(n, 26)
        out = chr(65 + rem) + out
        if n == 0:
            return out
        n -= 1
