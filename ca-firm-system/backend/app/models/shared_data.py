"""Central Shared Data Layer models.

Provides versioned, immutable records of approved module outputs (Accounting,
Taxation, and extensible to Audit), tracking source versions, cross-module
dependencies, and invalidation status.
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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk

MODULE_NAMES = ("accounting", "taxation", "audit")
OUTPUT_STATUSES = ("approved", "superseded", "invalidated")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class ApprovedModuleOutput(Base):
    """Central store for approved, versioned module outputs accessible across modules."""

    __tablename__ = "approved_module_outputs"
    __table_args__ = (
        CheckConstraint(f"module IN ({_in(MODULE_NAMES)})", name="module_valid"),
        CheckConstraint(f"status IN ({_in(OUTPUT_STATUSES)})", name="output_status_valid"),
        Index("ix_approved_outputs_firm_id", "firm_id"),
        Index(
            "ix_approved_outputs_client_period_module",
            "client_id",
            "period_id",
            "module",
            "output_type",
            "version",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    module: Mapped[str] = mapped_column(String(32), nullable=False)
    output_type: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="approved", server_default="approved"
    )

    # Full payload data (Trial balance, financial statements, or tax computations)
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # Summary KPI numbers for fast lookup and display
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # References to source versions consumed (e.g. {"accounting_output_version": 1})
    source_version_refs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # Validation results and checks
    validation_results: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    # Staleness & dependency invalidation tracking
    is_outdated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    stale_reason: Mapped[str | None] = mapped_column(Text)

    # CA Sign-off details
    signed_off_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    signed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sign_off_notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
