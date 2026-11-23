"""LangGraph end-to-end orchestration for the 4 CA Firm System agents.

Flow:
1. Files uploaded & structured (Agent 1 Intake Gate)
2. Data quality review gate (Staff correction if needed)
3. Accounting review & reconciliation (Agent 2)
4. Period-end adjustments proposed (Agent 3)
5. HUMAN-IN-THE-LOOP PAUSE: Workflow pauses at checkpoint for CA approval
6. Resume after CA approval -> Financial Reporting & validation (Agent 4)
7. Final validation gate -> CA final sign-off
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.agents.accounting_review_agent.agent import AccountingReviewAgent
from app.agents.adjustments_agent.agent import AdjustmentsAgent
from app.agents.reporting_agent.agent import ReportingAgent
from app.integrations.kafka import WORKFLOW_STATUS, get_event_publisher
from app.integrations.kafka.publisher import EventEnvelope
from app.models import DataQualityFinding, ExtractedTable
from app.models.accounting_review import ReviewRun
from app.models.adjustments import PeriodAdjustment
from app.models.reporting import FinancialReport
from app.models.workflows import WorkflowRun

logger = logging.getLogger("app.workflows.orchestrator")


class AgentWorkflowState(TypedDict):
    workflow_id: str
    firm_id: str
    client_id: str
    period_id: str
    step: str
    status: Literal["running", "paused_approval", "completed", "failed"]
    data_quality_passed: bool
    review_completed: bool
    adjustments_count: int
    ca_approval_granted: bool
    reporting_completed: bool
    validation_passed: bool
    error: str | None


class WorkflowOrchestrator:
    """Coordinates the 4 agents across checkpoints and human-in-the-loop pauses."""

    async def initiate_workflow(
        self,
        session: AsyncSession,
        *,
        firm_id: uuid.UUID,
        client_id: uuid.UUID,
        period_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> WorkflowRun:
        """Starts a new end-to-end workflow run."""
        run = WorkflowRun(
            firm_id=firm_id,
            client_id=client_id,
            period_id=period_id,
            status="running",
            current_step="data_quality_gate",
            initiated_by=user_id,
            state_data={
                "workflow_id": "",
                "firm_id": str(firm_id),
                "client_id": str(client_id),
                "period_id": str(period_id),
                "step": "data_quality_gate",
                "status": "running",
                "data_quality_passed": False,
                "review_completed": False,
                "adjustments_count": 0,
                "ca_approval_granted": False,
                "reporting_completed": False,
                "validation_passed": False,
                "error": None,
            },
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)

        run.state_data["workflow_id"] = str(run.id)
        await session.commit()

        # Execute first phase
        await self._step_next(session, run)
        await session.refresh(run)
        return run

    async def _step_next(self, session: AsyncSession, run: WorkflowRun) -> None:
        """Executes the workflow graph forward until a checkpoint or terminal state."""
        state: AgentWorkflowState = run.state_data  # type: ignore[assignment]
        firm_id = uuid.UUID(state["firm_id"])
        client_id = uuid.UUID(state["client_id"])
        period_id = uuid.UUID(state["period_id"])

        try:
            # Step 1: Data Quality Gate
            if run.current_step == "data_quality_gate":
                logger.info("orchestrator: checking data quality gate", extra={"run_id": str(run.id)})
                # Check that at least one table is extracted
                tbls = await session.scalars(
                    select(ExtractedTable).where(
                        ExtractedTable.firm_id == firm_id,
                        ExtractedTable.client_id == client_id,
                        ExtractedTable.period_id == period_id,
                    )
                )
                if not tbls.all():
                    run.status = "failed"
                    run.error_message = "No extracted documents found for this period."
                    state["error"] = run.error_message
                    await session.commit()
                    return

                # Check if there are unreviewed critical error findings
                err_findings = await session.scalars(
                    select(DataQualityFinding).where(
                        DataQualityFinding.firm_id == firm_id,
                        DataQualityFinding.client_id == client_id,
                        DataQualityFinding.period_id == period_id,
                        DataQualityFinding.severity == "error",
                        DataQualityFinding.status == "open",
                    )
                )
                if err_findings.all():
                    # Block at quality gate until staff reviews
                    run.status = "paused_approval"
                    run.current_step = "data_quality_gate"
                    run.checkpoint_id = f"quality_gate_{run.id}"
                    run.error_message = "Data quality gate: open error findings require staff resolution."
                    state["status"] = "paused_approval"
                    await session.commit()
                    await self._emit_status(run)
                    return

                # Accounting Agent 1: Accounting Intake & Preparation
                from app.agents.intake_agent.agent import AccountingIntakePreparationAgent
                intake_prep_agent = AccountingIntakePreparationAgent()
                prep_result = await intake_prep_agent.execute_intake_preparation(
                    session,
                    firm_id=firm_id,
                    client_id=client_id,
                    period_id=period_id,
                )
                state["intake_record_id"] = prep_result.get("intake_record_id")
                state["transactions_count"] = prep_result.get("transactions_count", 0)

                state["data_quality_passed"] = True
                run.current_step = "accounting_review"

            # Step 2: Accounting Review (Agent 2)
            if run.current_step == "accounting_review":
                logger.info("orchestrator: executing accounting review", extra={"run_id": str(run.id)})
                review_run = ReviewRun(
                    firm_id=firm_id,
                    client_id=client_id,
                    period_id=period_id,
                    status="running",
                    trigger="auto",
                )
                session.add(review_run)
                await session.commit()
                await session.refresh(review_run)

                rev_agent = AccountingReviewAgent()
                await rev_agent.run_review(
                    session,
                    review_run_id=review_run.id,
                    client_id=client_id,
                    period_id=period_id,
                    firm_id=firm_id,
                )
                state["review_completed"] = True
                run.current_step = "period_adjustments"
                await session.commit()

            # Step 3: Period-End Adjustments (Agent 3)
            if run.current_step == "period_adjustments":
                logger.info("orchestrator: generating period adjustments", extra={"run_id": str(run.id)})
                adj_agent = AdjustmentsAgent()
                adjustments = await adj_agent.generate_adjustments_for_period(
                    session,
                    client_id=client_id,
                    period_id=period_id,
                    firm_id=firm_id,
                )
                state["adjustments_count"] = len(adjustments)

                # Step 4: HUMAN-IN-THE-LOOP CHECKPOINT: Pause for CA Review
                if adjustments:
                    run.status = "paused_approval"
                    run.current_step = "ca_approval"
                    run.checkpoint_id = f"ca_approval_{run.id}"
                    state["status"] = "paused_approval"
                    state["step"] = "ca_approval"
                    await session.commit()
                    await self._emit_status(run)
                    logger.info("orchestrator paused at CA approval checkpoint", extra={"run_id": str(run.id)})
                    return
                else:
                    state["ca_approval_granted"] = True
                    run.current_step = "financial_reporting"

            # Step 5: Financial Reporting & Validation (Agent 4)
            if run.current_step == "financial_reporting":
                logger.info("orchestrator: generating financial statements", extra={"run_id": str(run.id)})
                rep_agent = ReportingAgent()
                rep_result = await rep_agent.generate_reporting_pack(
                    session,
                    client_id=client_id,
                    period_id=period_id,
                    firm_id=firm_id,
                )
                state["reporting_completed"] = True
                state["validation_passed"] = rep_result["validation"]["is_valid"]
                run.current_step = "completed"
                run.status = "completed"
                state["status"] = "completed"
                state["step"] = "completed"

                # Publish to Central Shared Data Layer
                try:
                    from app.api.deps import Principal
                    from app.services.shared_data import publish_approved_accounting_output

                    actor_id = run.initiated_by or uuid.uuid4()
                    system_principal = Principal(
                        user_id=actor_id,
                        firm_id=firm_id,
                        email="system@orchestrator.internal",
                        full_name="Workflow System",
                        role_key="ca_reviewer",
                        permissions=frozenset({"shared:publish", "client:read"}),
                        session_id=uuid.uuid4(),
                    )
                    pub_output = await publish_approved_accounting_output(
                        session,
                        system_principal,
                        client_id=client_id,
                        period_id=period_id,
                        notes="Auto-published from completed Accounting Workflow",
                    )
                    state["published_output_id"] = str(pub_output.id)
                except Exception as pub_exc:
                    logger.warning("Could not auto-publish accounting output to shared data layer: %s", pub_exc)

                flag_modified(run, "state_data")
                await session.commit()
                await self._emit_status(run)
                logger.info("orchestrator completed successfully", extra={"run_id": str(run.id)})

        except Exception as exc:
            logger.exception("orchestrator execution error", extra={"run_id": str(run.id)})
            run.status = "failed"
            run.error_message = str(exc)
            state["status"] = "failed"
            state["error"] = str(exc)
            flag_modified(run, "state_data")
            await session.commit()
            await self._emit_status(run)

    async def resume_after_ca_approval(
        self,
        session: AsyncSession,
        workflow_id: uuid.UUID,
    ) -> WorkflowRun:
        """Resumes workflow execution after CA review decision has been recorded."""
        run = await session.get(WorkflowRun, workflow_id)
        if not run:
            raise ValueError("Workflow run not found")
        if run.status != "paused_approval":
            raise ValueError(f"Workflow cannot be resumed from status '{run.status}'")

        run.status = "running"
        run.current_step = "financial_reporting"
        run.checkpoint_id = None
        run.state_data["ca_approval_granted"] = True
        run.state_data["status"] = "running"
        run.state_data["step"] = "financial_reporting"
        flag_modified(run, "state_data")
        await session.commit()

        await self._step_next(session, run)
        await session.refresh(run)
        return run

    async def _emit_status(self, run: WorkflowRun) -> None:
        """Publishes Kafka workflow-status event."""
        try:
            pub = get_event_publisher()
            envelope = EventEnvelope(
                event_type="workflow.status",
                schema_version=1,
                tenant_id=run.firm_id,
                client_id=run.client_id,
                accounting_period_id=run.period_id,
                correlation_id=str(run.id),
                payload={
                    "workflow_id": str(run.id),
                    "status": run.status,
                    "step": run.current_step,
                    "error_message": run.error_message or "",
                },
            )
            await pub.publish(WORKFLOW_STATUS, str(run.id), envelope)
        except Exception:
            logger.warning("failed to publish workflow-status kafka event")


AccountingWorkflowOrchestrator = WorkflowOrchestrator

