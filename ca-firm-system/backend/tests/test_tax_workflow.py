"""Tests for independent Pakistan Taxation LangGraph workflow orchestration."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal
from app.models.taxation import TaxEngagement, TaxReturnDraft, TaxWorkflowRun
from app.workflows.taxation.orchestrator import TaxWorkflowOrchestrator


@pytest.fixture
def mock_principal() -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        firm_id=uuid.uuid4(),
        email="ca@firm.com",
        full_name="CA Reviewer",
        role_key="ca_reviewer",
        permissions=frozenset({
            "tax:read",
            "tax:manage",
            "tax:approve",
            "shared:read",
            "shared:publish",
            "workflow:execute",
            "workflow:read",
            "client:read",
        }),
        session_id=uuid.uuid4(),
    )


@pytest.mark.asyncio
async def test_tax_workflow_initiation_and_pause_at_checkpoint(mock_principal: Principal) -> None:
    session = AsyncMock(spec=AsyncSession)
    client_id = uuid.uuid4()
    period_id = uuid.uuid4()
    engagement_id = uuid.uuid4()

    mock_engagement = TaxEngagement(
        id=engagement_id,
        firm_id=mock_principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        tax_year=2025,
        tax_period_label="TY2025",
        status="draft",
    )
    session.get.return_value = mock_engagement

    # Mock each agent's execution
    intake_output = {
        "taxpayer_profile": {"ntn": "1234567-8", "legal_form": "private_company"},
        "obligations": ["Federal Income Tax"],
        "missing_information": [],
    }
    data_output = {
        "source_origin": "approved_accounting",
        "accounting_version": 1,
        "mapping": {"category_totals": {"turnover_sales": 10_000_000}},
        "reconciliations": {},
        "exceptions": [],
    }
    comp_output = {
        "rule_set_version": "ITO2001_TY2025",
        "income_tax": {
            "taxable_income": 2_000_000,
            "net_tax_payable": 580_000,
            "calculation_trace": [],
        },
    }
    review_output = {
        "draft_id": str(uuid.uuid4()),
        "review_report": {"is_compliant": True, "findings": []},
        "iris_mapping": {"fields": {"7017": 580_000}},
    }

    with patch("app.workflows.taxation.orchestrator.TaxIntakeAgent.execute_intake", AsyncMock(return_value=intake_output)), \
         patch("app.workflows.taxation.orchestrator.TaxDataAgent.execute_data_and_reconciliation", AsyncMock(return_value=data_output)), \
         patch("app.workflows.taxation.orchestrator.TaxComputationAgent.execute_computation", AsyncMock(return_value=comp_output)), \
         patch("app.workflows.taxation.orchestrator.TaxReviewAgent.generate_review_and_draft", AsyncMock(return_value=review_output)), \
         patch("app.workflows.taxation.orchestrator.get_event_publisher"):

        wf = TaxWorkflowOrchestrator()
        run = await wf.initiate_workflow(
            session,
            firm_id=mock_principal.firm_id,
            client_id=client_id,
            period_id=period_id,
            engagement_id=engagement_id,
            principal=mock_principal,
        )

        # Asserts workflow paused at CA approval checkpoint
        assert run.status == "paused_approval"
        assert run.current_step == "paused_approval"
        assert run.checkpoint_id is not None
        assert "tax_ca_approval_" in run.checkpoint_id
        assert run.state_data["taxpayer_profile"]["ntn"] == "1234567-8"
        assert run.state_data["tax_computation"]["net_tax_payable"] == 580_000


@pytest.mark.asyncio
async def test_tax_workflow_resumption_and_shared_publishing(mock_principal: Principal) -> None:
    session = AsyncMock(spec=AsyncSession)
    workflow_id = uuid.uuid4()
    engagement_id = uuid.uuid4()
    client_id = uuid.uuid4()
    period_id = uuid.uuid4()
    draft_id = uuid.uuid4()

    mock_run = TaxWorkflowRun(
        id=workflow_id,
        firm_id=mock_principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        engagement_id=engagement_id,
        status="paused_approval",
        current_step="paused_approval",
        checkpoint_id="tax_ca_approval_123",
        state_data={"status": "paused_approval", "step": "paused_approval"},
    )
    mock_draft = TaxReturnDraft(
        id=draft_id,
        firm_id=mock_principal.firm_id,
        client_id=client_id,
        engagement_id=engagement_id,
        version=1,
        return_fields={},
        review_report={},
        risk_findings=[],
        status="draft",
        filing_evidence={},
    )

    session.get.return_value = mock_run

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_draft
    session.scalars.return_value = mock_scalars

    with patch("app.workflows.taxation.orchestrator.TaxReviewAgent.sign_off_tax_pack", AsyncMock(return_value=mock_draft)), \
         patch("app.workflows.taxation.orchestrator.get_event_publisher"):

        wf = TaxWorkflowOrchestrator()
        resumed = await wf.resume_after_ca_approval(
            session,
            workflow_id=workflow_id,
            principal=mock_principal,
            notes="CA approved and signed off",
        )

        assert resumed.status == "completed"
        assert resumed.current_step == "completed"
        assert resumed.checkpoint_id is None
        assert resumed.state_data["ca_approval_granted"] is True
