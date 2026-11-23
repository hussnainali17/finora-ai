"""Tests for Central Document Intelligence Layer."""

import uuid
import pytest

from app.document_intelligence.categories import (
    ACCOUNTING_CATEGORIES,
    ACCOUNTING_CATEGORY_KEYS,
    ALL_CATEGORIES,
    AUDIT_CATEGORIES,
    TAXATION_CATEGORIES,
    TAXATION_CATEGORY_KEYS,
    get_categories_for_module,
    is_valid_category_for_module,
)
from app.document_intelligence.classifier import verify_category
from app.document_intelligence.workflow import create_document_intelligence_graph


def test_module_categories_configuration():
    """Verify Accounting has 10 categories and Taxation has 7 categories."""
    assert len(ACCOUNTING_CATEGORIES) == 10
    assert len(TAXATION_CATEGORIES) == 7

    # Check the required 10 Accounting categories are present
    expected_accounting = {
        "trial_balance",
        "general_ledger",
        "bank_statement",
        "invoice",
        "receipt",
        "contract",
        "fixed_asset_schedule",
        "inventory_report",
        "payroll_schedule",
        "other",
    }
    assert set(ACCOUNTING_CATEGORY_KEYS) == expected_accounting

    # Check the required Taxation categories are present
    expected_taxation = {
        "tax_return",
        "withholding_certificate",
        "sales_tax_return",
        "tax_payment_challan",
        "tax_notice",
        "tax_exemption_certificate",
        "tax_other",
    }
    assert set(TAXATION_CATEGORY_KEYS) == expected_taxation

    # Categories are segregated
    assert is_valid_category_for_module("accounting", "trial_balance") is True
    assert is_valid_category_for_module("accounting", "tax_return") is False
    assert is_valid_category_for_module("taxation", "tax_return") is True
    assert is_valid_category_for_module("taxation", "fixed_asset_schedule") is False


def test_category_verification_matching():
    """Verify correct classification when content matches category."""
    # Bank statement content
    v_bank = verify_category(
        user_category="bank_statement",
        module="accounting",
        filename="MBL_Bank_Statement_Jan_2024.pdf",
        text_content="Account Statement: Opening Balance 50,000 Deposits 200,000 Withdrawals 120,000 Closing Balance 130,000 Cheque No 847291",
        table_headers=["Date", "Description", "Cheque No", "Withdrawals", "Deposits", "Balance"],
    )
    assert v_bank.is_mismatch is False
    assert v_bank.user_category == "bank_statement"
    assert v_bank.detected_category == "bank_statement"

    # Withholding certificate content
    v_wht = verify_category(
        user_category="withholding_certificate",
        module="taxation",
        filename="CPR_Tax_Deduction_153.pdf",
        text_content="FBR Withholding Tax Certificate under Section 153 CPR No CPR20240101 Tax Deducted at Source 45,000",
        table_headers=["CPR No", "Section", "Tax Year", "Tax Deducted", "Status"],
    )
    assert v_wht.is_mismatch is False
    assert v_wht.user_category == "withholding_certificate"
    assert v_wht.detected_category == "withholding_certificate"


def test_category_verification_mismatch_detected():
    """Verify mismatch is flagged, original user category preserved, not silently changed."""
    # User selected bank_statement, but content is clearly a CPR Withholding Tax Certificate
    v_mismatch = verify_category(
        user_category="bank_statement",
        module="accounting",
        filename="FBR_CPR_Challan_Section_153.pdf",
        text_content="Computerized Payment Receipt CPR CPR9928172 Tax Deducted at Source under Section 153 Withholding Tax Certificate",
        table_headers=["CPR Number", "Section Code", "Amount Deducted"],
    )
    assert v_mismatch.is_mismatch is True
    # Primary user selection must be preserved
    assert v_mismatch.user_category == "bank_statement"
    assert v_mismatch.detected_category in ("withholding_certificate", "tax_payment_challan")
    assert len(v_mismatch.warnings) > 0
    assert "Selected category 'bank_statement' does not match" in v_mismatch.warnings[0]


def test_generic_other_category_does_not_mismatch():
    """Generic 'other' does not produce a false positive mismatch."""
    v_other = verify_category(
        user_category="other",
        module="accounting",
        filename="general_notes.pdf",
        text_content="Meeting notes and client correspondence regarding FY24 close.",
    )
    assert v_other.is_mismatch is False
    assert v_other.user_category == "other"


def test_document_intelligence_langgraph_flow():
    """Verify execution of the Central Document Intelligence StateGraph."""
    graph = create_document_intelligence_graph()

    initial_state = {
        "document_id": str(uuid.uuid4()),
        "firm_id": str(uuid.uuid4()),
        "client_id": str(uuid.uuid4()),
        "period_id": str(uuid.uuid4()),
        "module": "accounting",
        "user_category": "trial_balance",
        "filename": "Unadjusted_Trial_Balance_2024.csv",
        "content_type": "text/csv",
        "size_bytes": 1024,
        "raw_bytes": b"account_code,account_name,debit,credit\n1000,Cash,50000,0\n2000,AP,0,50000",
        "text_content": "Unadjusted Trial Balance Debit Credit Balance",
        "table_headers": ["account_code", "account_name", "debit", "credit"],
        "detected_category": "",
        "category_confidence": 0.0,
        "category_mismatch": False,
        "category_warnings": [],
        "tables_count": 1,
        "rows_count": 2,
        "quality_findings": [],
        "routing_targets": [],
        "status": "pending",
        "error": None,
    }

    result = graph.invoke(initial_state)

    assert result["status"] == "completed"
    assert result["category_mismatch"] is False
    assert result["detected_category"] == "trial_balance"
    assert "accounting" in result["routing_targets"]
    assert "taxation_eligible" in result["routing_targets"]
