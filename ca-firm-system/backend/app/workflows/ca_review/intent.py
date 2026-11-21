"""Intent classification and entity extraction for the CA Review workflow.

Distinguishes between:
1. questions: Q&A about calculations, findings, reconciliations, statements
2. error_report: Identification of mistakes or discrepancies in agent outputs
3. correction_request: Explicit directives to update data values or classifications
4. instruction: Directives to agents to re-scan, re-filter, or execute checks
5. approval_action: Approve/reject actions on existing proposals
6. general: Conversational greeting or platform inquiry
"""

from __future__ import annotations

import logging
import re
import uuid
from decimal import Decimal
from typing import Any

from app.llm.gateway import LlmGateway
from app.workflows.ca_review.state import IntentType, TargetAgentType

logger = logging.getLogger("app.workflows.ca_review.intent")


def extract_amounts(text: str) -> list[Decimal]:
    """Extracts numeric currency amounts like 'Rs. 450,000', '500,000', '100000', '450k'."""
    # Matches: Rs. 450,000 or PKR 500000 or $450,000 or raw numbers with commas
    clean = text.replace(",", "")
    patterns = [
        r"(?:rs\.?|pkr|\$)\s*([0-9]+(?:\.[0-9]+)?)",
        r"\b([0-9]{3,}(?:\.[0-9]+)?)\b",
    ]
    amounts: list[Decimal] = []
    for pat in patterns:
        for match in re.finditer(pat, clean, flags=re.IGNORECASE):
            try:
                amt = Decimal(match.group(1))
                if amt > 0 and amt not in amounts:
                    amounts.append(amt)
            except Exception:
                pass
    return amounts


