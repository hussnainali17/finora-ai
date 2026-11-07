"""LangGraph workflow execution models.

Tracks durable state, checkpoints, human-in-the-loop pause/resume, and step status
for end-to-end accounting review and reporting runs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk

WORKFLOW_STATUSES = ("running", "paused_approval", "completed", "failed")
WORKFLOW_STEPS = (
    "intake",
    "data_quality_gate",
    "accounting_review",
    "period_adjustments",
    "ca_approval",
    "financial_reporting",
    "validation_gate",
    "completed",
)


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class WorkflowRun(Base):
    """End-to-end orchestrator run coordinating Agent 1 -> Agent 2 -> Agent 3 -> CA Approval -> Agent 4."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(WORKFLOW_STATUSES)})", name="status_valid"),
        Index("ix_workflow_runs_firm_id", "firm_id"),
        Index(
            "ix_workflow_runs_client_period_status",
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
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="running", server_default="running"
    )
    current_step: Mapped[str] = mapped_column(
        String(32), nullable=False, default="intake", server_default="intake"
    )
    state_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    checkpoint_id: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
