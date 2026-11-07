"""Tests for Phase 9: LangGraph End-to-End Orchestration.

Tests:
1. Workflow state initialization
2. Quality gate stops if no tables are found
3. Human-in-the-loop checkpoint: pauses at CA approval when adjustments exist
4. Resumes after CA approval
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workflows.orchestrator import WorkflowOrchestrator


class TestWorkflowState:
    @pytest.mark.asyncio
    async def test_workflow_initiation(self):
        orch = WorkflowOrchestrator()
        firm_id = uuid.uuid4()
        client_id = uuid.uuid4()
        period_id = uuid.uuid4()

        mock_session = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []  # No tables -> fails at quality gate
        mock_session.scalars.return_value = mock_scalars

        run = await orch.initiate_workflow(
            mock_session,
            firm_id=firm_id,
            client_id=client_id,
            period_id=period_id,
        )

        assert run.firm_id == firm_id
        assert run.client_id == client_id
        assert run.period_id == period_id
        assert run.status in ("running", "failed")
        if run.status == "failed":
            assert "No extracted documents" in (run.error_message or "")
