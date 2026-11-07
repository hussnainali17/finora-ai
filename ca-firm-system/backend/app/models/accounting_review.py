"""ORM models for Phase 6: Accounting Review & Reconciliation (Agent 2 output).

There is intentionally no ledger or bookkeeping here — these are REVIEW artefacts:
findings derived from checking client-supplied data against accounting rules, and
structured schedules (e.g. AR ageing, bank reconciliation) derived from that data.

Nothing in this module creates, modifies or posts accounting entries.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk

REVIEW_STATUSES = ("pending", "running", "completed", "failed")
FINDING_STATUSES = ("open", "explained", "resolved", "escalated")
FINDING_SEVERITIES = ("info", "warning", "error")
REVIEW_MODULES = (
    "sales_receivables",
    "purchases_payables",
    "bank_cash",
    "inventory",
    "fixed_assets",
    "payroll",
)
TRIGGER_TYPES = ("auto", "manual")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class ReviewRun(Base):
    """One review run per client/period trigger.

    A run orchestrates all 6 accounting modules. ``module_summary`` is a JSONB
    snapshot: {module: {status, finding_count, exception_count}}.
    """

    __tablename__ = "review_runs"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(REVIEW_STATUSES)})", name="status_valid"),
        CheckConstraint(f"trigger IN ({_in(TRIGGER_TYPES)})", name="trigger_valid"),
        Index("ix_review_runs_firm_id", "firm_id"),
        Index("ix_review_runs_client_id_period_id", "client_id", "period_id"),
        Index("ix_review_runs_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    trigger: Mapped[str] = mapped_column(
        String(16), nullable=False, default="manual", server_default="manual"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    module_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class ReviewFinding(Base):
    """An individual accounting finding produced by a review run.

    Findings are immutable once created by the agent; reviewers change only
    ``status``, ``reviewer_note`` and ``reviewed_at`` / ``reviewer_id``.
    ``source_ref`` links back to the extracted document / table / row.
    ``evidence_refs`` is a list of additional corroborating references.
    """

    __tablename__ = "review_findings"
    __table_args__ = (
        CheckConstraint(f"severity IN ({_in(FINDING_SEVERITIES)})", name="severity_valid"),
        CheckConstraint(f"status IN ({_in(FINDING_STATUSES)})", name="status_valid"),
        CheckConstraint(f"module IN ({_in(REVIEW_MODULES)})", name="module_valid"),
        Index("ix_review_findings_run_id_status", "review_run_id", "status"),
        Index("ix_review_findings_client_period_module", "client_id", "period_id", "module"),
        Index("ix_review_findings_firm_id", "firm_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    review_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("review_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    currency: Mapped[str | None] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default="open"
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class ReconciliationSchedule(Base):
    """Structured reconciliation output for one module in a review run.

    ``data`` is free-form JSONB holding the schedule rows (e.g. AR ageing buckets,
    bank recon outstanding items). ``schedule_type`` discriminates different
    schedule variants within a module (e.g. "ar_ageing", "ap_ageing").
    """

    __tablename__ = "reconciliation_schedules"
    __table_args__ = (
        UniqueConstraint(
            "review_run_id",
            "module",
            "schedule_type",
            name="uq_reconciliation_schedules_run_module_type",
        ),
        Index("ix_reconciliation_schedules_run_id", "review_run_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    review_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("review_runs.id", ondelete="CASCADE"), nullable=False
    )
    firm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    generated_at: Mapped[datetime] = created_at_col()
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )


__all__ = ["ReviewRun", "ReviewFinding", "ReconciliationSchedule"]
