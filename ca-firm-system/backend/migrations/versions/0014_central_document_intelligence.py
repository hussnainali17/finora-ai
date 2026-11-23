"""Central Document Intelligence and Module-Specific Document Ingestion.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-23 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

MODULE_NAMES = ("accounting", "taxation", "audit", "general")

ALL_CATEGORIES = (
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
    "tax_return",
    "withholding_certificate",
    "sales_tax_return",
    "tax_payment_challan",
    "tax_notice",
    "tax_exemption_certificate",
    "tax_other",
    "audit_engagement_letter",
    "management_representation",
    "audit_confirmation",
    "sampling_evidence",
    "audit_other",
)

IMMUTABLE_COLS = (
    "firm_id",
    "client_id",
    "period_id",
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
    # 1. Add module and intelligence columns to documents
    op.add_column(
        "documents",
        sa.Column(
            "module",
            sa.String(32),
            nullable=False,
            server_default="accounting",
        ),
    )
    op.add_column(
        "documents",
        sa.Column("user_category", sa.String(64), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("detected_category", sa.String(64), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("category_confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "category_mismatch",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # 2. Alter category column length to varchar(64)
    op.alter_column(
        "documents",
        "category",
        existing_type=sa.String(32),
        type_=sa.String(64),
        existing_nullable=False,
    )

    # 3. Update category check constraints to support Accounting, Taxation and Audit
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_category_valid;")
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS category_valid;")
    op.execute(
        f"ALTER TABLE documents ADD CONSTRAINT category_valid CHECK (category IN ({_in(ALL_CATEGORIES)}));"
    )

    op.execute(
        f"ALTER TABLE documents ADD CONSTRAINT module_valid CHECK (module IN ({_in(MODULE_NAMES)}));"
    )

    op.create_index(
        "ix_documents_module",
        "documents",
        ["firm_id", "client_id", "period_id", "module"],
    )

    # 4. Update the immutability trigger so new mutable metadata can be updated safely
    checks = " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in IMMUTABLE_COLS)
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION documents_enforce_immutability() RETURNS trigger LANGUAGE plpgsql AS $$
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

    # 5. Create document_module_references table (shared document layer)
    op.create_table(
        "document_module_references",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column("module_category", sa.String(64), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("shared_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "client_id"],
            ["documents.id", "documents.client_id"],
            name="fk_doc_module_ref_document_client",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("document_id", "module", name="uq_document_module_reference"),
        sa.CheckConstraint(f"module IN ({_in(MODULE_NAMES)})", name="doc_ref_module_valid"),
    )
    op.create_index(
        "ix_doc_module_ref_module",
        "document_module_references",
        ["firm_id", "client_id", "period_id", "module"],
    )

    # 6. Create accounting_intake_records table (Agent 1 structured preparation outputs)
    op.create_table(
        "accounting_intake_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="prepared"),
        sa.Column("transactions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicates_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unmapped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exceptions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "standardized_records",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "categorized_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "chart_of_accounts_mappings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "completeness_report",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "duplicate_candidates",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "exceptions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("prepared_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('draft', 'prepared', 'needs_review', 'approved')", name="intake_status_valid"),
    )
    op.create_index(
        "ix_accounting_intake_period",
        "accounting_intake_records",
        ["firm_id", "client_id", "period_id"],
    )
    op.create_index(
        "ix_accounting_intake_doc",
        "accounting_intake_records",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_table("accounting_intake_records")
    op.drop_table("document_module_references")
    op.drop_index("ix_documents_module", table_name="documents")
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS module_valid;")
    op.drop_column("documents", "category_mismatch")
    op.drop_column("documents", "category_confidence")
    op.drop_column("documents", "detected_category")
    op.drop_column("documents", "user_category")
    op.drop_column("documents", "module")
