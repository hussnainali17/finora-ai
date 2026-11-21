"""Phase 12: Add ca_review to llm_agent_configs/llm_task_overrides agent check constraints.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-21 00:00:00.000000
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_AGENTS_ORIG = "'intake', 'accounting_review', 'adjustments', 'reporting'"
_AGENTS_EXT = "'intake', 'accounting_review', 'adjustments', 'reporting', 'ca_review'"


def upgrade() -> None:
    # Use raw DDL — the constraint names were created without op.f() so they have no prefix.
    op.execute(
        "ALTER TABLE llm_agent_configs "
        "DROP CONSTRAINT ck_llm_agent_configs_agent_valid"
    )
    op.execute(
        f"ALTER TABLE llm_agent_configs "
        f"ADD CONSTRAINT ck_llm_agent_configs_agent_valid "
        f"CHECK (agent IN ({_AGENTS_EXT}))"
    )

    op.execute(
        "ALTER TABLE llm_task_overrides "
        "DROP CONSTRAINT ck_llm_task_overrides_agent_valid"
    )
    op.execute(
        f"ALTER TABLE llm_task_overrides "
        f"ADD CONSTRAINT ck_llm_task_overrides_agent_valid "
        f"CHECK (agent IN ({_AGENTS_EXT}))"
    )


def downgrade() -> None:
    # Remove any ca_review rows before restoring the narrower constraint
    op.execute("DELETE FROM llm_agent_configs WHERE agent = 'ca_review'")
    op.execute("DELETE FROM llm_task_overrides WHERE agent = 'ca_review'")

    op.execute(
        "ALTER TABLE llm_agent_configs "
        "DROP CONSTRAINT ck_llm_agent_configs_agent_valid"
    )
    op.execute(
        f"ALTER TABLE llm_agent_configs "
        f"ADD CONSTRAINT ck_llm_agent_configs_agent_valid "
        f"CHECK (agent IN ({_AGENTS_ORIG}))"
    )

    op.execute(
        "ALTER TABLE llm_task_overrides "
        "DROP CONSTRAINT ck_llm_task_overrides_agent_valid"
    )
    op.execute(
        f"ALTER TABLE llm_task_overrides "
        f"ADD CONSTRAINT ck_llm_task_overrides_agent_valid "
        f"CHECK (agent IN ({_AGENTS_ORIG}))"
    )
