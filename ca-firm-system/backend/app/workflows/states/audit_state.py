"""Future Audit Module State schema.

NOTE: This schema defines the architectural contract for the future Audit Module.
Audit agents and execution are NOT implemented at this stage, but this contract
ensures seamless future integration without redesigning the hybrid state architecture.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class AuditModuleState(TypedDict, total=False):
    """Architectural state contract for future Audit Module."""

    workflow_id: str
    firm_id: str
    client_id: str
    period_id: str
    step: str
    status: Literal["pending", "running", "paused_approval", "completed", "failed"]

    # Future audit workstream hooks
    audit_plan: dict[str, Any] | None
    risk_assessment: dict[str, Any] | None
    sampling_results: list[dict[str, Any]]
    substantive_testing: dict[str, Any] | None
    audit_findings: list[dict[str, Any]]
    ca_opinion: str | None
    published_output_id: str | None

    error: str | None
