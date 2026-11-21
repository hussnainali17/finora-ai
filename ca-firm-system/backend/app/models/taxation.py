"""Taxation models conforming to the Pakistan Tax Multi-Agent Architecture.

Maintains data models for:
- TaxEngagement
- TaxpayerProfile (versioned attributes, legal form, NTN/STRN, obligations)
- TaxWorkpaper (TB/GL tax mappings, withholding, sales tax reconciliations)
- TaxCalculationRun (deterministic tax calculations, book-to-tax bridge, super tax, minimum tax)
- TaxReturnDraft (IRIS field mappings, review pack, filing evidence)
- TaxWorkflowRun (independent LangGraph workflow execution for Taxation)
- MultiModuleWorkflowRun (top-level CA workflow coordinating Accounting and Taxation)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk

TAX_TYPES = ("income_tax", "sales_tax", "withholding_tax", "composite")
ENGAGEMENT_STATUSES = (
    "draft",
    "data_gathering",
    "reconciliation",
    "calculating",
    "review_pending",
    "approved",
    "filed",
)
LEGAL_FORMS = (
    "individual",
    "aop",
    "private_company",
    "public_unlisted",
    "public_listed",
    "non_resident",
    "banking_company",
    "modaraba",
)
WORKPAPER_TYPES = (
    "book_to_tax_mapping",
    "withholding_reconciliation",
    "sales_tax_reconciliation",
    "advance_tax_schedule",
    "depreciation_schedule",
)
WORKPAPER_STATUSES = ("draft", "reconciled", "discrepancy", "verified")
RETURN_TYPES = ("it_1", "sales_tax", "wht_statement")
RETURN_STATUSES = ("draft", "ca_approved", "filing_ready", "filed", "rejected")
TAX_WORKFLOW_STATUSES = ("running", "paused_approval", "completed", "failed")
MULTI_WORKFLOW_STATUSES = (
    "running",
    "paused_accounting_approval",
    "paused_taxation_approval",
    "paused_final_signoff",
    "completed",
    "failed",
)


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class TaxEngagement(Base):
    """Tax engagement for a client, tax year, and period."""

    __tablename__ = "tax_engagements"
    __table_args__ = (
        CheckConstraint(f"tax_type IN ({_in(TAX_TYPES)})", name="tax_type_valid"),
        CheckConstraint(f"status IN ({_in(ENGAGEMENT_STATUSES)})", name="engagement_status_valid"),
        Index("ix_tax_engagements_firm_id", "firm_id"),
        Index("ix_tax_engagements_client_period", "client_id", "period_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_period_label: Mapped[str] = mapped_column(String(64), nullable=False, default="TY")
    tax_type: Mapped[str] = mapped_column(String(32), nullable=False, default="composite")
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="draft", server_default="draft"
    )

    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class TaxpayerProfile(Base):
    """Verified taxpayer profile and legal status (Agent 1)."""

    __tablename__ = "taxpayer_profiles"
    __table_args__ = (
        CheckConstraint(f"legal_form IN ({_in(LEGAL_FORMS)})", name="legal_form_valid"),
        Index("ix_taxpayer_profiles_firm_id", "firm_id"),
        Index("ix_taxpayer_profiles_client_engagement", "client_id", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tax_engagements.id", ondelete="CASCADE"), nullable=False
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    legal_form: Mapped[str] = mapped_column(String(64), nullable=False, default="private_company")
    ntn: Mapped[str] = mapped_column(String(32), nullable=False)
    strn: Mapped[str | None] = mapped_column(String(32))
    principal_activity: Mapped[str] = mapped_column(String(255), nullable=False, default="General Trading")
    business_sector: Mapped[str] = mapped_column(String(128), nullable=False, default="Commercial")

    registered_branches: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    jurisdictions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    applicable_obligations: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    is_active_taxpayer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    verified_attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    missing_information: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class TaxWorkpaper(Base):
    """Tax mapping, transaction schedules, and reconciliations (Agent 2)."""

    __tablename__ = "tax_workpapers"
    __table_args__ = (
        CheckConstraint(
            f"workpaper_type IN ({_in(WORKPAPER_TYPES)})", name="workpaper_type_valid"
        ),
        CheckConstraint(f"status IN ({_in(WORKPAPER_STATUSES)})", name="workpaper_status_valid"),
        Index("ix_tax_workpapers_engagement_type", "engagement_id", "workpaper_type"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tax_engagements.id", ondelete="CASCADE"), nullable=False
    )

    workpaper_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_origin: Mapped[str] = mapped_column(
        String(32), nullable=False, default="approved_accounting", server_default="approved_accounting"
    )
    accounting_output_version: Mapped[int | None] = mapped_column(Integer)

    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    exceptions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="draft", server_default="draft"
    )

    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class TaxCalculationRun(Base):
    """Deterministic tax computation and compliance results (Agent 3)."""

    __tablename__ = "tax_calculation_runs"
    __table_args__ = (
        Index("ix_tax_calc_engagement", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tax_engagements.id", ondelete="CASCADE"), nullable=False
    )

    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_set_version: Mapped[str] = mapped_column(String(64), nullable=False)

    accounting_profit: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    tax_adjustments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    taxable_income: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    normal_tax: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    minimum_tax_113: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    alternate_corporate_tax_113c: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    super_tax_4c: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    tax_credits: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    withholding_taxes: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    net_tax_payable: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    sales_tax_computation: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    calculation_trace: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="draft", server_default="draft"
    )

    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class TaxReturnDraft(Base):
    """Validation, CA review pack, and draft filing return (Agent 4)."""

    __tablename__ = "tax_return_drafts"
    __table_args__ = (
        CheckConstraint(f"return_type IN ({_in(RETURN_TYPES)})", name="return_type_valid"),
        CheckConstraint(f"status IN ({_in(RETURN_STATUSES)})", name="return_status_valid"),
        Index("ix_tax_return_engagement", "engagement_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tax_engagements.id", ondelete="CASCADE"), nullable=False
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    return_type: Mapped[str] = mapped_column(String(32), nullable=False, default="it_1")

    # Mapped FBR IRIS return schedule fields (e.g. 7001, 7002, 7003...)
    return_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    review_report: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    risk_findings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="draft", server_default="draft"
    )

    # Formal CA sign-off
    signed_off_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    signed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sign_off_notes: Mapped[str | None] = mapped_column(Text)

    # Filing evidence (CPR, acknowledgment, date, confirmation)
    filing_evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class TaxWorkflowRun(Base):
    """Independent LangGraph execution tracking for Taxation Module."""

    __tablename__ = "tax_workflow_runs"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(TAX_WORKFLOW_STATUSES)})", name="tax_wf_status_valid"),
        Index("ix_tax_wf_engagement", "engagement_id"),
        Index("ix_tax_wf_client_period_status", "client_id", "period_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tax_engagements.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="running", server_default="running"
    )
    current_step: Mapped[str] = mapped_column(
        String(32), nullable=False, default="intake_profile", server_default="intake_profile"
    )
    state_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    checkpoint_id: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class MultiModuleWorkflowRun(Base):
    """Top-level CA Workflow coordinating Accounting and Taxation."""

    __tablename__ = "multi_module_workflow_runs"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_in(MULTI_WORKFLOW_STATUSES)})", name="multi_wf_status_valid"
        ),
        Index("ix_multi_wf_client_period_status", "client_id", "period_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="running", server_default="running"
    )
    current_module: Mapped[str] = mapped_column(
        String(32), nullable=False, default="accounting", server_default="accounting"
    )
    state_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    checkpoint_id: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
