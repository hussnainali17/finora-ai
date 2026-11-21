"""Modular Multi-Agent Architecture, Central Shared Data Layer, and Taxation Module.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-21 23:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

NEW_PERMISSIONS = [
    ("tax:read", "View tax profiles, reconciliations, computations and returns"),
    ("tax:manage", "Manage tax engagements, mappings, calculations and return drafts"),
    ("tax:approve", "Approve tax calculations, book-to-tax adjustments and return filing packs (CA authority)"),
    ("shared:read", "View central shared data layer records and published outputs"),
    ("shared:publish", "Publish approved module outputs to the central shared data layer"),
]

ROLE_PERMS_ADDITIONS = [
    ("firm_admin", "tax:read"),
    ("firm_admin", "tax:manage"),
    ("firm_admin", "tax:approve"),
    ("firm_admin", "shared:read"),
    ("firm_admin", "shared:publish"),
    ("ca_reviewer", "tax:read"),
    ("ca_reviewer", "tax:manage"),
    ("ca_reviewer", "tax:approve"),
    ("ca_reviewer", "shared:read"),
    ("ca_reviewer", "shared:publish"),
    ("accountant", "tax:read"),
    ("accountant", "tax:manage"),
    ("accountant", "shared:read"),
    ("accountant", "shared:publish"),
    ("client_user", "tax:read"),
    ("client_user", "shared:read"),
]


def upgrade() -> None:
    # 1. approved_module_outputs (Central Shared Data Layer)
    op.create_table(
        "approved_module_outputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column("output_type", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(24), nullable=False, server_default="approved"),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_version_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("validation_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_outdated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("stale_reason", sa.Text(), nullable=True),
        sa.Column("signed_off_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("signed_off_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sign_off_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("module IN ('accounting', 'taxation', 'audit')", name="ck_approved_module_outputs_module_valid"),
        sa.CheckConstraint("status IN ('approved', 'superseded', 'invalidated')", name="ck_approved_module_outputs_output_status_valid"),
    )
    op.create_index("ix_approved_outputs_firm_id", "approved_module_outputs", ["firm_id"])
    op.create_index(
        "ix_approved_outputs_client_period_module",
        "approved_module_outputs",
        ["client_id", "period_id", "module", "output_type", "version"],
    )

    # 2. tax_engagements
    op.create_table(
        "tax_engagements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tax_year", sa.Integer(), nullable=False),
        sa.Column("tax_period_label", sa.String(64), nullable=False, server_default="TY"),
        sa.Column("tax_type", sa.String(32), nullable=False, server_default="composite"),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("tax_type IN ('income_tax', 'sales_tax', 'withholding_tax', 'composite')", name="ck_tax_engagements_tax_type_valid"),
        sa.CheckConstraint(
            "status IN ('draft', 'data_gathering', 'reconciliation', 'calculating', 'review_pending', 'approved', 'filed')",
            name="ck_tax_engagements_engagement_status_valid",
        ),
    )
    op.create_index("ix_tax_engagements_firm_id", "tax_engagements", ["firm_id"])
    op.create_index("ix_tax_engagements_client_period", "tax_engagements", ["client_id", "period_id"])

    # 3. taxpayer_profiles
    op.create_table(
        "taxpayer_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("engagement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tax_engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("legal_form", sa.String(64), nullable=False, server_default="private_company"),
        sa.Column("ntn", sa.String(32), nullable=False),
        sa.Column("strn", sa.String(32), nullable=True),
        sa.Column("principal_activity", sa.String(255), nullable=False, server_default="General Trading"),
        sa.Column("business_sector", sa.String(128), nullable=False, server_default="Commercial"),
        sa.Column("registered_branches", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("jurisdictions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("applicable_obligations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active_taxpayer", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("verified_attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("missing_information", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "legal_form IN ('individual', 'aop', 'private_company', 'public_unlisted', 'public_listed', 'non_resident', 'banking_company', 'modaraba')",
            name="ck_taxpayer_profiles_legal_form_valid",
        ),
    )
    op.create_index("ix_taxpayer_profiles_firm_id", "taxpayer_profiles", ["firm_id"])
    op.create_index("ix_taxpayer_profiles_client_engagement", "taxpayer_profiles", ["client_id", "engagement_id"])

    # 4. tax_workpapers
    op.create_table(
        "tax_workpapers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("engagement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tax_engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workpaper_type", sa.String(64), nullable=False),
        sa.Column("source_origin", sa.String(32), nullable=False, server_default="approved_accounting"),
        sa.Column("accounting_output_version", sa.Integer(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("exceptions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "workpaper_type IN ('book_to_tax_mapping', 'withholding_reconciliation', 'sales_tax_reconciliation', 'advance_tax_schedule', 'depreciation_schedule')",
            name="ck_tax_workpapers_workpaper_type_valid",
        ),
        sa.CheckConstraint("status IN ('draft', 'reconciled', 'discrepancy', 'verified')", name="ck_tax_workpapers_workpaper_status_valid"),
    )
    op.create_index("ix_tax_workpapers_engagement_type", "tax_workpapers", ["engagement_id", "workpaper_type"])

    # 5. tax_calculation_runs
    op.create_table(
        "tax_calculation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("engagement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tax_engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tax_year", sa.Integer(), nullable=False),
        sa.Column("rule_set_version", sa.String(64), nullable=False),
        sa.Column("accounting_profit", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("tax_adjustments", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("taxable_income", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("normal_tax", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("minimum_tax_113", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("alternate_corporate_tax_113c", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("super_tax_4c", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("tax_credits", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("withholding_taxes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("net_tax_payable", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("sales_tax_computation", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("calculation_trace", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tax_calc_engagement", "tax_calculation_runs", ["engagement_id"])

    # 6. tax_return_drafts
    op.create_table(
        "tax_return_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("engagement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tax_engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("return_type", sa.String(32), nullable=False, server_default="it_1"),
        sa.Column("return_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("review_report", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("risk_findings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("signed_off_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("signed_off_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sign_off_notes", sa.Text(), nullable=True),
        sa.Column("filing_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("return_type IN ('it_1', 'sales_tax', 'wht_statement')", name="ck_tax_return_drafts_return_type_valid"),
        sa.CheckConstraint("status IN ('draft', 'ca_approved', 'filing_ready', 'filed', 'rejected')", name="ck_tax_return_drafts_return_status_valid"),
    )
    op.create_index("ix_tax_return_engagement", "tax_return_drafts", ["engagement_id"])

    # 7. tax_workflow_runs
    op.create_table(
        "tax_workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("engagement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tax_engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="running"),
        sa.Column("current_step", sa.String(32), nullable=False, server_default="intake_profile"),
        sa.Column("state_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("checkpoint_id", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("initiated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('running', 'paused_approval', 'completed', 'failed')", name="ck_tax_workflow_runs_tax_wf_status_valid"),
    )
    op.create_index("ix_tax_wf_engagement", "tax_workflow_runs", ["engagement_id"])
    op.create_index("ix_tax_wf_client_period_status", "tax_workflow_runs", ["client_id", "period_id", "status"])

    # 8. multi_module_workflow_runs
    op.create_table(
        "multi_module_workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("current_module", sa.String(32), nullable=False, server_default="accounting"),
        sa.Column("state_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("checkpoint_id", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("initiated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('running', 'paused_accounting_approval', 'paused_taxation_approval', 'paused_final_signoff', 'completed', 'failed')",
            name="ck_multi_module_workflow_runs_multi_wf_status_valid",
        ),
    )
    op.create_index("ix_multi_wf_client_period_status", "multi_module_workflow_runs", ["client_id", "period_id", "status"])

    # 9. Seed new permissions
    for key, desc in NEW_PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO permissions (key, description) VALUES (:key, :desc) ON CONFLICT (key) DO NOTHING"
            ).bindparams(key=key, desc=desc)
        )

    for role_key, perm_key in ROLE_PERMS_ADDITIONS:
        op.execute(
            sa.text(
                "INSERT INTO role_permissions (role_key, permission_key) VALUES (:role, :perm) ON CONFLICT DO NOTHING"
            ).bindparams(role=role_key, perm=perm_key)
        )


def downgrade() -> None:
    for role_key, perm_key in ROLE_PERMS_ADDITIONS:
        op.execute(
            sa.text("DELETE FROM role_permissions WHERE role_key = :role AND permission_key = :perm").bindparams(
                role=role_key, perm=perm_key
            )
        )
    for key, _ in NEW_PERMISSIONS:
        op.execute(sa.text("DELETE FROM permissions WHERE key = :key").bindparams(key=key))

    op.drop_table("multi_module_workflow_runs")
    op.drop_table("tax_workflow_runs")
    op.drop_table("tax_return_drafts")
    op.drop_table("tax_calculation_runs")
    op.drop_table("tax_workpapers")
    op.drop_table("taxpayer_profiles")
    op.drop_table("tax_engagements")
    op.drop_table("approved_module_outputs")
