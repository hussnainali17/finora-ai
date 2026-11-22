"""Tests for Agent 1: Tax Intake & Taxpayer Profile."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tax_intake_agent.agent import TaxIntakeAgent
from app.agents.tax_intake_agent.obligations import determine_applicable_obligations
from app.agents.tax_intake_agent.profile_builder import (
    analyze_profile_completeness,
    validate_ntn,
    validate_strn,
)
from app.models.identity import Client
from app.models.taxation import TaxEngagement, TaxpayerProfile


def test_validate_ntn_and_strn() -> None:
    valid, _ = validate_ntn("1234567-8")
    assert valid is True

    valid, _ = validate_ntn("1234567")
    assert valid is True

    invalid, err = validate_ntn("abc")
    assert invalid is False
    assert "not in valid" in err

    valid_strn, _ = validate_strn("12-34-5678-901-23")
    assert valid_strn is True

    invalid_strn, _ = validate_strn("123")
    assert invalid_strn is False


def test_determine_applicable_obligations() -> None:
    # Corporate goods business in Punjab & Sindh
    corp_obligations = determine_applicable_obligations(
        legal_form="private_company",
        business_sector="Commercial",
        principal_activity="Trading of electronic goods",
        jurisdictions=["PRA", "SRB"],
        has_strn=True,
        turnover_estimate=150_000_000,
    )
    assert any("Corporate Income Tax" in o for o in corp_obligations)
    assert any("Quarterly Advance" in o for o in corp_obligations)
    assert any("Super Tax" in o for o in corp_obligations)
    assert any("Withholding Tax Agent" in o for o in corp_obligations)
    assert any("Federal Sales Tax on Goods" in o for o in corp_obligations)

    # Individual service provider in Punjab
    indiv_obligations = determine_applicable_obligations(
        legal_form="individual",
        business_sector="IT Services",
        principal_activity="Software development consultancy",
        jurisdictions=["PRA"],
        has_strn=False,
        turnover_estimate=20_000_000,
    )
    assert any("Individual Business" in o for o in indiv_obligations)
    assert any("Punjab Sales Tax on Services" in o for o in indiv_obligations)
    assert not any("Corporate Income Tax" in o for o in indiv_obligations)


def test_analyze_profile_completeness_identifies_missing_items() -> None:
    missing = analyze_profile_completeness(
        legal_form="private_company",
        ntn="invalid-ntn",
        strn=None,
        business_sector="Manufacturing",
        principal_activity="Textile Manufacturing",
        registered_branches=[],
        jurisdictions=[],
        has_prior_returns=False,
        has_tax_payment_evidence=False,
    )
    fields = [m["field"] for m in missing]
    assert "ntn" in fields
    assert "strn" in fields
    assert "jurisdictions" in fields
    assert "registered_branches" in fields
    assert "prior_year_returns" in fields
    assert "tax_challans" in fields


@pytest.mark.asyncio
async def test_agent1_intake_execution() -> None:
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
        tax_type="composite",
        status="draft",
    )
    mock_client = Client(
        id=client_id,
        firm_id=firm_id,
        name="Apex Trading Pvt Ltd",
    )

    session.get.side_effect = lambda model, obj_id: {
        TaxEngagement: mock_engagement if obj_id == engagement_id else None,
        Client: mock_client if obj_id == client_id else None,
    }.get(model)

    mock_scalars = MagicMock()
    # 1. Documents query -> []
    # 2. Existing profile query -> None
    mock_scalars.all.return_value = []
    mock_scalars.first.return_value = None
    session.scalars.return_value = mock_scalars

    agent = TaxIntakeAgent()
    result = await agent.execute_intake(
        session,
        engagement_id=engagement_id,
        override_profile_data={
            "legal_form": "private_company",
            "ntn": "7654321-0",
            "strn": "12-34-5678-901-23",
            "principal_activity": "Commercial Trading",
            "business_sector": "Commercial",
            "jurisdictions": ["Federal", "PRA"],
        },
    )

    assert result["engagement_id"] == str(engagement_id)
    assert result["taxpayer_profile"]["ntn"] == "7654321-0"
    assert len(result["obligations"]) > 0
    assert mock_engagement.status == "data_gathering"
