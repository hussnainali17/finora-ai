"""Tests for Complete CA Multi-Module Workflow Orchestrator."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal
from app.models.identity import AccountingPeriod, Client
from app.models.shared_data import ApprovedModuleOutput
from app.models.taxation import (
    MultiModuleWorkflowRun,
    TaxEngagement,
    TaxReturnDraft,
    TaxWorkflowRun,
)
from app.models.workflows import WorkflowRun
from app.workflows.coordination.complete_workflow import CompleteCAWorkflowOrchestrator


@pytest.fixture
def mock_principal() -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        firm_id=uuid.uuid4(),
        email="partner@cafirm.com",
        full_name="Senior Partner",
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
            "report:read",
        }),
        session_id=uuid.uuid4(),
    )


@pytest.mark.asyncio
async def test_complete_ca_workflow_lifecycle(mock_principal: Principal) -> None:
    session = AsyncMock(spec=AsyncSession)
    firm_id = mock_principal.firm_id
    client_id = uuid.uuid4()
    period_id = uuid.uuid4()
    eng_id = uuid.uuid4()
    complete_wf_id = uuid.uuid4()

    mock_client = Client(id=client_id, firm_id=firm_id, name="Prime Industries Ltd")
    mock_period = AccountingPeriod(id=period_id, firm_id=firm_id, client_id=client_id, label="FY2025")
    mock_eng = TaxEngagement(id=eng_id, firm_id=firm_id, client_id=client_id, period_id=period_id, tax_year=2025)

    mock_acct_run_paused = WorkflowRun(
        id=uuid.uuid4(),
        firm_id=firm_id,
        client_id=client_id,
        period_id=period_id,
        status="paused_approval",
        current_step="ca_approval",
    )

    mock_shared_output = ApprovedModuleOutput(
        id=uuid.uuid4(),
        firm_id=firm_id,
        client_id=client_id,
        period_id=period_id,
        module="accounting",
        version=1,
        status="approved",
        data={"profit_loss": {"net_profit": 5_000_000}},
        summary={"net_profit": 5_000_000, "total_revenue": 25_000_000},
        source_version_refs={},
        validation_results={"is_valid": True},
    )

    mock_tax_run_paused = TaxWorkflowRun(
        id=uuid.uuid4(),
        firm_id=firm_id,
        client_id=client_id,
        period_id=period_id,
        engagement_id=eng_id,
        status="paused_approval",
        current_step="paused_approval",
        checkpoint_id="tax_gate_1",
        state_data={"status": "paused_approval"},
    )

    mock_tax_draft = TaxReturnDraft(
        id=uuid.uuid4(),
        firm_id=firm_id,
        client_id=client_id,
        engagement_id=eng_id,
        version=1,
        return_fields={"7005": 5_000_000, "7008": 5_000_000, "7013": 1_450_000, "7017": 1_450_000},
        review_report={"is_compliant": True},
        risk_findings=[],
        status="ca_approved",
        filing_evidence={},
    )

    # Database entity lookups
    session.get.side_effect = lambda model, obj_id: {
        AccountingPeriod: mock_period if obj_id == period_id else None,
        Client: mock_client if obj_id == client_id else None,
        MultiModuleWorkflowRun: None,  # overridden per step
    }.get(model)

    mock_scalars = MagicMock()
    mock_scalars.first.side_effect = [
        mock_eng,           # TaxEngagement lookup
        mock_tax_draft,     # TaxReturnDraft lookup for cross-validation
    ]
    session.scalars.return_value = mock_scalars

    with patch("app.workflows.coordination.complete_workflow.WorkflowOrchestrator.initiate_workflow", AsyncMock(return_value=mock_acct_run_paused)), \
         patch("app.workflows.coordination.complete_workflow.get_latest_approved_accounting_output", AsyncMock(return_value=mock_shared_output)), \
         patch("app.workflows.coordination.complete_workflow.TaxWorkflowOrchestrator.initiate_workflow", AsyncMock(return_value=mock_tax_run_paused)), \
         patch("app.workflows.coordination.complete_workflow.get_event_publisher"):

        orch = CompleteCAWorkflowOrchestrator()

        # Step 1: Initiate Complete Workflow
        complete_run = await orch.initiate_complete_workflow(
            session,
            firm_id=firm_id,
            client_id=client_id,
            period_id=period_id,
            principal=mock_principal,
            tax_year=2025,
        )

        assert complete_run.status == "paused_accounting_approval"
        assert complete_run.current_module == "accounting_gate"
        assert "complete_acct_gate_" in complete_run.checkpoint_id

        # Step 2: Resume after Accounting Approval -> launches Taxation
        complete_run.id = complete_wf_id
        session.get.side_effect = lambda model, obj_id: {
            MultiModuleWorkflowRun: complete_run if obj_id == complete_wf_id else None,
            AccountingPeriod: mock_period if obj_id == period_id else None,
            Client: mock_client if obj_id == client_id else None,
        }.get(model)

        with patch("app.workflows.coordination.complete_workflow.WorkflowOrchestrator.resume_after_ca_approval", AsyncMock(return_value=mock_acct_run_paused)):
            resumed_tax_gate = await orch.resume_complete_workflow(
                session,
                workflow_id=complete_wf_id,
                principal=mock_principal,
                notes="Accounting adjustments approved",
            )
            assert resumed_tax_gate.status == "paused_taxation_approval"
            assert resumed_tax_gate.current_module == "taxation_gate"

        # Step 3: Resume after Taxation Approval -> Cross-validation & Consolidated Report
        mock_scalars.first.side_effect = [mock_tax_draft]
        with patch("app.workflows.coordination.complete_workflow.TaxWorkflowOrchestrator.resume_after_ca_approval", AsyncMock()):
            resumed_final = await orch.resume_complete_workflow(
                session,
                workflow_id=complete_wf_id,
                principal=mock_principal,
                notes="Tax return calculations approved",
            )
            assert resumed_final.status == "paused_final_signoff"
            assert resumed_final.current_module == "final_ca_review"
            cross_val = resumed_final.state_data["cross_module_validation"]
            assert cross_val["statements_tied_to_tax"] is True
            assert cross_val["difference"] == 0.0

        # Step 4: Final CA Sign-Off
        final_completed = await orch.resume_complete_workflow(
            session,
            workflow_id=complete_wf_id,
            principal=mock_principal,
            notes="Consolidated pack approved for filing",
        )
        assert final_completed.status == "completed"
        assert final_completed.current_module == "completed"
        assert final_completed.state_data["ca_final_signoff"] is True
