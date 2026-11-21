"""Accounting Module State definition for LangGraph workflow execution.

Maintains independent execution state, checkpoints, step tracking,
and metrics for the Accounting pipeline (Agents 1-4).
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class AccountingModuleState(TypedDict, total=False):
    workflow_id: str
    firm_id: str
    client_id: str
    period_id: str
    step: str
    status: Literal["running", "paused_approval", "completed", "failed"]
    data_quality_passed: bool
    review_completed: bool
    adjustments_count: int
    ca_approval_granted: bool
    reporting_completed: bool
    validation_passed: bool
    published_output_id: str | None
    extracted_summary: dict[str, Any]
    review_summary: dict[str, Any]
    adjustments_summary: dict[str, Any]
    reporting_summary: dict[str, Any]
    error: str | None
