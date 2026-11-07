"""Agent 4 output: Financial reporting, account mappings, and statement validation.

CRITICAL ARCHITECTURE BOUNDARIES:
- The original client Trial Balance is NEVER modified.
- Only CA-APPROVED adjustments feed the Adjusted Trial Balance.
- Unbalanced TBs are flagged; no automatic balancing entries are ever invented.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk

STATEMENT_TYPES = ("balance_sheet", "profit_loss", "cash_flow", "equity")
REPORT_TYPES = (
    "adjusted_trial_balance",
    "profit_loss",
    "balance_sheet",
    "cash_flows",
    "changes_in_equity",
    "full_pack",
)
REPORT_STATUSES = ("draft", "published", "signed_off")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class AccountMapping(Base):
    """Maps client accounts to standardized financial statement lines."""

    __tablename__ = "account_mappings"
    __table_args__ = (
        UniqueConstraint(
            "client_id", "account_code", name="uq_account_mappings_client_account_code"
        ),
        CheckConstraint(
            f"statement_type IN ({_in(STATEMENT_TYPES)})", name="statement_type_valid"
        ),
        Index("ix_account_mappings_firm_id", "firm_id"),
        Index("ix_account_mappings_client_id", "client_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_code: Mapped[str] = mapped_column(String(64), nullable=False)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    statement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    sub_category: Mapped[str | None] = mapped_column(String(64))
    is_debit_balance: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class FinancialReport(Base):
    """Generated reporting output: Adjusted TB, Financial Statements, or Validation pack."""

    __tablename__ = "financial_reports"
    __table_args__ = (
        CheckConstraint(f"report_type IN ({_in(REPORT_TYPES)})", name="report_type_valid"),
        CheckConstraint(f"status IN ({_in(REPORT_STATUSES)})", name="status_valid"),
        Index("ix_financial_reports_firm_id", "firm_id"),
        Index(
            "ix_financial_reports_client_period_type",
            "client_id",
            "period_id",
            "report_type",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    validation_results: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    excel_object_key: Mapped[str | None] = mapped_column(String(512))
    pdf_object_key: Mapped[str | None] = mapped_column(String(512))
    signed_off_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    signed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sign_off_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
