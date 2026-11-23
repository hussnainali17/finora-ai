# ruff: noqa: E501
"""Approved model aliases, the four agents and the tasks they may run through the LLM gateway.

This module is the application's copy of what LiteLLM is configured to serve
(``infrastructure/litellm/config.yaml``; a test asserts they list the same aliases). It holds display
metadata and CAPABILITIES only - never provider ids, URLs or credentials. Capabilities are
conservative statements used to refuse an assignment that cannot work; they are not provider promises.
"""

from dataclasses import dataclass
from typing import Final

AGENTS: Final[dict[str, str]] = {
    "intake": "Agent 1 - Data Intake & Structuring",
    "accounting_review": "Agent 2 - Accounting Review & Reconciliation",
    "adjustments": "Agent 3 - Period-End Adjustments",
    "reporting": "Agent 4 - Financial Reporting & Validation",
    "ca_review": "CA Review Assistant - Multi-Agent Interaction & Correction",
}

CAP_STRUCTURED = "structured_output"  # reliably returns the JSON object it is asked for
CAP_TOOLS = "tools"
CAP_VISION = "vision"
CAPABILITIES: Final[tuple[str, ...]] = (CAP_STRUCTURED, CAP_TOOLS, CAP_VISION)


@dataclass(frozen=True)
class ModelSpec:
    alias: str
    display_name: str
    provider: str
    description: str
    context_window: int  # tokens
    capabilities: frozenset[str]
    tier: str  # economy | standard | premium (relative cost, for display)

    def has(self, capability: str) -> bool:
        return capability in self.capabilities


MODELS: Final[dict[str, ModelSpec]] = {
    m.alias: m
    for m in (
        ModelSpec(
            "fast-general", "Fast general", "OpenAI",
            "Low-cost, low-latency model for classification and light extraction help.",
            128_000, frozenset({CAP_STRUCTURED, CAP_TOOLS, CAP_VISION}), "economy",
        ),
        ModelSpec(
            "strong-general", "Strong general", "OpenAI",
            "Higher-accuracy model for review, reconciliation reasoning and drafting.",
            128_000, frozenset({CAP_STRUCTURED, CAP_TOOLS, CAP_VISION}), "premium",
        ),
        ModelSpec(
            "claude-balanced", "Claude balanced", "Anthropic",
            "Balanced accuracy and cost with a long context window.",
            200_000, frozenset({CAP_STRUCTURED, CAP_TOOLS, CAP_VISION}), "standard",
        ),
        ModelSpec(
            "gemini-fast", "Gemini fast", "Google",
            "Fast, inexpensive model with a very long context window.",
            1_000_000, frozenset({CAP_STRUCTURED, CAP_TOOLS}), "economy",
        ),
        ModelSpec(
            "hy4-flash", "HY4 Flash (Free)", "CentAI",
            "Free-tier model via CentAI gateway — used for CA Review chat, intent classification and all agent tasks.",
            128_000, frozenset({CAP_STRUCTURED, CAP_TOOLS}), "economy",
        ),
    )
}  # fmt: skip


@dataclass(frozen=True)
class TaskSpec:
    agent: str
    task: str
    description: str
    requires: frozenset[str]
    min_context: int  # tokens the task may need (prompt + answer)
    max_output_tokens: int = 1024

    @property
    def key(self) -> str:
        return f"{self.agent}.{self.task}"


TASKS: Final[dict[str, TaskSpec]] = {
    t.key: t
    for t in (
        TaskSpec(
            "intake", "column_roles",
            "Suggest column roles / document type for ambiguous spreadsheet columns.",
            frozenset({CAP_STRUCTURED}), 8_000, 1024,
        ),
        TaskSpec(
            "ca_review", "chat",
            "Conversational Q&A grounded in project source data, reconciliations and reports.",
            frozenset({CAP_STRUCTURED}), 32_000, 3072,
        ),
        TaskSpec(
            "ca_review", "classify_intent",
            "Classify CA review intent (question, error_report, correction_request, instruction).",
            frozenset({CAP_STRUCTURED}), 8_000, 1024,
        ),
        TaskSpec(
            "ca_review", "proposal",
            "Generate structured correction proposals with diffs and downstream re-execution plans.",
            frozenset({CAP_STRUCTURED}), 16_000, 2048,
        ),
        TaskSpec(
            "ca_review", "instruction",
            "Interpret and route CA directives across accounting, audit, and adjustments agents.",
            frozenset({CAP_STRUCTURED}), 16_000, 2048,
        ),
    )
}  # fmt: skip
# Later phases register their tasks here (Agent 2-4); the settings screen and API pick them up.

# Used only to pre-fill choices; a firm still has to ENABLE a model before anything is sent to it.
SUGGESTED_DEFAULTS: Final[dict[str, str]] = {
    "intake": "hy4-flash",
    "accounting_review": "hy4-flash",
    "adjustments": "hy4-flash",
    "reporting": "hy4-flash",
    "ca_review": "hy4-flash",
}


def tasks_for(agent: str) -> list[TaskSpec]:
    return [t for t in TASKS.values() if t.agent == agent]


def unsupported_reasons(model: ModelSpec, task: TaskSpec) -> list[str]:
    """Why `model` cannot run `task` (empty list = suitable). Validates capabilities, not quality."""
    problems = [
        f"does not support {cap.replace('_', ' ')}"
        for cap in sorted(task.requires)
        if not model.has(cap)
    ]
    if model.context_window < task.min_context:
        problems.append(
            f"context window {model.context_window} is below the {task.min_context} required"
        )
    return problems


def agent_unsupported_reasons(model: ModelSpec, agent: str) -> dict[str, list[str]]:
    """Per-task problems for assigning `model` as the agent's default (only tasks with problems)."""
    out = {}
    for t in tasks_for(agent):
        if r := unsupported_reasons(model, t):
            out[t.task] = r
    return out
