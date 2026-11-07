"""Phase 8: account_mappings, financial_reports tables and reporting permissions

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-07 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ account_mappings
    op.create_table(
        "account_mappings",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("firm_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("account_code", sa.String(length=64), nullable=False),
        sa.Column("account_name", sa.String(length=200), nullable=False),
        sa.Column("statement_type", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("sub_category", sa.String(length=64), nullable=True),
        sa.Column("is_debit_balance", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "statement_type IN ('balance_sheet', 'profit_loss', 'cash_flow', 'equity')",
            name=op.f("ck_account_mappings_statement_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["firm_id"],
            ["firms.id"],
            name=op.f("fk_account_mappings_firm_id_firms"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_mappings")),
        sa.UniqueConstraint(
            "client_id", "account_code", name="uq_account_mappings_client_account_code"
        ),
    )
    op.create_index("ix_account_mappings_firm_id", "account_mappings", ["firm_id"])
    op.create_index("ix_account_mappings_client_id", "account_mappings", ["client_id"])

    # ------------------------------------------------------------------ financial_reports
    op.create_table(
        "financial_reports",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("firm_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("period_id", sa.UUID(), nullable=False),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "validation_results",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("excel_object_key", sa.String(length=512), nullable=True),
        sa.Column("pdf_object_key", sa.String(length=512), nullable=True),
        sa.Column("signed_off_by", sa.UUID(), nullable=True),
        sa.Column("signed_off_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sign_off_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "report_type IN ('adjusted_trial_balance', 'profit_loss', 'balance_sheet', 'cash_flows', 'changes_in_equity', 'full_pack')",
            name=op.f("ck_financial_reports_report_type_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'signed_off')",
            name=op.f("ck_financial_reports_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["firm_id"],
            ["firms.id"],
            name=op.f("fk_financial_reports_firm_id_firms"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_financial_reports")),
    )
    op.create_index("ix_financial_reports_firm_id", "financial_reports", ["firm_id"])
    op.create_index(
        "ix_financial_reports_client_period_type",
        "financial_reports",
        ["client_id", "period_id", "report_type"],
    )

    # Permissions
    perms = sa.table("permissions", sa.column("key"), sa.column("description"))
    role_perms = sa.table("role_permissions", sa.column("role_key"), sa.column("permission_key"))

    op.bulk_insert(
        perms,
        [
            {
                "key": "report:read",
                "description": "View financial reports, Adjusted Trial Balance, and validation outputs",
            },
            {
                "key": "report:generate",
                "description": "Generate Adjusted Trial Balance and financial statements",
            },
            {
                "key": "report:sign_off",
                "description": "Provide formal CA sign-off on final published reports",
            },
        ],
    )

    grants: dict[str, list[str]] = {
        "firm_admin": ["report:read", "report:generate", "report:sign_off"],
        "ca_reviewer": ["report:read", "report:generate", "report:sign_off"],
        "accountant": ["report:read", "report:generate"],
        "client_user": ["report:read"],
    }
    op.bulk_insert(
        role_perms,
        [{"role_key": r, "permission_key": p} for r, ps in grants.items() for p in ps],
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_key IN "
            "('report:read', 'report:generate', 'report:sign_off')"
        )
    )
    conn.execute(
        sa.text(
            "DELETE FROM permissions WHERE key IN "
            "('report:read', 'report:generate', 'report:sign_off')"
        )
    )
    op.drop_index("ix_financial_reports_client_period_type", table_name="financial_reports")
    op.drop_index("ix_financial_reports_firm_id", table_name="financial_reports")
    op.drop_table("financial_reports")
    op.drop_index("ix_account_mappings_client_id", table_name="account_mappings")
    op.drop_index("ix_account_mappings_firm_id", table_name="account_mappings")
    op.drop_table("account_mappings")
