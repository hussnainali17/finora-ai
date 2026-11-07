"""Phase 5: worker_jobs table for Kafka consumer idempotency and job state tracking.

worker_jobs

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-07 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_jobs",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=True),
        sa.Column("accounting_period_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_class", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name=op.f("ck_worker_jobs_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_jobs")),
    )
    op.create_index(
        "ix_worker_jobs_event_id",
        "worker_jobs",
        ["event_id"],
        unique=True,
    )
    op.create_index(
        "ix_worker_jobs_status_started_at",
        "worker_jobs",
        ["status", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_worker_jobs_tenant_id",
        "worker_jobs",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_worker_jobs_tenant_id", table_name="worker_jobs")
    op.drop_index("ix_worker_jobs_status_started_at", table_name="worker_jobs")
    op.drop_index("ix_worker_jobs_event_id", table_name="worker_jobs")
    op.drop_table("worker_jobs")
