"""Phase 10: add general_ledger to documents category check constraint

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-17 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

CATEGORIES = (
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


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_ck_documents_category_valid;")
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_category_valid;")
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS category_valid;")
    op.execute(
        f"ALTER TABLE documents ADD CONSTRAINT category_valid CHECK (category IN ({_in(CATEGORIES)}));"
    )


def downgrade() -> None:
    pass
