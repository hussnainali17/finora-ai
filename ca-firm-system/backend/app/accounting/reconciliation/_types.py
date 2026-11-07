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


__all__ = ["FindingData", "ScheduleData", "ReconciliationResult"]
