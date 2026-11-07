"""Phase 9: workflow_runs table for LangGraph orchestration and checkpoints

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-07 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("firm_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("period_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="running"),
        sa.Column("current_step", sa.String(length=32), nullable=False, server_default="intake"),
        sa.Column(
            "state_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("checkpoint_id", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("initiated_by", sa.UUID(), nullable=True),
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
            "status IN ('running', 'paused_approval', 'completed', 'failed')",
            name=op.f("ck_workflow_runs_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["firm_id"],
            ["firms.id"],
            name=op.f("fk_workflow_runs_firm_id_firms"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_runs")),
    )
    op.create_index("ix_workflow_runs_firm_id", "workflow_runs", ["firm_id"])
    op.create_index(
        "ix_workflow_runs_client_period_status",
        "workflow_runs",
        ["client_id", "period_id", "status"],
    )

    # Permissions
    perms = sa.table("permissions", sa.column("key"), sa.column("description"))
    role_perms = sa.table("role_permissions", sa.column("role_key"), sa.column("permission_key"))

    op.bulk_insert(
        perms,
        [
            {
                "key": "workflow:read",
                "description": "View end-to-end workflow execution state and history",
            },
            {
                "key": "workflow:execute",
                "description": "Trigger, pause, or resume end-to-end agent workflows",
            },
        ],
    )

    grants: dict[str, list[str]] = {
        "firm_admin": ["workflow:read", "workflow:execute"],
        "ca_reviewer": ["workflow:read", "workflow:execute"],
        "accountant": ["workflow:read", "workflow:execute"],
        "client_user": ["workflow:read"],
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
            "('workflow:read', 'workflow:execute')"
        )
    )
    conn.execute(
        sa.text(
            "DELETE FROM permissions WHERE key IN "
            "('workflow:read', 'workflow:execute')"
        )
    )
    op.drop_index("ix_workflow_runs_client_period_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_firm_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
