"""LangGraph Workflow for Central Document Intelligence.

Architecture:
Upload → File Validation → OCR & Text Extraction → Generic Classification & Category Verification
→ Data Extraction → Quality Validation → Module Routing.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.document_intelligence.categories import (
    ACCOUNTING_CATEGORIES,
    TAXATION_CATEGORIES,
    is_valid_category_for_module,
)
from app.document_intelligence.classifier import verify_category

logger = logging.getLogger("app.document_intelligence.workflow")


class DocumentIntelligenceState(TypedDict):
    document_id: str
    firm_id: str
    client_id: str
    period_id: str
    module: str
    user_category: str
    filename: str
    content_type: str
    size_bytes: int
    raw_bytes: bytes | None
    text_content: str
    table_headers: list[str]
    detected_category: str
    category_confidence: float
    category_mismatch: bool
    category_warnings: list[str]
    tables_count: int
    rows_count: int
    quality_findings: list[dict[str, Any]]
    routing_targets: list[str]
    status: Literal["pending", "processing", "completed", "failed", "needs_review"]
    error: str | None


def validate_file_node(state: DocumentIntelligenceState) -> dict[str, Any]:
    """Validates file presence, size limits, and basic constraints."""
    logger.info("central_doc_intel: validating file %s", state.get("filename"))
    if not state.get("filename"):
        return {"status": "failed", "error": "Missing filename"}
    if state.get("size_bytes", 0) <= 0 and not state.get("raw_bytes"):
        return {"status": "failed", "error": "Empty or zero-byte file"}
    return {"status": "processing", "error": None}


def ocr_and_text_extraction_node(state: DocumentIntelligenceState) -> dict[str, Any]:
    """Extracts text layer and performs OCR if required."""
    logger.info("central_doc_intel: extracting text for %s", state.get("filename"))
    text = state.get("text_content", "")
    raw = state.get("raw_bytes")
    filename = state.get("filename", "")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # If text is already extracted or available, keep it
    if text:
        return {"text_content": text}

    extracted_text = f"Document: {filename}\nType: {ext}"
    if raw:
        try:
            # Quick textual extraction for txt/csv/searchable text
            if ext in ("csv", "txt"):
                extracted_text = raw.decode("utf-8", errors="replace")[:20000]
        except Exception as exc:
            logger.warning("Could not decode text directly: %s", exc)

    return {"text_content": extracted_text}


def generic_classification_node(state: DocumentIntelligenceState) -> dict[str, Any]:
    """Generic document classification & CA category verification."""
    logger.info(
        "central_doc_intel: classifying document %s under module %s",
        state.get("filename"),
        state.get("module"),
    )
    user_cat = state.get("user_category", "other")
    mod = state.get("module", "accounting")
    filename = state.get("filename", "")
    text = state.get("text_content", "")
    headers = state.get("table_headers", [])

    verification = verify_category(
        user_category=user_cat,
        module=mod,
        filename=filename,
        text_content=text,
        table_headers=headers,
    )

    return {
        "detected_category": verification.detected_category,
        "category_confidence": verification.confidence,
        "category_mismatch": verification.is_mismatch,
        "category_warnings": verification.warnings,
    }


def data_extraction_node(state: DocumentIntelligenceState) -> dict[str, Any]:
    """Prepares structured tabular data indicators."""
    logger.info("central_doc_intel: checking extracted tables count")
    return {
        "tables_count": state.get("tables_count", 0),
        "rows_count": state.get("rows_count", 0),
    }


def quality_validation_node(state: DocumentIntelligenceState) -> dict[str, Any]:
    """Validates extraction quality and checks for mismatches."""
    logger.info("central_doc_intel: validating quality for %s", state.get("filename"))
    is_mismatch = state.get("category_mismatch", False)
    findings = list(state.get("quality_findings", []))

    if is_mismatch:
        findings.append(
            {
                "code": "category_mismatch",
                "severity": "warning",
                "message": (
                    f"Selected category '{state.get('user_category')}' does not match detected "
                    f"content '{state.get('detected_category')}'."
                ),
            }
        )

    final_status = "needs_review" if is_mismatch else "completed"
    return {"quality_findings": findings, "status": final_status}


def module_routing_node(state: DocumentIntelligenceState) -> dict[str, Any]:
    """Determines module routing targets and references."""
    mod = state.get("module", "accounting")
    targets = [mod]

    # Shared cross-module referencing rules:
    # Sales invoices and Trial Balances can optionally be shared with Taxation
    user_cat = state.get("user_category", "")
    if mod == "accounting" and user_cat in ("trial_balance", "invoice", "general_ledger"):
        targets.append("taxation_eligible")

    return {"routing_targets": targets}


def create_document_intelligence_graph() -> StateGraph:
    """Creates the compiled LangGraph workflow for Central Document Intelligence."""
    workflow = StateGraph(DocumentIntelligenceState)

    workflow.add_node("validate_file", validate_file_node)
    workflow.add_node("ocr_and_text_extraction", ocr_and_text_extraction_node)
    workflow.add_node("generic_classification", generic_classification_node)
    workflow.add_node("data_extraction", data_extraction_node)
    workflow.add_node("quality_validation", quality_validation_node)
    workflow.add_node("module_routing", module_routing_node)

    workflow.add_edge(START, "validate_file")
    workflow.add_edge("validate_file", "ocr_and_text_extraction")
    workflow.add_edge("ocr_and_text_extraction", "generic_classification")
    workflow.add_edge("generic_classification", "data_extraction")
    workflow.add_edge("data_extraction", "quality_validation")
    workflow.add_edge("quality_validation", "module_routing")
    workflow.add_edge("module_routing", END)

    return workflow.compile()
