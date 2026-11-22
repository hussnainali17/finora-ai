"""Tests for Agent 4: Tax Review & Filing Pack Agent."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tax_review_agent.agent import TaxReviewAgent
from app.agents.tax_review_agent.cross_checks import run_tax_cross_checks
from app.agents.tax_review_agent.iris_mapper import map_to_fbr_iris_fields
from app.api.deps import Principal
from app.models.taxation import (
    TaxCalculationRun,
    TaxEngagement,
    TaxpayerProfile,
    TaxReturnDraft,
    TaxWorkpaper,
)


def test_tax_cross_checks_detects_unsupported_wht() -> None:
    # Scenario: Claimed WHT 500,000 but certificates only 300,000
    res = run_tax_cross_checks(
        income_tax_data={
            "accounting_profit_before_tax": 2_000_000,
            "turnover": 10_000_000,
            "taxable_income": 2_500_000,
            "gross_tax_liability": 725_000,
            "withholding_taxes_paid": 500_000,
            "net_tax_payable": 225_000,
        },
        workpapers={
            "withholding_reconciliation": {
                "certificates_total": 300_000,
                "exceptions": [],
            }
        },
        taxpayer_profile={"legal_form": "private_company", "ntn": "1234567-8"},
    )
    assert res["is_compliant"] is False
    rules_flagged = [f["rule"] for f in res["findings"]]
    assert "unsupported_withholding_claim" in rules_flagged


def test_fbr_iris_mapping() -> None:
    iris = map_to_fbr_iris_fields(
        income_tax={
            "turnover": 50_000_000,
            "accounting_profit_before_tax": 10_000_000,
            "total_additions": 1_050_000,
            "total_deductions": 1_200_000,
            "taxable_income": 9_850_000,
            "normal_tax": 2_856_500,
            "super_tax_4c": 0,
            "minimum_tax_113": 625_000,
            "alternate_corporate_tax_113c": 1_700_000,
            "gross_tax_liability": 2_856_500,
            "tax_credits": 0,
            "withholding_taxes_paid": 500_000,
            "advance_tax_paid": 800_000,
            "net_tax_payable": 1_556_500,
            "rule_set_version": "ITO2001_TY2025_FA2024",
        },
        sales_tax=None,
        taxpayer_profile={"ntn": "7654321-0", "legal_form": "private_company"},
        tax_year=2025,
    )

    fields = iris["fields"]
    assert fields["7018"] == "7654321-0"
    assert fields["7019"] == "2025"
    assert fields["7001"] == 50_000_000
    assert fields["7005"] == 10_000_000
    assert fields["7008"] == 9_850_000
    assert fields["7013"] == 2_856_500
    assert fields["7017"] == 1_556_500
    assert len(iris["filing_checklist"]) >= 4


@pytest.mark.asyncio
async def test_agent4_generate_draft_and_ca_sign_off() -> None:
    session = AsyncMock(spec=AsyncSession)
    engagement_id = uuid.uuid4()
    client_id = uuid.uuid4()
    firm_id = uuid.uuid4()
    period_id = uuid.uuid4()
    draft_id = uuid.uuid4()

    mock_engagement = TaxEngagement(
        id=engagement_id,
        firm_id=firm_id,
        client_id=client_id,
        period_id=period_id,
        tax_year=2025,
        tax_period_label="TY2025",
        status="calculating",
    )
    mock_calc_run = TaxCalculationRun(
        id=uuid.uuid4(),
        firm_id=firm_id,
        client_id=client_id,
        engagement_id=engagement_id,
        tax_year=2025,
        rule_set_version="ITO2001_TY2025",
        accounting_profit={"pbt": 5_000_000, "turnover": 20_000_000},
        tax_adjustments={"additions": [], "deductions": []},
        taxable_income={"taxable_income": 5_000_000},
        normal_tax={"normal_tax": 1_450_000},
        minimum_tax_113={"minimum_tax_113": 250_000},
        alternate_corporate_tax_113c={"act_113c": 850_000},
        super_tax_4c={"super_tax_4c": 0},
        tax_credits={"credits": []},
        withholding_taxes={"withholding_taxes": [], "advance_tax": 0},
        net_tax_payable={"gross_liability": 1_450_000, "net_payable": 1_450_000},
        sales_tax_computation={},
        calculation_trace=[],
    )
    mock_profile = TaxpayerProfile(
        id=uuid.uuid4(),
        firm_id=firm_id,
        client_id=client_id,
        engagement_id=engagement_id,
        ntn="1234567-8",
        legal_form="private_company",
    )

    session.get.side_effect = lambda model, obj_id: {
        TaxEngagement: mock_engagement if obj_id == engagement_id else None,
        TaxReturnDraft: TaxReturnDraft(
            id=draft_id,
            firm_id=firm_id,
            client_id=client_id,
            engagement_id=engagement_id,
            version=1,
            return_type="it_1",
            return_fields={"7017": 1_450_000, "7013": 1_450_000, "7008": 5_000_000, "7001": 20_000_000},
            review_report={"is_compliant": True, "error_count": 0},
            risk_findings=[],
            status="draft",
            filing_evidence={},
        ) if obj_id == draft_id else None,
    }.get(model)

    mock_scalars_calc = MagicMock()
    mock_scalars_calc.first.return_value = mock_calc_run

    mock_scalars_prof = MagicMock()
    mock_scalars_prof.first.return_value = mock_profile

    mock_scalars_wp = MagicMock()
    mock_scalars_wp.all.return_value = []

    mock_scalars_draft = MagicMock()
    mock_scalars_draft.first.return_value = None

    mock_scalars_sample_wp = MagicMock()
    mock_scalars_sample_wp.first.return_value = None

    session.scalars.side_effect = [
        mock_scalars_calc,
        mock_scalars_prof,
        mock_scalars_wp,
        mock_scalars_draft,
        mock_scalars_sample_wp,
    ]

    agent = TaxReviewAgent()

    # 1. Generate Review and Draft
    draft_res = await agent.generate_review_and_draft(
        session,
        engagement_id=engagement_id,
    )
    assert draft_res["status"] == "draft"
    assert "iris_mapping" in draft_res
    assert mock_engagement.status == "review_pending"

    # 2. CA Sign-off
    principal = Principal(
        user_id=uuid.uuid4(),
        firm_id=firm_id,
        email="ca@firm.com",
        full_name="CA Reviewer",
        role_key="ca_reviewer",
        permissions=frozenset({"tax:approve", "shared:publish", "client:read"}),
        session_id=uuid.uuid4(),
    )

    with patch("app.agents.tax_review_agent.agent.publish_approved_tax_output") as mock_pub:
        signed = await agent.sign_off_tax_pack(
            session,
            principal,
            draft_id=draft_id,
            notes="Formally reviewed and approved by Partner",
        )
        assert signed.status == "ca_approved"
        assert mock_engagement.status == "approved"
        assert mock_pub.called
