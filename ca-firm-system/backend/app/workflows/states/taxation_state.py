"""Taxation Module State definition for LangGraph workflow execution.

Maintains independent execution state, checkpoints, step tracking,
and Pakistan tax pipeline outputs across the 4 tax agents.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class TaxationModuleState(TypedDict, total=False):
    workflow_id: str
    firm_id: str
    client_id: str
    period_id: str
    engagement_id: str
    tax_year: int
    step: Literal[
        "intake_profile",
        "data_reconciliation",
        "computation_compliance",
        "review_filing_pack",
        "paused_approval",
        "completed",
        "failed",
    ]
    status: Literal["running", "paused_approval", "completed", "failed"]

    # Agent 1 outputs
    taxpayer_profile: dict[str, Any]
    obligations: list[str]
    missing_information: list[dict[str, Any]]

    # Agent 2 outputs
    source_data_origin: Literal["approved_accounting", "client_tax_records"]
    accounting_output_version: int | None
    tax_mapping: dict[str, Any]
    reconciliations: dict[str, Any]
    reconciliation_exceptions: list[dict[str, Any]]

    # Agent 3 outputs
    tax_rule_version: str
    tax_computation: dict[str, Any]
    calculation_trace: list[dict[str, Any]]
    return_schedules: dict[str, Any]

    # Agent 4 outputs
    validation_results: dict[str, Any]
    risk_findings: list[dict[str, Any]]
    filing_pack: dict[str, Any]
    ca_approval_granted: bool
    published_output_id: str | None

    # Version tracking & staleness
    is_outdated: bool
    stale_reason: str | None

    error: str | None
