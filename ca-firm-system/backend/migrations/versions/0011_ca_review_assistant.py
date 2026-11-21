"""Phase 11: CA Review & AI Interaction Module (conversations, messages, proposals, permissions)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-19 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. ca_conversations
    op.create_table(
        "ca_conversations",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("firm_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("period_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False, server_default="CA Review Session"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_by", sa.UUID(), nullable=True),
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
            "status IN ('active', 'archived')",
            name=op.f("ck_ca_conversations_ca_conv_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["firm_id"],
            ["firms.id"],
            name=op.f("fk_ca_conversations_firm_id_firms"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ca_conversations")),
    )
    op.create_index("ix_ca_conversations_firm_id", "ca_conversations", ["firm_id"])
    op.create_index(
        "ix_ca_conversations_client_period",
        "ca_conversations",
        ["client_id", "period_id", "status"],
    )

    # 2. ca_messages
    op.create_table(
        "ca_messages",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("firm_id", sa.UUID(), nullable=False),
        sa.Column("sender_type", sa.String(length=20), nullable=False),
        sa.Column("sender_id", sa.UUID(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=32), nullable=True),
        sa.Column("target_agent", sa.String(length=32), nullable=True),
        sa.Column("proposal_id", sa.UUID(), nullable=True),
        sa.Column(
            "message_metadata",
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
        sa.CheckConstraint(
            "sender_type IN ('user', 'assistant', 'system')",
            name=op.f("ck_ca_messages_ca_msg_sender_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["ca_conversations.id"],
            name=op.f("fk_ca_messages_conversation_id_ca_conversations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ca_messages")),
    )
    op.create_index(
        "ix_ca_messages_conv_id_created",
        "ca_messages",
        ["conversation_id", "created_at"],
    )
    op.create_index("ix_ca_messages_firm_id", "ca_messages", ["firm_id"])

    # 3. ca_correction_proposals
    op.create_table(
        "ca_correction_proposals",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("firm_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("period_id", sa.UUID(), nullable=False),
        sa.Column("target_agent", sa.String(length=32), nullable=False),
        sa.Column("target_entity_type", sa.String(length=32), nullable=False),
        sa.Column("target_entity_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "original_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "proposed_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column(
            "reexecution_plan",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "reexecution_result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
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
            "status IN ('pending', 'approved', 'rejected', 'applied', 'failed')",
            name=op.f("ck_ca_correction_proposals_ca_prop_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["ca_conversations.id"],
            name=op.f("fk_ca_correction_proposals_conversation_id_ca_conversations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ca_correction_proposals")),
    )
    op.create_index(
        "ix_ca_proposals_conv_id",
        "ca_correction_proposals",
        ["conversation_id"],
    )
    op.create_index(
        "ix_ca_proposals_client_period_status",
        "ca_correction_proposals",
        ["client_id", "period_id", "status"],
    )
    op.create_index(
        "ix_ca_proposals_firm_id",
        "ca_correction_proposals",
        ["firm_id"],
    )

    # 4. Seed Permissions
    perms = sa.table("permissions", sa.column("key"), sa.column("description"))
    role_perms = sa.table("role_permissions", sa.column("role_key"), sa.column("permission_key"))

    op.bulk_insert(
        perms,
        [
            {
                "key": "ca_review:read",
                "description": "View CA Review conversation history, source documents context, and proposals",
            },
            {
                "key": "ca_review:write",
                "description": "Send questions, identify errors, request corrections, and give agent instructions",
            },
            {
                "key": "ca_review:approve",
                "description": "Approve or reject correction proposals and trigger agent re-execution",
            },
        ],
    )

    grants: dict[str, list[str]] = {
        "firm_admin": ["ca_review:read", "ca_review:write", "ca_review:approve"],
        "ca_reviewer": ["ca_review:read", "ca_review:write", "ca_review:approve"],
        "accountant": ["ca_review:read", "ca_review:write"],
        "client_user": ["ca_review:read"],
    }
    op.bulk_insert(
        role_perms,
        [{"role_key": r, "permission_key": p} for r, ps in grants.items() for p in ps],
    )


def downgrade() -> None:
    op.drop_table("ca_correction_proposals")
    op.drop_table("ca_messages")
    op.drop_table("ca_conversations")
    op.execute("DELETE FROM role_permissions WHERE permission_key LIKE 'ca_review:%'")
    op.execute("DELETE FROM permissions WHERE key LIKE 'ca_review:%'")
