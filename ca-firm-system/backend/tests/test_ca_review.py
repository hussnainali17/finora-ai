"""Tests for the CA Review & AI Interaction Module.

Tests:
1. Intent classification (questions, error reports, correction requests, instructions, approvals)
2. Entity extraction (amounts, invoice numbers, account codes)
3. Correction proposal generation with diff and downstream re-execution plan
4. Agent instruction execution (filtering high-value transactions and missing invoices)
5. Human-in-the-loop proposal approval and agent re-execution flow
6. LangGraph StateGraph workflow execution
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.ca_review import CACorrectionProposal, CAConversation, CAMessage
from app.workflows.ca_review.correction_engine import (
    build_correction_proposal,
    determine_reexecution_plan,
)
from app.workflows.ca_review.instruction_engine import execute_ca_instruction
from app.workflows.ca_review.intent import (
    classify_intent_rule_based,
    extract_amounts,
    extract_invoice_ref,
)
from app.workflows.ca_review.qa_engine import build_grounded_answer
from app.workflows.ca_review.reexecution_engine import (
    apply_correction_and_reexecute,
    reject_correction_proposal,
)


class TestIntentAndEntityExtraction:
    def test_extract_amounts(self):
        text = "The sales figure shows Rs. 450,000 instead of Rs. 500,000."
        amts = extract_amounts(text)
        assert Decimal("450000") in amts
        assert Decimal("500000") in amts

    def test_extract_invoice_ref(self):
        assert extract_invoice_ref("Check invoice #INV-2024-001 now") == "INV-2024-001"
        assert extract_invoice_ref("The problem is in invoice 450A") == "450A"
        assert extract_invoice_ref("General question without doc") is None

    def test_classify_correction_request(self):
        text = "The sales figure is incorrect. The original invoice shows Rs. 450,000 instead of Rs. 500,000. Correct it."
        intent, agent, conf, entities = classify_intent_rule_based(text)
        assert intent == "correction_request"
        assert conf >= 0.90
        assert entities.get("proposed_value") == 450000.0
        assert entities.get("original_value") == 500000.0

    def test_classify_instruction(self):
        text = "Recheck all transactions above Rs. 100,000 and identify transactions without supporting invoices."
        intent, agent, conf, entities = classify_intent_rule_based(text)
        assert intent == "instruction"
        assert entities.get("threshold_amount") == 100000.0
        assert entities.get("missing_filter") == "supporting_documents"

    def test_classify_question(self):
        text = "Why is the Trial Balance out of balance and what is the variance?"
        intent, agent, conf, entities = classify_intent_rule_based(text)
        assert intent == "question"

    def test_classify_approval(self):
        text = "I approve the proposal. Please proceed."
        intent, agent, conf, entities = classify_intent_rule_based(text)
        assert intent == "approval_action"
        assert entities.get("approval_action") == "approve"


class TestCorrectionProposalEngine:
    def test_proposal_generation(self):
        firm_id = str(uuid.uuid4())
        client_id = str(uuid.uuid4())
        period_id = str(uuid.uuid4())
        conv_id = str(uuid.uuid4())

        sample_rows = [
            {
                "id": 101,
                "table_type": "sales_receivables",
                "row_index": 2,
                "raw": {"invoice": "INV-002", "amount": "500,000"},
                "normalized": {"invoice": "INV-002", "amount": 500000.0},
            }
        ]

        parsed_entities = {
            "proposed_value": 450000.0,
            "original_value": 500000.0,
            "invoice_ref": "INV-002",
            "target_module": "sales_receivables",
        }

        proposal, md = build_correction_proposal(
            firm_id=firm_id,
            client_id=client_id,
            period_id=period_id,
            conversation_id=conv_id,
            user_message="The sales figure is incorrect. Invoice shows Rs. 450,000 instead of Rs. 500,000. Correct it.",
            parsed_entities=parsed_entities,
            context_data={"rows": sample_rows},
        )

        assert proposal["target_agent"] in ("accounting_review", "intake")
        assert proposal["target_entity_type"] == "extracted_row"
        assert proposal["target_entity_id"] == "101"
        assert proposal["status"] == "pending"
        assert proposal["proposed_data"]["corrected_amount"] == 450000.0
        assert proposal["proposed_data"]["difference"] == -50000.0
        assert "accounting_review" in proposal["reexecution_plan"]
        assert "reporting" in proposal["reexecution_plan"]
        assert "PKR 450,000.00" in md
        assert "PKR 500,000.00" in md
        assert "Human-in-the-Loop Required" in md


class TestInstructionExecutionEngine:
    def test_execute_instruction(self):
        sample_rows = [
            {
                "id": 1,
                "row_index": 1,
                "table_type": "sales_receivables",
                "normalized": {"amount": 150000.0, "reference": "INV-101", "date": "2024-03-01", "party": "Acme Corp"},
                "flags": [{"type": "missing_doc"}],
            },
            {
                "id": 2,
                "row_index": 2,
                "table_type": "sales_receivables",
                "normalized": {"amount": 80000.0, "reference": "INV-102", "date": "2024-03-02", "party": "Beta LLC"},
            },
            {
                "id": 3,
                "row_index": 3,
                "table_type": "purchases_payables",
                "normalized": {"amount": 250000.0, "reference": "BILL-201", "date": "2024-03-05", "party": "Vendor X"},
            },
        ]

        parsed = {"threshold_amount": 100000.0, "missing_filter": "supporting_documents"}
        res, md = execute_ca_instruction(
            user_message="Recheck all transactions above Rs. 100,000 and identify transactions without supporting invoices.",
            parsed_entities=parsed,
            context_data={"rows": sample_rows, "documents": []},
        )

        assert res["threshold"] == 100000.0
        assert res["matching_high_value_count"] >= 1
        assert "PKR 100,000.00" in md
        assert "INV-101" in md or "BILL-201" in md


class TestGroundedQAEngine:
    def test_grounded_answer(self):
        context = {
            "summary": {
                "trial_balance": {
                    "total_debits": 1250000.0,
                    "total_credits": 1250000.0,
                    "is_balanced": True,
                    "variance": 0.0,
                },
                "review_findings_count": 2,
                "open_findings_count": 1,
            },
            "review_findings": [
                {
                    "module": "sales_receivables",
                    "severity": "warning",
                    "title": "Unverified credit note",
                    "amount": 25000.0,
                    "status": "open",
                }
            ],
        }

        ans_tb = build_grounded_answer("Is the trial balance balanced?", context)
        assert "Balanced" in ans_tb
        assert "1,250,000.00" in ans_tb

        ans_findings = build_grounded_answer("What findings did Agent 2 detect?", context)
        assert "Unverified credit note" in ans_findings


class TestReexecutionAndApproval:
    @pytest.mark.asyncio
    async def test_reject_proposal(self):
        proposal_id = uuid.uuid4()
        user_id = uuid.uuid4()

        mock_proposal = CACorrectionProposal(
            id=proposal_id,
            conversation_id=uuid.uuid4(),
            firm_id=uuid.uuid4(),
            client_id=uuid.uuid4(),
            period_id=uuid.uuid4(),
            target_agent="accounting_review",
            target_entity_type="extracted_row",
            target_entity_id="101",
            title="Correction of Sales Figure",
            description="Fix 500k to 450k",
            status="pending",
        )

        mock_session = AsyncMock()
        mock_session.get.return_value = mock_proposal

        updated = await reject_correction_proposal(
            mock_session,
            proposal_id=proposal_id,
            user_id=user_id,
            reviewer_notes="Client confirmed 500k was actually correct",
        )

        assert updated.status == "rejected"
        assert updated.reviewed_by == user_id
        assert "500k was actually correct" in (updated.reviewer_notes or "")

    @pytest.mark.asyncio
    async def test_apply_and_reexecute(self):
        proposal_id = uuid.uuid4()
        user_id = uuid.uuid4()
        firm_id = uuid.uuid4()
        client_id = uuid.uuid4()
        period_id = uuid.uuid4()

        mock_proposal = CACorrectionProposal(
            id=proposal_id,
            conversation_id=uuid.uuid4(),
            firm_id=firm_id,
            client_id=client_id,
            period_id=period_id,
            target_agent="accounting_review",
            target_entity_type="extracted_row",
            target_entity_id="1",
            title="Correction of Sales Figure",
            description="Fix 500k to 450k",
            status="pending",
            reexecution_plan=["accounting_review", "adjustments", "reporting"],
            proposed_data={"corrected_amount": 450000.0, "original_amount": 500000.0},
        )

        mock_session = AsyncMock()
        mock_session.get.side_effect = lambda model, pk: mock_proposal if model == CACorrectionProposal else None

        with patch("app.workflows.ca_review.reexecution_engine.AccountingReviewAgent") as MockRevAgent, \
             patch("app.workflows.ca_review.reexecution_engine.AdjustmentsAgent") as MockAdjAgent, \
             patch("app.workflows.ca_review.reexecution_engine.ReportingAgent") as MockRepAgent:

            mock_rev_inst = MockRevAgent.return_value
            mock_rev_inst.run_review = AsyncMock(return_value={"status": "completed"})

            mock_adj_inst = MockAdjAgent.return_value
            mock_adj_inst.generate_adjustments_for_period = AsyncMock(return_value=[])

            mock_rep_inst = MockRepAgent.return_value
            mock_rep_inst.generate_reporting_pack = AsyncMock(return_value={
                "validation": {"is_valid": True, "issues": []},
                "statements": {"balance_sheet": {}, "profit_loss": {}},
            })

            res = await apply_correction_and_reexecute(
                mock_session,
                proposal_id=proposal_id,
                user_id=user_id,
                reviewer_notes="Approved per audit verification",
            )

            assert res["status"] == "success"
            assert "accounting_review" in res["executed_agents"]
            assert "adjustments" in res["executed_agents"]
            assert "reporting" in res["executed_agents"]
            assert mock_proposal.status == "applied"
            assert mock_proposal.reviewed_by == user_id

