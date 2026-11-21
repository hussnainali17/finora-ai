"""Top-level Orchestrator State for Complete CA Workflow.

Coordinates multi-module execution:
Shared Ingestion -> Accounting -> CA Gate -> Publish -> Taxation -> Cross-Module Validation -> CA Final Review.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class CompleteCAWorkflowState(TypedDict, total=False):
    workflow_id: str
    firm_id: str
    client_id: str
    period_id: str
    tax_engagement_id: str | None

    current_module: Literal[
        "shared_intake",
        "accounting",
        "accounting_gate",
        "taxation",
        "taxation_gate",
        "cross_validation",
        "final_ca_review",
        "completed",
        "failed",
    ]
    status: Literal[
        "running",
        "paused_accounting_approval",
        "paused_taxation_approval",
        "paused_final_signoff",
        "completed",
        "failed",
    ]

    accounting_workflow_id: str | None
    accounting_output_id: str | None
    accounting_output_version: int | None
    accounting_approved: bool

    taxation_workflow_id: str | None
    taxation_output_id: str | None
    taxation_output_version: int | None
    taxation_approved: bool

    cross_module_validation: dict[str, Any]
    consolidated_report: dict[str, Any]
    ca_final_signoff: bool

    error: str | None
