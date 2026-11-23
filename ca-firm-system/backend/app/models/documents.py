"""Document metadata (the files themselves live in S3/MinIO) and the transactional outbox."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk

MODULE_NAMES = ("accounting", "taxation", "audit", "general")

# Accounting categories (Preserved exactly: 10 categories)
ACCOUNTING_DOCUMENT_CATEGORIES = (
    "trial_balance",
    "general_ledger",
    "bank_statement",
    "invoice",
    "receipt",
    "contract",
    "fixed_asset_schedule",
    "inventory_report",
    "payroll_schedule",
    "other",
)

# Taxation categories (7 categories)
TAXATION_DOCUMENT_CATEGORIES = (
    "tax_return",
    "withholding_certificate",
    "sales_tax_return",
    "tax_payment_challan",
    "tax_notice",
    "tax_exemption_certificate",
    "tax_other",
)

# Audit categories (extensible)
AUDIT_DOCUMENT_CATEGORIES = (
    "audit_engagement_letter",
    "management_representation",
    "audit_confirmation",
    "sampling_evidence",
    "audit_other",
)

# All valid categories across modules
DOCUMENT_CATEGORIES = tuple(
    sorted(
        set(
            ACCOUNTING_DOCUMENT_CATEGORIES
            + TAXATION_DOCUMENT_CATEGORIES
            + AUDIT_DOCUMENT_CATEGORIES
            + ("other",)
        )
    )
)
DOCUMENT_STATUSES = ("uploaded", "queued", "processing", "processed", "failed")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class Document(Base):
    """One immutable original file. Immutability is enforced by a database trigger
    (migration 0002); only ``status``, ``updated_at`` and the ``deleted_*`` columns may change."""

    __tablename__ = "documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["client_id", "firm_id"],
            ["clients.id", "clients.firm_id"],
            name="fk_documents_client_firm_clients",
            ondelete="RESTRICT",
        ),
        # The period must belong to the SAME client (and therefore the same firm).
        ForeignKeyConstraint(
            ["period_id", "client_id"],
            ["accounting_periods.id", "accounting_periods.client_id"],
            name="fk_documents_period_client_accounting_periods",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["uploaded_by", "firm_id"],
            ["users.id", "users.firm_id"],
            name="fk_documents_uploader_firm_users",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("object_key", name="uq_documents_object_key"),
        # Target for extraction_runs' (document_id, client_id) foreign key.
        UniqueConstraint("id", "client_id", name="uq_documents_id_client_id"),
        CheckConstraint(f"category IN ({_in(DOCUMENT_CATEGORIES)})", name="category_valid"),
        CheckConstraint(f"module IN ({_in(MODULE_NAMES)})", name="module_valid"),
        CheckConstraint(f"status IN ({_in(DOCUMENT_STATUSES)})", name="status_valid"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        CheckConstraint("char_length(sha256) = 64", name="sha256_len"),
        # Duplicate detection: the same bytes cannot be live twice in one client period.
        Index(
            "uq_documents_live_hash",
            "client_id",
            "period_id",
            "sha256",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_documents_period_id_created_at", "period_id", "created_at"),
        Index("ix_documents_firm_id", "firm_id"),
        Index("ix_documents_module", "firm_id", "client_id", "period_id", "module"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    module: Mapped[str] = mapped_column(
        String(32), nullable=False, default="accounting", server_default="accounting"
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    user_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detected_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    category_mismatch: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="uploaded", server_default="uploaded"
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class DocumentModuleReference(Base):
    """Enables a single central document to be referenced by multiple modules
    (e.g., an invoice referenced by Accounting for ledger entries and Taxation for withholding/sales tax).
    """

    __tablename__ = "document_module_references"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "client_id"],
            ["documents.id", "documents.client_id"],
            name="fk_doc_module_ref_document_client",
            ondelete="CASCADE",
        ),
        UniqueConstraint("document_id", "module", name="uq_document_module_reference"),
        CheckConstraint(f"module IN ({_in(MODULE_NAMES)})", name="doc_ref_module_valid"),
        Index("ix_doc_module_ref_module", "firm_id", "client_id", "period_id", "module"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    module_category: Mapped[str] = mapped_column(String(64), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", server_default="active")
    notes: Mapped[str | None] = mapped_column(Text)
    shared_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class OutboxEvent(Base):
    """Transactional outbox: written in the same DB transaction as the business change, then
    relayed to Kafka. Guarantees an event exists if and only if the change committed."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_outbox_events_pending",
            "next_attempt_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()  # this is the event_id consumers deduplicate on
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    partition_key: Mapped[str] = mapped_column(String(100), nullable=False)
    firm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    accounting_period_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    correlation_id: Mapped[str | None] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = created_at_col()
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = created_at_col()
    last_error: Mapped[str | None] = mapped_column(Text)
