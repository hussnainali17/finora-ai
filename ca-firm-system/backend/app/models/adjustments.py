"""Agent 3 output: proposed period-end adjustments.

CRITICAL ARCHITECTURE BOUNDARY:
Adjustments are PROPOSALS with full audit and evidence trails.
They do NOT create or post ledger entries. They are held separately and ONLY
CA-approved adjustments feed into reporting (Phase 8 Adjusted Trial Balance).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk

ADJUSTMENT_CATEGORIES = ("accruals", "prepayments", "depreciation", "provisions", "other")
ADJUSTMENT_STATUSES = ("draft", "proposed", "approved", "rejected")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class PeriodAdjustment(Base):
    """A proposed accounting adjustment for period-end closing.

    Includes full debit/credit account mappings, calculation rationale,
    formula breakdown, source references, status transitions, and CA approval audit.
    """

    __tablename__ = "period_adjustments"
    __table_args__ = (
        CheckConstraint(f"category IN ({_in(ADJUSTMENT_CATEGORIES)})", name="category_valid"),
        CheckConstraint(f"status IN ({_in(ADJUSTMENT_STATUSES)})", name="status_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_period_adjustments_firm_id", "firm_id"),
        Index(
            "ix_period_adjustments_client_period_status",
            "client_id",
            "period_id",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="proposed", server_default="proposed"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    debit_account_code: Mapped[str] = mapped_column(String(64), nullable=False)
    debit_account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    credit_account_code: Mapped[str] = mapped_column(String(64), nullable=False)
    credit_account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=4), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="PKR", server_default="PKR"
    )
    accounting_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    calculation_details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    source_refs: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    prepared_by_agent: Mapped[str] = mapped_column(
        String(32), nullable=False, default="adjustments_agent", server_default="adjustments_agent"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer_decision: Mapped[str | None] = mapped_column(String(16))  # 'approved' | 'rejected'
    reviewer_comments: Mapped[str | None] = mapped_column(Text)
    history: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
