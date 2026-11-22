"""Independent LangGraph workflow execution for the Pakistan Taxation Module.

Flow:
1. Agent 1: Tax Intake & Taxpayer Profile (determines obligations, flags missing data)
2. Agent 2: Tax Data & Reconciliation (consumes approved accounting outputs or direct client records)
3. Agent 3: Tax Computation & Compliance (deterministic Pakistan tax rules engine)
4. Agent 4: Tax Review & Filing Pack (cross-checks, IRIS return draft)
5. HUMAN-IN-THE-LOOP CHECKPOINT: Pauses for CA review and sign-off
6. CA Approval: Publishes approved tax outputs to the Central Shared Data Layer
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.agents.tax_computation_agent.agent import TaxComputationAgent
from app.agents.tax_data_agent.agent import TaxDataAgent
from app.agents.tax_intake_agent.agent import TaxIntakeAgent
from app.agents.tax_review_agent.agent import TaxReviewAgent
from app.api.deps import Principal
from app.integrations.kafka import WORKFLOW_STATUS, get_event_publisher
from app.integrations.kafka.publisher import EventEnvelope
from app.models.taxation import (
    TaxEngagement,
    TaxReturnDraft,
    TaxWorkflowRun,
    TaxpayerProfile,
)
from app.workflows.states.taxation_state import TaxationModuleState

logger = logging.getLogger("app.workflows.taxation")


class TaxWorkflowOrchestrator:
    """Coordinates the 4 Pakistan Tax agents with independent checkpoints and CA approval gate."""

    async def initiate_workflow(
        self,
        session: AsyncSession,
        *,
        firm_id: uuid.UUID,
        client_id: uuid.UUID,
        period_id: uuid.UUID,
        engagement_id: uuid.UUID,
        principal: Principal,
        source_origin: str = "approved_accounting",
        accounting_version: int | None = None,
    ) -> TaxWorkflowRun:
        """Starts a new independent taxation workflow run."""
        engagement = await session.get(TaxEngagement, engagement_id)
        if not engagement:
            raise ValueError(f"TaxEngagement {engagement_id} not found.")

        initial_state: TaxationModuleState = {
            "workflow_id": "",
            "firm_id": str(firm_id),
            "client_id": str(client_id),
            "period_id": str(period_id),
            "engagement_id": str(engagement_id),
            "tax_year": engagement.tax_year,
            "step": "intake_profile",
            "status": "running",
            "taxpayer_profile": {},
            "obligations": [],
            "missing_information": [],
            "source_data_origin": source_origin,  # type: ignore[typeddict-item]
            "accounting_output_version": accounting_version,
            "tax_mapping": {},
            "reconciliations": {},
            "reconciliation_exceptions": [],
            "tax_rule_version": "",
            "tax_computation": {},
            "calculation_trace": [],
            "return_schedules": {},
            "validation_results": {},
            "risk_findings": [],
            "filing_pack": {},
            "ca_approval_granted": False,
            "published_output_id": None,
            "is_outdated": False,
            "stale_reason": None,
            "error": None,
        }

        run = TaxWorkflowRun(
            firm_id=firm_id,
            client_id=client_id,
            period_id=period_id,
            engagement_id=engagement_id,
            status="running",
            current_step="intake_profile",
            initiated_by=principal.user_id,
            state_data=initial_state,  # type: ignore[arg-type]
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)

        run.state_data["workflow_id"] = str(run.id)
        await session.commit()

        # Execute workflow forward
        await self._step_next(session, run, principal)
        await session.refresh(run)
        return run

    async def _step_next(
        self,
        session: AsyncSession,
        run: TaxWorkflowRun,
        principal: Principal,
    ) -> None:
        """Executes taxation workflow graph forward until CA approval checkpoint or completion."""
        state: TaxationModuleState = run.state_data  # type: ignore[assignment]
        engagement_id = uuid.UUID(state["engagement_id"])

        try:
            # Step 1: Agent 1 (Tax Intake & Taxpayer Profile)
            if run.current_step == "intake_profile":
                logger.info("tax_orchestrator: running Agent 1 Tax Intake", extra={"run_id": str(run.id)})
                intake_agent = TaxIntakeAgent()
                intake_res = await intake_agent.execute_intake(
                    session,
                    engagement_id=engagement_id,
                )
                state["taxpayer_profile"] = intake_res["taxpayer_profile"]
                state["obligations"] = intake_res["obligations"]
                state["missing_information"] = intake_res["missing_information"]
                run.current_step = "data_reconciliation"
                state["step"] = "data_reconciliation"
                await session.commit()

            # Step 2: Agent 2 (Tax Data & Reconciliation)
            if run.current_step == "data_reconciliation":
                logger.info("tax_orchestrator: running Agent 2 Tax Data & Reconciliation", extra={"run_id": str(run.id)})
                data_agent = TaxDataAgent()
                data_res = await data_agent.execute_data_and_reconciliation(
                    session,
                    engagement_id=engagement_id,
                    principal=principal,
                    source_origin_preference=state.get("source_data_origin", "approved_accounting"),
                    version=state.get("accounting_output_version"),
                )
                state["source_data_origin"] = data_res["source_origin"]
                state["accounting_output_version"] = data_res["accounting_version"]
                state["tax_mapping"] = data_res["mapping"]
                state["reconciliations"] = data_res["reconciliations"]
                state["reconciliation_exceptions"] = data_res["exceptions"]
                run.current_step = "computation_compliance"
                state["step"] = "computation_compliance"
                await session.commit()

            # Step 3: Agent 3 (Tax Computation & Compliance)
            if run.current_step == "computation_compliance":
                logger.info("tax_orchestrator: running Agent 3 Tax Computation", extra={"run_id": str(run.id)})
                comp_agent = TaxComputationAgent()
                comp_res = await comp_agent.execute_computation(
                    session,
                    engagement_id=engagement_id,
                )
                state["tax_rule_version"] = comp_res["rule_set_version"]
                state["tax_computation"] = comp_res["income_tax"]
                state["calculation_trace"] = comp_res["income_tax"].get("calculation_trace", [])
                run.current_step = "review_filing_pack"
                state["step"] = "review_filing_pack"
                await session.commit()

            # Step 4: Agent 4 (Tax Review & Filing Pack)
            if run.current_step == "review_filing_pack":
                logger.info("tax_orchestrator: running Agent 4 Tax Review & Filing Pack", extra={"run_id": str(run.id)})
                review_agent = TaxReviewAgent()
                review_res = await review_agent.generate_review_and_draft(
                    session,
                    engagement_id=engagement_id,
                )
                state["validation_results"] = review_res["review_report"]
                state["risk_findings"] = review_res["review_report"].get("findings", [])
                state["filing_pack"] = review_res["iris_mapping"]

                # HUMAN-IN-THE-LOOP CHECKPOINT: Pause for CA Review & Sign-Off
                run.status = "paused_approval"
                run.current_step = "paused_approval"
                run.checkpoint_id = f"tax_ca_approval_{run.id}"
                state["status"] = "paused_approval"
                state["step"] = "paused_approval"
                flag_modified(run, "state_data")
                await session.commit()
                await self._emit_status(run)
                logger.info("tax_orchestrator paused at CA approval checkpoint", extra={"run_id": str(run.id)})
                return

        except Exception as exc:
            logger.exception("tax_orchestrator execution error", extra={"run_id": str(run.id)})
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
        principal: Principal,
        notes: str | None = None,
    ) -> TaxWorkflowRun:
        """Resumes workflow execution after CA reviewer grants approval."""
        run = await session.get(TaxWorkflowRun, workflow_id)
        if not run:
            raise ValueError("TaxWorkflowRun not found")
        if run.status != "paused_approval":
            raise ValueError(f"TaxWorkflowRun cannot be resumed from status '{run.status}'")

        # 1. Fetch draft to approve
        draft_res = await session.scalars(
            select(TaxReturnDraft)
            .where(TaxReturnDraft.engagement_id == run.engagement_id)
            .order_by(desc(TaxReturnDraft.version))
        )
        draft = draft_res.first()
        if not draft:
            raise ValueError("Draft return not found to sign off.")

        # 2. Formal CA Sign-off via Agent 4 (which publishes to Central Shared Data Layer)
        review_agent = TaxReviewAgent()
        signed_draft = await review_agent.sign_off_tax_pack(
            session,
            principal,
            draft_id=draft.id,
            notes=notes or "Approved and finalized in Tax Workflow",
        )

        run.status = "completed"
        run.current_step = "completed"
        run.checkpoint_id = None
        run.state_data["ca_approval_granted"] = True
        run.state_data["status"] = "completed"
        run.state_data["step"] = "completed"
        run.state_data["published_output_id"] = str(signed_draft.id)
        flag_modified(run, "state_data")
        await session.commit()
        await self._emit_status(run)

        logger.info("tax_orchestrator completed successfully after CA approval", extra={"run_id": str(run.id)})
        return run

    async def _emit_status(self, run: TaxWorkflowRun) -> None:
        """Publishes Kafka workflow status event."""
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
                    "workflow_type": "taxation",
                    "workflow_id": str(run.id),
                    "engagement_id": str(run.engagement_id),
                    "status": run.status,
                    "step": run.current_step,
                    "error_message": run.error_message or "",
                },
            )
            await pub.publish(WORKFLOW_STATUS, str(run.id), envelope)
        except Exception:
            logger.warning("failed to publish tax workflow-status kafka event")
