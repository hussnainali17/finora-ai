"""Tests for Agent 2: Tax Data & Reconciliation Agent."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tax_data_agent.agent import TaxDataAgent
from app.agents.tax_data_agent.mapper import build_tax_workpaper_mapping, map_account_to_tax_head
from app.agents.tax_data_agent.reconciler import (
    reconcile_advance_tax,
    reconcile_sales_and_turnover,
    reconcile_withholding_taxes,
)
from app.api.deps import Principal
from app.models.shared_data import ApprovedModuleOutput
from app.models.taxation import TaxEngagement


def test_mapper_categorization() -> None:
    assert map_account_to_tax_head("Revenue from Sales", "Income") == "turnover_sales"
    assert map_account_to_tax_head("Accounting Depreciation on Machinery") == "accounting_depreciation"
    assert map_account_to_tax_head("Fines and FBR Penalties") == "inadmissible_penalties"
    assert map_account_to_tax_head("Salaries & Staff Wages") == "payroll_salaries"
    assert map_account_to_tax_head("Raw Materials & Direct Purchases") == "cost_of_sales"

    mapping = build_tax_workpaper_mapping([
        {"account_name": "Sales - Goods", "balance": 1000000},
        {"account_name": "Cost of Goods Sold", "balance": 600000},
        {"account_name": "Depreciation Expense", "balance": 50000},
        {"account_name": "FBR Penalties", "balance": 15000},
    ])
    assert mapping["category_totals"]["turnover_sales"] == 1000000
    assert mapping["category_totals"]["accounting_depreciation"] == 50000
    assert mapping["category_totals"]["inadmissible_penalties"] == 15000


def test_reconciliations() -> None:
    # 1. Withholding reconciliation
    wht_rec = reconcile_withholding_taxes(
        wht_ledger_balance=100000.0,
        certificates=[
            {"certificate_number": "CPR-001", "amount": 60000.0, "section": "153(1)(a)"},
            {"certificate_number": "CPR-002", "amount": 40000.0, "section": "235"},
        ],
        cprs=[
            {"cpr_number": "CPR-001", "amount": 60000.0},
            {"cpr_number": "CPR-002", "amount": 40000.0},
        ],
    )
    assert wht_rec["is_reconciled"] is True
    assert wht_rec["variance"] == 0.0

    # Discrepancy scenario
    wht_disc = reconcile_withholding_taxes(
        wht_ledger_balance=150000.0,
        certificates=[{"certificate_number": "CPR-001", "amount": 100000.0}],
        cprs=[],
    )
    assert wht_disc["is_reconciled"] is False
    assert len(wht_disc["exceptions"]) > 0

    # 2. Sales reconciliation
    sales_rec = reconcile_sales_and_turnover(
        accounting_turnover=5000000.0,
        sales_tax_returns=[{"taxable_supplies": 5000000.0}],
    )
    assert sales_rec["is_reconciled"] is True


@pytest.mark.asyncio
async def test_agent2_execution_mode_a_approved_accounting() -> None:
    session = AsyncMock(spec=AsyncSession)
    engagement_id = uuid.uuid4()
    client_id = uuid.uuid4()
    firm_id = uuid.uuid4()
    period_id = uuid.uuid4()

    mock_engagement = TaxEngagement(
        id=engagement_id,
        firm_id=firm_id,
        client_id=client_id,
        period_id=period_id,
        tax_year=2025,
        tax_period_label="TY2025",
        status="data_gathering",
    )
    session.get.return_value = mock_engagement

    mock_shared_output = ApprovedModuleOutput(
        id=uuid.uuid4(),
        firm_id=firm_id,
        client_id=client_id,
        period_id=period_id,
        module="accounting",
        version=1,
        status="approved",
        data={
            "profit_loss": {
                "total_revenue": 5000000,
                "cost_of_goods_sold": 3000000,
                "depreciation": 200000,
                "salaries": 500000,
                "operating_expenses": 300000,
            },
            "withholding_certificates": [
                {"certificate_number": "CPR-101", "amount": 150000, "section": "153"}
            ],
            "wht_challans": [
                {"cpr_number": "CPR-101", "amount": 150000}
            ],
            "wht_receivable": 150000,
        },
        summary={},
        source_version_refs={},
        validation_results={},
    )

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    session.scalars.return_value = mock_scalars

    principal = Principal(
        user_id=uuid.uuid4(),
        firm_id=firm_id,
        email="ca@firm.com",
        full_name="CA Reviewer",
        role_key="ca_reviewer",
        permissions=frozenset({"tax:manage", "shared:read"}),
        session_id=uuid.uuid4(),
    )

    with patch("app.agents.tax_data_agent.agent.get_latest_approved_accounting_output", return_value=mock_shared_output):
        agent = TaxDataAgent()
        result = await agent.execute_data_and_reconciliation(
            session,
            engagement_id=engagement_id,
            principal=principal,
            source_origin_preference="approved_accounting",
        )

        assert result["source_origin"] == "approved_accounting"
        assert result["accounting_version"] == 1
        assert "turnover_sales" in result["mapping"]["category_totals"]
        assert mock_engagement.status == "reconciliation"
