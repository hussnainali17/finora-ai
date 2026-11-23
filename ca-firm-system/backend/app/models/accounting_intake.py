"""Accounting Intake & Preparation Models (Accounting Agent 1).

Persists structured intake and preparation outputs derived from centrally extracted documents:
- Accounting-relevant transactions (categorized and mapped to chart of accounts)
- Duplicate detection results
- Completeness and supporting document checks
- Ambiguous transactions & accounting exceptions
- Structured inputs prepared for Accounting Agent 2 (Reconciliation)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk

INTAKE_RECORD_STATUSES = ("draft", "prepared", "needs_review", "approved")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class AccountingIntakeRecord(Base):
    """Output of Accounting Agent 1 (Accounting Intake & Preparation Agent).

    Captures standardized accounting records and preparation assessments
    before handoff to Accounting Agent 2 (Reconciliation Agent).
    """

    __tablename__ = "accounting_intake_records"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(INTAKE_RECORD_STATUSES)})", name="intake_status_valid"),
        Index("ix_accounting_intake_period", "firm_id", "client_id", "period_id"),
        Index("ix_accounting_intake_doc", "document_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="prepared", server_default="prepared"
    )

    # Metrics
    transactions_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    duplicates_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    unmapped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    exceptions_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Structured data payloads
    standardized_records: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    categorized_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    chart_of_accounts_mappings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    completeness_report: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    duplicate_candidates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    exceptions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    notes: Mapped[str | None] = mapped_column(Text)
    prepared_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
