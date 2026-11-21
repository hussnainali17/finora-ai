"""State definition for the CA Review & AI Interaction LangGraph workflow."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

IntentType = Literal[
    "question",
    "error_report",
    "correction_request",
    "instruction",
    "approval_action",
    "general",
]

TargetAgentType = Literal[
    "intake",
    "accounting_review",
    "adjustments",
    "reporting",
    "audit",
    "general",
]


class CAReviewState(TypedDict):
    """The shared state passed through each node of the CA Review graph."""

    # Context identifiers
    conversation_id: str
    firm_id: str
    client_id: str
    period_id: str
    user_id: str | None

    # Chat context
    user_message: str
    history: list[dict[str, Any]]

    # Intent classification
    intent: IntentType
    target_agent: TargetAgentType
    intent_confidence: float
    parsed_entities: dict[str, Any]

    # Data context
    context_data: dict[str, Any]

    # Node outputs
    assistant_reply: str
    proposal: dict[str, Any] | None
    instruction_result: dict[str, Any] | None
    reexecution_result: dict[str, Any] | None

    # Status & tracing
    status: Literal["completed", "pending_approval", "failed"]
    error: str | None