def extract_invoice_ref(text: str) -> str | None:
    """Extracts invoice/document references like 'INV-001', 'invoice #102', 'INV-2024-01'."""
    patterns = [
        r"\b(INV-[A-Za-z0-9\-_]+)\b",
        r"\binvoice\s*(?:#|no\.?|num)?\s*([A-Za-z0-9\-_]+)\b",
        r"\bbill\s*(?:#|no\.?|num)?\s*([A-Za-z0-9\-_]+)\b",
        r"\bvoucher\s*(?:#|no\.?|num)?\s*([A-Za-z0-9\-_]+)\b",
    ]
    for pat in patterns:
        match = re.search(pat, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def extract_account_code(text: str) -> str | None:
    """Extracts account codes like 'account 1010', 'ACC-201', 'code 4001'."""
    match = re.search(r"\b(?:account|code|acc)\s*(?:#)?\s*([A-Za-z0-9\-_]+)\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def classify_intent_rule_based(text: str) -> tuple[IntentType, TargetAgentType, float, dict[str, Any]]:
    """Deterministic rule-based intent classifier with entity extraction."""
    lower = text.lower()
    entities: dict[str, Any] = {}

    amounts = extract_amounts(text)
    invoice_ref = extract_invoice_ref(text)
    account_code = extract_account_code(text)

    if amounts:
        entities["amounts"] = [float(a) for a in amounts]
    if invoice_ref:
        entities["invoice_ref"] = invoice_ref
    if account_code:
        entities["account_code"] = account_code

    # Target agent heuristic
    target_agent: TargetAgentType = "general"
    if any(k in lower for k in ["sales", "receivable", "ar", "revenue", "invoice", "bank", "recon", "cash", "purchas", "payable", "ap", "inventory", "asset", "depreciat", "payroll"]):
        target_agent = "accounting_review"
    if any(k in lower for k in ["adjust", "accrual", "prepayment", "provision", "depreciation calculation"]):
        target_agent = "adjustments"
    if any(k in lower for k in ["report", "statement", "p&l", "profit", "loss", "balance sheet", "trial balance", "tb"]):
        target_agent = "reporting"
    if any(k in lower for k in ["document", "upload", "ocr", "extract", "file", "intake"]):
        target_agent = "intake"

    entities["target_module"] = target_agent

    # 1. Approval action
    if re.search(r"\b(approve|confirm proposal|accept proposal|reject proposal|decline proposal)\b", lower):
        action = "approve" if "approve" in lower or "accept" in lower or "confirm" in lower else "reject"
        entities["approval_action"] = action
        return "approval_action", target_agent, 0.95, entities

    # 2. Correction request / Error report
    # Example: "The sales figure is incorrect. The original invoice shows Rs. 450,000 instead of Rs. 500,000. Correct it."
    is_correction = any(
        phrase in lower
        for phrase in [
            "correct it",
            "fix it",
            "change it to",
            "update it to",
            "instead of",
            "should be",
            "incorrect",
            "is wrong",
            "mistake in",
            "error in",
            "wrong figure",
            "wrong amount",
            "not 500",
            "not rs",
        ]
    )
    if is_correction:
        # Check if they specified old vs new amounts
        if len(amounts) >= 2:
            # Often "shows 450,000 instead of 500,000" or "500,000 should be 450,000"
            if "instead of" in lower:
                # Target is before "instead of", original is after
                parts = lower.split("instead of")
                new_cand = extract_amounts(parts[0])
                orig_cand = extract_amounts(parts[1])
                if new_cand and orig_cand:
                    entities["proposed_value"] = float(new_cand[-1])
                    entities["original_value"] = float(orig_cand[0])
            elif "should be" in lower:
                parts = lower.split("should be")
                orig_cand = extract_amounts(parts[0])
                new_cand = extract_amounts(parts[1])
                if orig_cand and new_cand:
                    entities["original_value"] = float(orig_cand[-1])
                    entities["proposed_value"] = float(new_cand[0])
        elif len(amounts) == 1:
            if any(k in lower for k in ["should be", "change to", "update to", "correct to"]):
                entities["proposed_value"] = float(amounts[0])
            else:
                entities["flagged_value"] = float(amounts[0])

        intent: IntentType = "correction_request" if "correct" in lower or "update" in lower or "change" in lower else "error_report"
        return intent, target_agent, 0.92, entities

    # 3. Agent Instruction
    # Example: "Recheck all transactions above Rs. 100,000 and identify transactions without supporting invoices."
    is_instruction = any(
        lower.startswith(k) or f" {k} " in f" {lower} "
        for k in [
            "recheck",
            "scan all",
            "find all",
            "identify transactions",
            "filter all",
            "check all",
            "audit all",
            "verify all",
            "list all transactions above",
            "identify any",
            "look for",
        ]
    )
    if is_instruction:
        # Extract threshold if mentioned (e.g. above 100,000)
        match_thresh = re.search(r"(?:above|greater than|exceeding|over|>)\s*(?:rs\.?|pkr|\$)?\s*([0-9,]+)", lower)
        if match_thresh:
            try:
                entities["threshold_amount"] = float(match_thresh.group(1).replace(",", ""))
            except Exception:
                pass
        if "without" in lower or "missing" in lower:
            entities["missing_filter"] = "supporting_documents" if "invoice" in lower or "receipt" in lower or "doc" in lower else "counterparty"
        return "instruction", target_agent, 0.90, entities

    # 4. Question
    is_question = (
        "?" in text
        or any(lower.startswith(q) for q in ["why", "what", "how", "is ", "are ", "where", "show", "can you", "explain", "does", "which"])
        or any(k in lower for k in ["variance", "balance", "breakdown", "summary", "why did", "status of"])
    )
    if is_question:
        return "question", target_agent, 0.88, entities

    return "general", target_agent, 0.70, entities


async def classify_intent(
    text: str,
    *,
    firm_id: uuid.UUID,
    history: list[dict[str, Any]] | None = None,
    llm_gateway: LlmGateway | None = None,
) -> tuple[IntentType, TargetAgentType, float, dict[str, Any]]:
    """Classifies user intent using rules with optional LLM Gateway refinement."""
    rule_intent, target_agent, confidence, entities = classify_intent_rule_based(text)

    # If confidence is already very high (e.g. clear approval or clear correction syntax), return immediately
    if confidence >= 0.90 or llm_gateway is None:
        return rule_intent, target_agent, confidence, entities

    try:
        prompt = (
            "You are an intent classifier for a Chartered Accountant AI Interaction system.\n"
            "Classify the following user message into one intent:\n"
            "- 'question': asking about numbers, calculations, reports, decisions\n"
            "- 'error_report': reporting a mistake or discrepancy in agent outputs\n"
            "- 'correction_request': asking to correct/update a specific figure or classification\n"
            "- 'instruction': asking an agent to execute a new check, filter, or recheck\n"
            "- 'approval_action': approving or rejecting a proposal\n"
            "- 'general': greeting or other general chat\n\n"
            f"User message: {text}\n"
            "Respond ONLY with a JSON object: {\"intent\": \"...\", \"target_agent\": \"...\"}"
        )
        res = await llm_gateway.complete(
            firm_id=firm_id,
            agent="ca_review",
            task="classify_intent",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
        )
        import json
        clean_text = res.text.strip()
        if "{" in clean_text:
            clean_text = clean_text[clean_text.find("{"):clean_text.rfind("}") + 1]
            data = json.loads(clean_text)
            intent = data.get("intent", rule_intent)
            agent = data.get("target_agent", target_agent)
            return intent, agent, 0.95, entities
    except Exception as exc:
        logger.debug("LLM intent classification fallback to rules: %s", exc)

    return rule_intent, target_agent, confidence, entities
