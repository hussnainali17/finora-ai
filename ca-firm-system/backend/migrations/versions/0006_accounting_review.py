"""Phase 6: accounting review tables (review_runs, review_findings, reconciliation_schedules)
and review permissions.

accounting_review

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-07 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ review_runs
    op.create_table(
        "review_runs",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("firm_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("period_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("triggered_by", sa.UUID(), nullable=True),
        sa.Column(
            "trigger",
            sa.String(length=16),
            nullable=False,
            server_default="manual",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "module_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
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
            "status IN ('pending', 'running', 'completed', 'failed')",
            name=op.f("ck_review_runs_status_valid"),
        ),
        sa.CheckConstraint(
            "trigger IN ('auto', 'manual')",
            name=op.f("ck_review_runs_trigger_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["firm_id"],
            ["firms.id"],
            name=op.f("fk_review_runs_firm_id_firms"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_runs")),
    )
    op.create_index("ix_review_runs_firm_id", "review_runs", ["firm_id"])
    op.create_index(
        "ix_review_runs_client_id_period_id",
        "review_runs",
        ["client_id", "period_id"],
    )
    op.create_index(
        "ix_review_runs_status_created_at",
        "review_runs",
        ["status", "created_at"],
    )

    # ------------------------------------------------------------------ review_findings
    op.create_table(
        "review_findings",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("review_run_id", sa.UUID(), nullable=False),
        sa.Column("firm_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("period_id", sa.UUID(), nullable=False),
        sa.Column("module", sa.String(length=32), nullable=False),
        sa.Column("finding_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "source_ref",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "amount",
            sa.Numeric(precision=20, scale=4),
            nullable=True,
        ),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="open",
        ),
        sa.Column("reviewer_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column(
            "evidence_refs",
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
            "severity IN ('info', 'warning', 'error')",
            name=op.f("ck_review_findings_severity_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'explained', 'resolved', 'escalated')",
            name=op.f("ck_review_findings_status_valid"),
        ),
        sa.CheckConstraint(
            "module IN ('sales_receivables', 'purchases_payables', 'bank_cash', "
            "'inventory', 'fixed_assets', 'payroll')",
            name=op.f("ck_review_findings_module_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["review_run_id"],
            ["review_runs.id"],
            name=op.f("fk_review_findings_review_run_id_review_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_findings")),
    )
    op.create_index(
        "ix_review_findings_run_id_status",
        "review_findings",
        ["review_run_id", "status"],
    )
    op.create_index(
        "ix_review_findings_client_period_module",
        "review_findings",
        ["client_id", "period_id", "module"],
    )
    op.create_index("ix_review_findings_firm_id", "review_findings", ["firm_id"])

    # ------------------------------------------------------------------ reconciliation_schedules
    op.create_table(
        "reconciliation_schedules",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("review_run_id", sa.UUID(), nullable=False),
        sa.Column("firm_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("period_id", sa.UUID(), nullable=False),
        sa.Column("module", sa.String(length=32), nullable=False),
        sa.Column("schedule_type", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "source_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.ForeignKeyConstraint(
            ["review_run_id"],
            ["review_runs.id"],
            name=op.f("fk_reconciliation_schedules_review_run_id_review_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reconciliation_schedules")),
        sa.UniqueConstraint(
            "review_run_id",
            "module",
            "schedule_type",
            name="uq_reconciliation_schedules_run_module_type",
        ),
    )
    op.create_index(
        "ix_reconciliation_schedules_run_id",
        "reconciliation_schedules",
        ["review_run_id"],
    )

    # ------------------------------------------------------------------ permissions
    perms = sa.table("permissions", sa.column("key"), sa.column("description"))
    role_perms = sa.table("role_permissions", sa.column("role_key"), sa.column("permission_key"))

    op.bulk_insert(
        perms,
        [
            {
                "key": "review:read",
                "description": "View accounting review results, findings and reconciliation schedules",
            },
            {
                "key": "review:manage",
                "description": "Trigger accounting review runs and configure review settings",
            },
            {
                "key": "review:resolve",
                "description": "Update finding status (explained/resolved/escalated) and add reviewer notes",
            },
        ],
    )

    grants: dict[str, list[str]] = {
        "firm_admin": ["review:read", "review:manage", "review:resolve"],
        "ca_reviewer": ["review:read", "review:manage", "review:resolve"],
        "accountant": ["review:read", "review:resolve"],
        "client_user": ["review:read"],
    }
    op.bulk_insert(
        role_perms,
        [{"role_key": r, "permission_key": p} for r, ps in grants.items() for p in ps],
    )


def downgrade() -> None:
    # Remove permissions
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_key IN "
            "('review:read', 'review:manage', 'review:resolve')"
        )
    )
    conn.execute(
        sa.text(
            "DELETE FROM permissions WHERE key IN "
            "('review:read', 'review:manage', 'review:resolve')"
        )
    )

    op.drop_index("ix_reconciliation_schedules_run_id", table_name="reconciliation_schedules")
    op.drop_table("reconciliation_schedules")

    op.drop_index("ix_review_findings_firm_id", table_name="review_findings")
    op.drop_index("ix_review_findings_client_period_module", table_name="review_findings")
    op.drop_index("ix_review_findings_run_id_status", table_name="review_findings")
    op.drop_table("review_findings")

    op.drop_index("ix_review_runs_status_created_at", table_name="review_runs")
    op.drop_index("ix_review_runs_client_id_period_id", table_name="review_runs")
    op.drop_index("ix_review_runs_firm_id", table_name="review_runs")
    op.drop_table("review_runs")
