"""Pydantic schemas for the Pakistan Taxation Module."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CreateTaxEngagementIn(BaseModel):
    tax_year: int = Field(ge=2000, le=2100, default=2025)
    tax_period_label: str = Field(default="TY2025", max_length=64)
    tax_type: str = Field(default="composite", max_length=32)
    notes: str | None = Field(default=None, max_length=1000)


class TaxEngagementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    firm_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    tax_year: int
    tax_period_label: str
    tax_type: str
    status: str
    assigned_to: uuid.UUID | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class TaxEngagementListOut(BaseModel):
    items: list[TaxEngagementOut]
    total: int


class TaxpayerProfileIn(BaseModel):
    legal_form: str = Field(default="private_company")
    ntn: str | None = Field(default=None, max_length=32)
    strn: str | None = Field(default=None, max_length=32)
    principal_activity: str = Field(default="General Trading", max_length=255)
    business_sector: str = Field(default="Commercial", max_length=128)
    registered_branches: list[dict[str, Any]] = Field(default_factory=list)
    jurisdictions: list[str] = Field(default_factory=list)
    is_active_taxpayer: bool = True
    verified_attributes: dict[str, Any] = Field(default_factory=dict)


class TaxpayerProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    firm_id: uuid.UUID
    client_id: uuid.UUID
    engagement_id: uuid.UUID
    version: int
    legal_form: str
    ntn: str
    strn: str | None = None
    principal_activity: str
    business_sector: str
    registered_branches: list[dict[str, Any]]
    jurisdictions: list[str]
    applicable_obligations: list[str]
    is_active_taxpayer: bool
    verified_attributes: dict[str, Any]
    missing_information: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class ResolveMissingInfoIn(BaseModel):
    query_id: str
    response_value: str
    notes: str | None = None


class TaxWorkpaperOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    firm_id: uuid.UUID
    client_id: uuid.UUID
    engagement_id: uuid.UUID
    workpaper_type: str
    source_origin: str
    accounting_output_version: int | None = None
    data: dict[str, Any]
    exceptions: list[dict[str, Any]]
    status: str
    created_at: datetime
    updated_at: datetime


class TaxWorkpaperListOut(BaseModel):
    items: list[TaxWorkpaperOut]
    total: int


class TaxCalculationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    firm_id: uuid.UUID
    client_id: uuid.UUID
    engagement_id: uuid.UUID
    tax_year: int
    rule_set_version: str
    accounting_profit: dict[str, Any]
    tax_adjustments: list[dict[str, Any]]
    taxable_income: dict[str, Any]
    normal_tax: dict[str, Any]
    minimum_tax_113: dict[str, Any]
    alternate_corporate_tax_113c: dict[str, Any]
    super_tax_4c: dict[str, Any]
    tax_credits: list[dict[str, Any]]
    withholding_taxes: list[dict[str, Any]]
    net_tax_payable: dict[str, Any]
    sales_tax_computation: dict[str, Any]
    calculation_trace: list[dict[str, Any]]
    status: str
    created_at: datetime
    updated_at: datetime


class TaxReturnDraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    firm_id: uuid.UUID
    client_id: uuid.UUID
    engagement_id: uuid.UUID
    version: int
    return_type: str
    return_fields: dict[str, Any]
    review_report: dict[str, Any]
    risk_findings: list[dict[str, Any]]
    status: str
    signed_off_by: uuid.UUID | None = None
    signed_off_at: datetime | None = None
    sign_off_notes: str | None = None
    filing_evidence: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TaxSignOffIn(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)


class FilingEvidenceIn(BaseModel):
    cpr_numbers: list[str] = Field(default_factory=list)
    acknowledgment_number: str = Field(max_length=64)
    filing_date: str = Field(max_length=32)
    bank_name: str | None = Field(default=None, max_length=128)
    amount_paid: str | None = Field(default=None, max_length=32)
    notes: str | None = None


class TaxWorkflowRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    firm_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    engagement_id: uuid.UUID
    status: str
    current_step: str
    state_data: dict[str, Any]
    checkpoint_id: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class MultiModuleWorkflowRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    firm_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    status: str
    current_module: str
    state_data: dict[str, Any]
    checkpoint_id: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class InitiateTaxWorkflowIn(BaseModel):
    engagement_id: uuid.UUID
    source_origin: str = Field(default="approved_accounting")  # or "client_tax_records"
    accounting_version: int | None = None
