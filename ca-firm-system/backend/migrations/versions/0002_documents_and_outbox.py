"""Phase 2: documents (metadata for immutable originals), outbox, document permissions.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

CATEGORIES = (
    "trial_balance",
    "bank_statement",
    "invoice",
    "receipt",
    "contract",
    "fixed_asset_schedule",
    "inventory_report",
    "payroll_schedule",
    "other",
)
STATUSES = ("uploaded", "queued", "processing", "processed", "failed")
NEW_PERMISSIONS = {
    "document:read": "List and download documents of accessible clients",
    "document:upload": "Upload documents to open accounting periods of accessible clients",
    "document:delete": "Remove (soft-delete) documents; the original object is retained",
}
GRANTS = {
    "firm_admin": ["document:read", "document:upload", "document:delete"],
    "ca_reviewer": ["document:read", "document:upload", "document:delete"],
    "accountant": ["document:read", "document:upload"],
    "client_user": ["document:read"],
}
IMMUTABLE = (
    "firm_id",
    "client_id",
    "period_id",
    "category",
    "original_filename",
    "object_key",
    "content_type",
    "size_bytes",
    "sha256",
    "uploaded_by",
    "created_at",
)


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_accounting_periods_id_client_id", "accounting_periods", ["id", "client_id"]
    )

    perms = sa.table("permissions", sa.column("key"), sa.column("description"))
    role_perms = sa.table("role_permissions", sa.column("role_key"), sa.column("permission_key"))
    op.bulk_insert(perms, [{"key": k, "description": d} for k, d in NEW_PERMISSIONS.items()])
    op.bulk_insert(
        role_perms, [{"role_key": r, "permission_key": p} for r, ps in GRANTS.items() for p in ps]
    )

    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(150), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="uploaded"),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True)),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.ForeignKeyConstraint(
            ["client_id", "firm_id"],
            ["clients.id", "clients.firm_id"],
            name="fk_documents_client_firm_clients",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["period_id", "client_id"],
            ["accounting_periods.id", "accounting_periods.client_id"],
            name="fk_documents_period_client_accounting_periods",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by", "firm_id"],
            ["users.id", "users.firm_id"],
            name="fk_documents_uploader_firm_users",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("object_key", name="uq_documents_object_key"),
        sa.CheckConstraint(f"category IN ({_in(CATEGORIES)})", name="ck_documents_category_valid"),
        sa.CheckConstraint(f"status IN ({_in(STATUSES)})", name="ck_documents_status_valid"),
        sa.CheckConstraint("size_bytes > 0", name="ck_documents_size_positive"),
        sa.CheckConstraint("char_length(sha256) = 64", name="ck_documents_sha256_len"),
    )
    op.create_index(
        "uq_documents_live_hash",
        "documents",
        ["client_id", "period_id", "sha256"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_documents_period_id_created_at", "documents", ["period_id", "created_at"])
    op.create_index("ix_documents_firm_id", "documents", ["firm_id"])

    # Originals are immutable: only status / updated_at / deleted_* may change; rows are never deleted.
    checks = " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in IMMUTABLE)
    op.execute(
        f"""
        CREATE FUNCTION documents_enforce_immutability() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'documents rows cannot be deleted (soft-delete instead)'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF {checks} THEN
                RAISE EXCEPTION 'documents original-file columns are immutable'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER documents_immutable BEFORE UPDATE OR DELETE ON documents "
        "FOR EACH ROW EXECUTE FUNCTION documents_enforce_immutability()"
    )

    op.create_table(
        "outbox_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("topic", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("partition_key", sa.String(100), nullable=False),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True)),
        sa.Column("accounting_period_id", postgresql.UUID(as_uuid=True)),
        sa.Column("correlation_id", sa.String(100)),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_events"),
    )
    op.create_index(
        "ix_outbox_events_pending",
        "outbox_events",
        ["next_attempt_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.execute("DROP TRIGGER IF EXISTS documents_immutable ON documents")
    op.drop_table("documents")
    op.execute("DROP FUNCTION IF EXISTS documents_enforce_immutability()")
    op.execute("DELETE FROM role_permissions WHERE permission_key LIKE 'document:%'")
    op.execute("DELETE FROM permissions WHERE key LIKE 'document:%'")
    op.drop_constraint("uq_accounting_periods_id_client_id", "accounting_periods", type_="unique")
