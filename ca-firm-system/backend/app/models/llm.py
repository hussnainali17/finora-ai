# ruff: noqa: E501
"""Firm-level AI model configuration and the model-usage log.

Only alias NAMES and settings are stored. No API keys, provider URLs or provider model ids ever enter
this database (they live in the LiteLLM container's environment)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, uuid_pk

AGENT_KEYS = ("intake", "accounting_review", "adjustments", "reporting")
_AGENTS_SQL = ", ".join(f"'{a}'" for a in AGENT_KEYS)


class LlmFirmPolicy(Base):
    """One row per firm. ``config_version`` increases on EVERY change to the firm's model configuration
    and is recorded on each logged call, so a call can be tied to the configuration in force."""

    __tablename__ = "llm_firm_policies"

    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), primary_key=True
    )
    allow_task_overrides: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LlmModelSetting(Base):
    __tablename__ = "llm_model_settings"
    __table_args__ = (
        UniqueConstraint("firm_id", "alias", name="uq_llm_model_settings_firm_id_alias"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LlmAgentConfig(Base):
    __tablename__ = "llm_agent_configs"
    __table_args__ = (
        UniqueConstraint("firm_id", "agent", name="uq_llm_agent_configs_firm_id_agent"),
        CheckConstraint(f"agent IN ({_AGENTS_SQL})", name="agent_valid"),
        CheckConstraint(
            "fallback_alias IS NULL OR fallback_alias <> default_alias", name="fallback_differs"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    agent: Mapped[str] = mapped_column(String(32), nullable=False)
    default_alias: Mapped[str] = mapped_column(String(64), nullable=False)
    fallback_alias: Mapped[str | None] = mapped_column(String(64))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LlmTaskOverride(Base):
    __tablename__ = "llm_task_overrides"
    __table_args__ = (
        UniqueConstraint(
            "firm_id", "agent", "task", name="uq_llm_task_overrides_firm_id_agent_task"
        ),
        CheckConstraint(f"agent IN ({_AGENTS_SQL})", name="agent_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    agent: Mapped[str] = mapped_column(String(32), nullable=False)
    task: Mapped[str] = mapped_column(String(64), nullable=False)
    alias: Mapped[str] = mapped_column(String(64), nullable=False)
    set_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    set_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LlmCallLog(Base):
    """One row per gateway call (after retries/fallback). Append-only (database trigger).

    Holds metadata only: never prompts, completions or client data."""

    __tablename__ = "llm_call_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["client_id", "firm_id"],
            ["clients.id", "clients.firm_id"],
            name="fk_llm_call_logs_client_firm_clients",
        ),
        CheckConstraint("status IN ('ok', 'error')", name="status_valid"),
        Index("ix_llm_call_logs_firm_id_created_at", "firm_id", "created_at"),
        Index("ix_llm_call_logs_firm_id_agent", "firm_id", "agent"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    agent: Mapped[str] = mapped_column(String(32), nullable=False)
    task: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_alias: Mapped[str] = mapped_column(String(64), nullable=False)
    alias: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # the alias that answered/failed last
    provider: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(8), nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 6)
    )  # only if the gateway reports it
    request_id: Mapped[str | None] = mapped_column(String(128))  # LiteLLM / provider response id
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    config_version: Mapped[int | None] = mapped_column(Integer)
    error_class: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_col()
