"""ORM models for the CA Review & AI Interaction Module.

Provides persistent multi-agent conversation history, error identification,
traceable correction proposals, and agent re-execution tracking.

CRITICAL RULES:
- Original client data is preserved; every correction records a full before/after snapshot.
- Corrections require human-in-the-loop approval before consequential modification.
- Complete auditability linked to AuditEvent.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk

CONVERSATION_STATUSES = ("active", "archived")
MESSAGE_SENDER_TYPES = ("user", "assistant", "system")
MESSAGE_INTENTS = (
    "question",
    "error_report",
    "correction_request",
    "instruction",
    "approval_action",
    "general",
)
PROPOSAL_STATUSES = ("pending", "approved", "rejected", "applied", "failed")
TARGET_AGENTS = (
    "intake",
    "accounting_review",
    "adjustments",
    "reporting",
    "audit",
    "general",
)


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class CAConversation(Base):
    """A persistent conversation session between the CA and the AI agents."""

    __tablename__ = "ca_conversations"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(CONVERSATION_STATUSES)})", name="ca_conv_status_valid"),
        Index("ix_ca_conversations_firm_id", "firm_id"),
        Index(
            "ix_ca_conversations_client_period",
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
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, default="CA Review Session"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    messages: Mapped[list[CAMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="CAMessage.created_at",
    )
    proposals: Mapped[list[CACorrectionProposal]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="CACorrectionProposal.created_at",
    )


class CAMessage(Base):
    """An individual message in the CA Review conversation."""

    __tablename__ = "ca_messages"
    __table_args__ = (
        CheckConstraint(
            f"sender_type IN ({_in(MESSAGE_SENDER_TYPES)})", name="ca_msg_sender_valid"
        ),
        Index("ix_ca_messages_conv_id_created", "conversation_id", "created_at"),
        Index("ix_ca_messages_firm_id", "firm_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ca_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(32))
    target_agent: Mapped[str | None] = mapped_column(String(32))
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    message_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = created_at_col()

    conversation: Mapped[CAConversation] = relationship(back_populates="messages")


class CACorrectionProposal(Base):
    """A structured correction proposed through the CA Review conversation.

    Preserves original data, explains what is wrong and why, tracks human-in-the-loop
    approval, defines the re-execution plan, and logs validation results.
    """

    __tablename__ = "ca_correction_proposals"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_in(PROPOSAL_STATUSES)})", name="ca_prop_status_valid"
        ),
        Index("ix_ca_proposals_conv_id", "conversation_id"),
        Index("ix_ca_proposals_client_period_status", "client_id", "period_id", "status"),
        Index("ix_ca_proposals_firm_id", "firm_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ca_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    target_agent: Mapped[str] = mapped_column(String(32), nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_entity_id: Mapped[str] = mapped_column(String(100), nullable=False)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Immutable snapshot of the data before the proposed change
    original_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # Proposed new values, field diffs, and calculation changes
    proposed_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )

    # Agents that need to re-execute in order: e.g. ["accounting_review", "adjustments", "reporting"]
    reexecution_plan: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # Detailed output of re-execution: validations, status, updated sums
    reexecution_result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    # Human-in-the-loop review audit
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer_notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    conversation: Mapped[CAConversation] = relationship(back_populates="proposals")


__all__ = [
    "CAConversation",
    "CAMessage",
    "CACorrectionProposal",
]
