"""Tests for Accounting Agent 1: Accounting Intake & Preparation Agent."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.intake_agent.agent import AccountingIntakePreparationAgent
from app.models.accounting_intake import AccountingIntakeRecord
from app.models.documents import Document
from app.models.extraction import ExtractedColumn, ExtractedRow, ExtractedTable, ExtractionRun
from app.models.identity import AccountingPeriod


@pytest.fixture
def firm_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def client_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def period_id() -> uuid.UUID:
    return uuid.uuid4()


def test_intake_preparation_agent_instantiation():
    """Verify Accounting Agent 1 can be instantiated cleanly."""
    agent = AccountingIntakePreparationAgent()
    assert agent is not None


def test_categorization_heuristics():
    """Verify transaction categorization into accounting categories."""
    agent = AccountingIntakePreparationAgent()

    # Sales invoice -> revenue
    cat_sales = agent._categorize_transaction(
        table_type="sales_ledger",
        description="Sale of consulting services",
        party="ACME Corp",
        debit=Decimal("50000"),
        credit=Decimal("0"),
        account_code="4000",
    )
    assert cat_sales == "revenue"

    # Bank statement -> cash_and_bank
    cat_bank = agent._categorize_transaction(
        table_type="bank_statement",
        description="Online transfer out to vendor",
        party="ABC Supplies",
        debit=Decimal("15000"),
        credit=Decimal("0"),
        account_code="1010",
    )
    assert cat_bank == "cash_and_bank"

    # Payroll -> payroll
    cat_payroll = agent._categorize_transaction(
        table_type="payroll_schedule",
        description="Staff monthly basic salary",
        party="Employee A",
        debit=Decimal("120000"),
        credit=Decimal("0"),
        account_code="6100",
    )
    assert cat_payroll == "payroll"

    # Fixed assets -> fixed_assets
    cat_fa = agent._categorize_transaction(
        table_type="fixed_assets",
        description="Office laptop computer purchase",
        party="Dell Direct",
        debit=Decimal("250000"),
        credit=Decimal("0"),
        account_code="1500",
    )
    assert cat_fa == "fixed_assets"


def test_chart_of_accounts_mapping():
    """Verify mapping of transactions into COA."""
    agent = AccountingIntakePreparationAgent()
    existing_mappings = {}

    mapped = agent._map_to_chart_of_accounts(
        account_code="4000",
        account_name="Sales Consulting",
        category="revenue",
        description="Consulting services invoice",
        existing_mappings=existing_mappings,
    )
    assert mapped["account_code"] == "4000"
    assert mapped["account_category"] == "Revenue"
    assert mapped["is_unmapped"] is False

    # Unmapped account code proposed fallback
    unmapped = agent._map_to_chart_of_accounts(
        account_code=None,
        account_name=None,
        category="operating_expense",
        description="Miscellaneous office supplies",
        existing_mappings=existing_mappings,
    )
    assert unmapped["is_unmapped"] is True
    assert unmapped["account_code"] == "6000"


@pytest.mark.asyncio
async def test_execute_intake_preparation_mocked(firm_id, client_id, period_id):
    """Test full execute_intake_preparation execution flow with mocked database queries."""
    agent = AccountingIntakePreparationAgent()

    mock_session = AsyncMock(spec=AsyncSession)

    # Mock period
    period = MagicMock(spec=AccountingPeriod)
    period.start_date = None
    period.end_date = None
    mock_session.get.return_value = period

    # Mock ExtractedTable
    tbl = MagicMock(spec=ExtractedTable)
    tbl.id = uuid.uuid4()
    tbl.document_id = uuid.uuid4()
    tbl.name = "Sales_Invoices_Jan"
    tbl.detected_type = "sales_ledger"
    tbl.confirmed_type = None

    # Mock ExtractedRows
    row1 = MagicMock(spec=ExtractedRow)
    row1.row_index = 0
    row1.normalized = {
        "date": "2024-01-15",
        "reference": "INV-1001",
        "party": "Customer X",
        "description": "Consulting software services",
        "amount": "50000.00",
        "debit": "50000.00",
        "credit": "0.00",
        "account_code": "4000",
    }
    row1.flags = {}

    # Second row with duplicate reference to test duplicate detection
    row2 = MagicMock(spec=ExtractedRow)
    row2.row_index = 1
    row2.normalized = {
        "date": "2024-01-15",
        "reference": "INV-1001",  # Same reference!
        "party": "Customer X",
        "description": "Consulting software services",
        "amount": "50000.00",
        "debit": "50000.00",
        "credit": "0.00",
        "account_code": "4000",
    }
    row2.flags = {}

    # Setup mock scalars returns:
    # 1st call: tables list
    # 2nd call: existing mappings list
    # 3rd call: rows list
    tables_result = MagicMock()
    tables_result.all.return_value = [tbl]

    mappings_result = MagicMock()
    mappings_result.all.return_value = []

    rows_result = MagicMock()
    rows_result.all.return_value = [row1, row2]

    mock_session.scalars.side_effect = [tables_result, mappings_result, rows_result]

    result = await agent.execute_intake_preparation(
        mock_session,
        firm_id=firm_id,
        client_id=client_id,
        period_id=period_id,
    )

    assert result["ready_for_reconciliation"] is True
    assert result["transactions_count"] == 2
    assert result["duplicates_count"] == 2  # INV-1001 duplicate ref + date-amount-party match
    assert "revenue" in result["categorized_summary"]
    assert result["status"] == "needs_review"  # Flagged for review due to duplicate!
    assert mock_session.add.called
    assert mock_session.commit.called
