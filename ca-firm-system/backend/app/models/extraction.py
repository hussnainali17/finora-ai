"""Agent 1 output: structured REVIEW data extracted from client files.

None of this is a ledger. Rows are copies of what the client supplied (``raw`` is preserved exactly;
``normalized`` is derived deterministically from ``raw`` + the confirmed column roles), and nothing
here is ever posted anywhere."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, uuid_pk

RUN_STATUSES = ("running", "completed", "failed")
TABLE_STATUSES = ("ok", "needs_review", "ignored")
FINDING_STATUSES = ("open", "resolved", "dismissed")
SEVERITIES = ("info", "warning", "error")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "client_id"],
            ["documents.id", "documents.client_id"],
            name="fk_extraction_runs_document_client_documents",
            ondelete="CASCADE",
        ),
        UniqueConstraint("document_id", "version", name="uq_extraction_runs_document_id_version"),
        UniqueConstraint("id", "document_id", name="uq_extraction_runs_id_document_id"),
        CheckConstraint(f"status IN ({_in(RUN_STATUSES)})", name="status_valid"),
        Index(
            "uq_extraction_runs_current",
            "document_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index("ix_extraction_runs_status_started_at", "status", "started_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    trigger: Mapped[str] = mapped_column(String(16), nullable=False, default="auto")
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = created_at_col()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)  # safe, user-facing
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    llm_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    llm_model: Mapped[str | None] = mapped_column(String(100))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class ExtractedTable(Base):
    __tablename__ = "extracted_tables"
    __table_args__ = (
        UniqueConstraint("run_id", "ordinal", name="uq_extracted_tables_run_id_ordinal"),
        CheckConstraint(f"status IN ({_in(TABLE_STATUSES)})", name="status_valid"),
        Index("ix_extracted_tables_document_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    firm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_ref: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    n_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_cols: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    header_row: Mapped[int | None] = mapped_column(Integer)
    has_header: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    detected_type: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    type_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    type_source: Mapped[str] = mapped_column(String(16), nullable=False, default="heuristic")
    confirmed_type: Mapped[str | None] = mapped_column(String(32))
    detected_currency: Mapped[str | None] = mapped_column(String(3))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    table_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExtractedColumn(Base):
    __tablename__ = "extracted_columns"
    __table_args__ = (
        UniqueConstraint("table_id", "col_index", name="uq_extracted_columns_table_id_col_index"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    table_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extracted_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    col_index: Mapped[int] = mapped_column(Integer, nullable=False)
    letter: Mapped[str | None] = mapped_column(String(8))
    header_raw: Mapped[str | None] = mapped_column(Text)
    header_normalized: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    header_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suggested_role: Mapped[str] = mapped_column(String(24), nullable=False, default="other")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    role_source: Mapped[str] = mapped_column(String(16), nullable=False, default="heuristic")
    confirmed_role: Mapped[str | None] = mapped_column(String(24))
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExtractedRow(Base):
    __tablename__ = "extracted_rows"
    __table_args__ = (
        UniqueConstraint("table_id", "row_index", name="uq_extracted_rows_table_id_row_index"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    table_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extracted_tables.id", ondelete="CASCADE"), nullable=False
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)  # source row number
    source_ref: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    normalized: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    flags: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class DataQualityFinding(Base):
    __tablename__ = "data_quality_findings"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(FINDING_STATUSES)})", name="status_valid"),
        CheckConstraint(f"severity IN ({_in(SEVERITIES)})", name="severity_valid"),
        Index("ix_data_quality_findings_run_id_status", "run_id", "status"),
        Index("ix_data_quality_findings_table_id", "table_id"),
        Index("ix_data_quality_findings_document_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    table_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extracted_tables.id", ondelete="CASCADE")
    )
    firm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    row_index: Mapped[int | None] = mapped_column(Integer)
    col_index: Mapped[int | None] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source_ref: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    origin: Mapped[str] = mapped_column(String(12), nullable=False, default="parse")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="open")
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
