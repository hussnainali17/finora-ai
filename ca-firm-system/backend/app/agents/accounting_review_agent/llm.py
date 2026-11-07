"""LLM utilities for the Accounting Review Agent.

The ONLY LLM calls in Agent 2 are here:
- ``explain_finding``: asks the LLM to produce a plain-language explanation of a finding
  for the CA reviewer, citing the evidence already found by the deterministic checks.
- ``classify_ambiguous_entry``: asks the LLM to suggest a classification for an entry
  that the heuristics could not confidently classify.

Rules (enforced by design):
- Never performs arithmetic.
- Never invents evidence or references.
- All calls go through ``LlmGateway.complete()`` (never direct provider calls).
- Prompts include only the finding metadata — never raw document bytes or PII.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.llm.gateway import LlmGateway

logger = logging.getLogger("app.agents.accounting_review.llm")

AGENT = "accounting_review"
TASK_EXPLAIN = "accounting_review.explain_finding"
TASK_CLASSIFY = "accounting_review.classify_entry"

# Max tokens for each LLM call in this agent
MAX_EXPLAIN_TOKENS = 300
MAX_CLASSIFY_TOKENS = 100


async def explain_finding(
    gateway: LlmGateway,
    finding_data: dict[str, Any],
    model_alias: str | None = None,
) -> str:
    """Generate a plain-language explanation of an accounting finding.

    Args:
        gateway: the LLM gateway (all calls go through this).
        finding_data: dict with keys: finding_type, severity, title, description,
                      source_ref, amount, currency, evidence_refs.
        model_alias: optional override; if None the firm default is used via gateway.

    Returns:
        A plain-language explanation string for the CA reviewer.
        On LLM failure returns a safe fallback using the finding description directly.
    """
    prompt = (
        "You are an assistant helping a Chartered Accountant review accounting findings. "
        "Below is a structured accounting finding. Write a concise, plain-language explanation "
        "(2-3 sentences) that the CA reviewer can present to the client. "
        "Do NOT perform any calculations. Do NOT invent any numbers or references not given below.\n\n"
        f"Finding type: {finding_data.get('finding_type')}\n"
        f"Severity: {finding_data.get('severity')}\n"
        f"Title: {finding_data.get('title')}\n"
        f"Description: {finding_data.get('description')}\n"
        f"Amount: {finding_data.get('amount')} {finding_data.get('currency', '')}\n"
        "Provide only the explanation, no headings or bullet points."
    )

    # We use a fixed firm_id placeholder — the gateway will resolve the firm's default model
    # In real use, firm_id and client_id are passed from the calling context
    import uuid

    placeholder_firm_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    try:
        result = await gateway.complete(
            firm_id=placeholder_firm_id,
            agent=AGENT,
            task=TASK_EXPLAIN,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_EXPLAIN_TOKENS,
        )
        return result.text.strip()
    except Exception:
        logger.warning(
            "LLM explain_finding failed — returning description as fallback",
            extra={"finding_type": finding_data.get("finding_type")},
        )
        return str(finding_data.get("description", ""))


async def classify_ambiguous_entry(
    gateway: LlmGateway,
    entry_data: dict[str, Any],
    model_alias: str | None = None,
) -> str:
    """Suggest a classification for an ambiguous extracted entry.

    Args:
        gateway: the LLM gateway.
        entry_data: dict with keys: description, amount, date, context (table type).
        model_alias: optional override.

    Returns:
        A short classification suggestion string (e.g. "sales_receivables", "bank_cash").
        On failure returns "unknown".
    """
    prompt = (
        "You are an accounting classification assistant. "
        "Given the entry below, suggest which accounting module it belongs to. "
        "Reply with ONLY one of these exact strings, nothing else:\n"
        "sales_receivables | purchases_payables | bank_cash | inventory | fixed_assets | payroll\n\n"
        f"Description: {entry_data.get('description')}\n"
        f"Amount: {entry_data.get('amount')}\n"
        f"Date: {entry_data.get('date')}\n"
        f"Table context: {entry_data.get('context', 'unknown')}\n"
    )

    import uuid

    placeholder_firm_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    try:
        result = await gateway.complete(
            firm_id=placeholder_firm_id,
            agent=AGENT,
            task=TASK_CLASSIFY,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_CLASSIFY_TOKENS,
        )
        suggestion = result.text.strip().lower()
        valid = {
            "sales_receivables",
            "purchases_payables",
            "bank_cash",
            "inventory",
            "fixed_assets",
            "payroll",
        }
        return suggestion if suggestion in valid else "unknown"
    except Exception:
        logger.warning(
            "LLM classify_ambiguous_entry failed — returning 'unknown'",
            extra={"description": str(entry_data.get("description", ""))[:100]},
        )
        return "unknown"


__all__ = ["explain_finding", "classify_ambiguous_entry"]
