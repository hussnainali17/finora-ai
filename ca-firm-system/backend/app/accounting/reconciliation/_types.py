"""Internal shared types for reconciliation modules.

This module exists to avoid circular imports between the reconciliation
sub-modules and the ``__init__.py`` that re-exports them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class FindingData:
    """A single accounting finding from a reconciliation check."""

    finding_type: str
    severity: str  # "info" | "warning" | "error"
    title: str
    description: str
    source_ref: dict  # {document_id, table_id, row_index, sheet_name, page, ...}
    amount: Decimal | None = None
    currency: str | None = None
    evidence_refs: list[dict] = field(default_factory=list)


@dataclass
class ScheduleData:
    """A structured output schedule (AR ageing, bank recon, etc.)."""

    schedule_type: str
    label: str
    data: dict  # structured schedule rows / buckets
    source_refs: list[dict] = field(default_factory=list)


@dataclass
class ReconciliationResult:
    """Full output from one reconciliation module."""

    findings: list[FindingData]
    schedules: list[ScheduleData]
    summary: dict  # {total_findings, by_severity, totals, ...}


def flatten_rows(items: list[dict]) -> list[dict]:
    """Flattens a list of table dicts (each having a 'rows' key) or returns plain rows.

    Preserves _table_id and _document_id from the parent table if present.
    """
    rows: list[dict] = []
    for item in items:
        if isinstance(item, dict) and "rows" in item and isinstance(item["rows"], list):
            table_id = str(item.get("table_id", ""))
            doc_id = str(item.get("document_id", ""))
            for r in item["rows"]:
                r_copy = dict(r)
                if table_id and "_table_id" not in r_copy:
                    r_copy["_table_id"] = table_id
                if doc_id and "_document_id" not in r_copy:
                    r_copy["_document_id"] = doc_id
                rows.append(r_copy)
        elif isinstance(item, dict):
            rows.append(item)
    return rows


__all__ = ["FindingData", "ScheduleData", "ReconciliationResult", "flatten_rows"]
