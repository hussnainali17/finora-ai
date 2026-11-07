"""Phase 7: period_adjustments table and adjustment permissions

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-07 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "period_adjustments",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("firm_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("period_id", sa.UUID(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="proposed"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("debit_account_code", sa.String(length=64), nullable=False),
        sa.Column("debit_account_name", sa.String(length=200), nullable=False),
        sa.Column("credit_account_code", sa.String(length=64), nullable=False),
        sa.Column("credit_account_name", sa.String(length=200), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="PKR"),
        sa.Column("accounting_rationale", sa.Text(), nullable=False),
        sa.Column(
            "calculation_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "source_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "prepared_by_agent",
            sa.String(length=32),
            nullable=False,
            server_default="adjustments_agent",
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("reviewer_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_decision", sa.String(length=16), nullable=True),
        sa.Column("reviewer_comments", sa.Text(), nullable=True),
        sa.Column(
            "history",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
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
            "category IN ('accruals', 'prepayments', 'depreciation', 'provisions', 'other')",
            name=op.f("ck_period_adjustments_category_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'proposed', 'approved', 'rejected')",
            name=op.f("ck_period_adjustments_status_valid"),
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_period_adjustments_amount_positive")),
        sa.ForeignKeyConstraint(
            ["firm_id"],
            ["firms.id"],
            name=op.f("fk_period_adjustments_firm_id_firms"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_period_adjustments")),
    )
    op.create_index("ix_period_adjustments_firm_id", "period_adjustments", ["firm_id"])
    op.create_index(
        "ix_period_adjustments_client_period_status",
        "period_adjustments",
        ["client_id", "period_id", "status"],
    )

    # Permissions
    perms = sa.table("permissions", sa.column("key"), sa.column("description"))
    role_perms = sa.table("role_permissions", sa.column("role_key"), sa.column("permission_key"))

    op.bulk_insert(
        perms,
        [
            {
                "key": "adjustment:read",
                "description": "View proposed, approved, and rejected period-end adjustments",
            },
            {
                "key": "adjustment:propose",
                "description": "Create and edit draft or proposed period-end adjustments",
            },
            {
                "key": "adjustment:approve",
                "description": "Approve or reject period-end adjustments (CA reviewer authority)",
            },
        ],
    )

    grants: dict[str, list[str]] = {
        "firm_admin": ["adjustment:read", "adjustment:propose", "adjustment:approve"],
        "ca_reviewer": ["adjustment:read", "adjustment:propose", "adjustment:approve"],
        "accountant": ["adjustment:read", "adjustment:propose"],
        "client_user": ["adjustment:read"],
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
            "('adjustment:read', 'adjustment:propose', 'adjustment:approve')"
        )
    )
    conn.execute(
        sa.text(
            "DELETE FROM permissions WHERE key IN "
            "('adjustment:read', 'adjustment:propose', 'adjustment:approve')"
        )
    )
    op.drop_index("ix_period_adjustments_client_period_status", table_name="period_adjustments")
    op.drop_index("ix_period_adjustments_firm_id", table_name="period_adjustments")
    op.drop_table("period_adjustments")
