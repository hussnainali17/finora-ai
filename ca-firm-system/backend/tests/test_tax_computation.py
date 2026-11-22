"""Tests for Agent 3: Tax Computation & Compliance and Deterministic Services."""

from decimal import Decimal
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tax_computation_agent.agent import TaxComputationAgent
from app.models.taxation import TaxEngagement, TaxpayerProfile, TaxWorkpaper
from app.taxation.services.income_tax import compute_pakistan_income_tax
from app.taxation.services.sales_tax import compute_sales_tax


def test_deterministic_income_tax_calculation() -> None:
    # Scenario: Corporate taxpayer with PBT 10,000,000, Turnover 50,000,000
    # Inadmissible additions: Accounting depreciation 1,000,000, Penalties 50,000
    # Admissible deductions: Tax depreciation 1,200,000
    # Withholding taxes paid: 500,000, Advance tax paid: 800,000
    result = compute_pakistan_income_tax(
        accounting_profit_before_tax=10_000_000,
        turnover=50_000_000,
        tax_year=2025,
        legal_form="private_company",
        inadmissible_additions=[
            {"description": "Accounting Depreciation", "amount": 1_000_000, "citation": "s.22"},
            {"description": "Penalties", "amount": 50_000, "citation": "s.21(g)"},
        ],
        admissible_deductions=[
            {"description": "Tax Depreciation", "amount": 1_200_000, "citation": "s.22"},
        ],
        withholding_taxes_paid=[{"amount": 500_000}],
        advance_tax_paid=800_000,
    )

    # 1. Taxable income: 10M + 1.05M - 1.2M = 9,850,000
    assert result["taxable_income"] == 9_850_000.0

    # 2. Normal tax @ 29%: 9,850,000 * 0.29 = 2,856,500
    assert result["normal_tax"] == 2_856_500.0

    # 3. Super Tax under Section 4C: taxable income < 150M => 0%
    assert result["super_tax_4c"] == 0.0

    # 4. Minimum Tax under s.113: 50M * 1.25% = 625,000
    assert result["minimum_tax_113"] == 625_000.0

    # 5. Alternate Corporate Tax (ACT) under s.113C: 10M * 17% = 1,700,000
    assert result["alternate_corporate_tax_113c"] == 1_700_000.0

    # 6. Benchmark comparison: max(2,856,500, 625,000, 1,700,000) = 2,856,500
    assert result["gross_tax_liability"] == 2_856_500.0
    assert result["regime_applied"] == "normal_and_super"

    # 7. Net tax payable: 2,856,500 - (500,000 + 800,000) = 1,556,500
    assert result["net_tax_payable"] == 1_556_500.0

    # 8. Full calculation trace present
    assert len(result["calculation_trace"]) >= 5


def test_minimum_tax_applies_when_higher() -> None:
    # Low margin business: PBT 500,000, Turnover 100,000,000
    # Normal tax: 500,000 * 0.29 = 145,000
    # Minimum tax s.113: 100,000,000 * 1.25% = 1,250,000
    result = compute_pakistan_income_tax(
        accounting_profit_before_tax=500_000,
        turnover=100_000_000,
        tax_year=2025,
    )
    assert result["minimum_tax_113"] == 1_250_000.0
    assert result["gross_tax_liability"] == 1_250_000.0
    assert result["regime_applied"] == "minimum_tax_113"


def test_sales_tax_computation_with_section_8b_cap() -> None:
    # Supplies: 10,000,000 (Output tax @ 18% = 1,800,000)
    # Purchases: 12,000,000 (Input tax @ 18% = 2,160,000)
    # Section 8B 90% cap: 1,800,000 * 90% = 1,620,000 max input tax allowed
    # Net Federal Payable: 1,800,000 - 1,620,000 = 180,000
    # Carried forward: 2,160,000 - 1,620,000 = 540,000
    res = compute_sales_tax(
        taxable_supplies=10_000_000,
        admissible_purchases=12_000_000,
        province="pra",
        provincial_service_turnover=1_000_000,
    )
    assert res["output_tax_goods"] == 1_800_000.0
    assert res["raw_input_tax"] == 2_160_000.0
    assert res["admissible_input_tax"] == 1_620_000.0
    assert res["carried_forward_input_tax"] == 540_000.0
    assert res["net_federal_payable"] == 180_000.0
    # PRA @ 16% on 1M services = 160,000
    assert res["provincial_output_tax"] == 160_000.0
    assert res["total_sales_tax_payable"] == 340_000.0


@pytest.mark.asyncio
async def test_agent3_execution() -> None:
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
        status="reconciliation",
    )
    session.get.return_value = mock_engagement

    mock_profile = TaxpayerProfile(
        id=uuid.uuid4(),
        firm_id=firm_id,
        client_id=client_id,
        engagement_id=engagement_id,
        legal_form="private_company",
        jurisdictions=["PRA"],
        ntn="1234567-8",
        principal_activity="Trading",
        business_sector="Commercial",
    )

    mock_wp_mapping = TaxWorkpaper(
        id=uuid.uuid4(),
        firm_id=firm_id,
        client_id=client_id,
        engagement_id=engagement_id,
        workpaper_type="book_to_tax_mapping",
        data={
            "category_totals": {
                "turnover_sales": 20_000_000,
                "cost_of_sales": 12_000_000,
                "accounting_depreciation": 500_000,
                "payroll_salaries": 2_000_000,
                "inadmissible_penalties": 50_000,
                "admin_selling_expenses": 1_000_000,
                "finance_costs": 200_000,
            }
        },
    )

    mock_wp_wht = TaxWorkpaper(
        id=uuid.uuid4(),
        firm_id=firm_id,
        client_id=client_id,
        engagement_id=engagement_id,
        workpaper_type="withholding_reconciliation",
        data={"certificates_total": 400_000},
    )

    mock_scalars_prof = MagicMock()
    mock_scalars_prof.first.return_value = mock_profile

    mock_scalars_wp = MagicMock()
    mock_scalars_wp.all.return_value = [mock_wp_mapping, mock_wp_wht]

    session.scalars.side_effect = [mock_scalars_prof, mock_scalars_wp]

    agent = TaxComputationAgent()
    res = await agent.execute_computation(
        session,
        engagement_id=engagement_id,
        advance_tax_override=300_000,
    )

    assert "income_tax" in res
    assert "sales_tax" in res
    assert res["tax_year"] == 2025
    assert mock_engagement.status == "calculating"
