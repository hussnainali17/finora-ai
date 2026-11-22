"""Complete CA Workflow Orchestrator.

Coordinates the end-to-end multi-module CA lifecycle:
1. Shared Document Ingestion Check
2. Execute Accounting Module
3. Wait for CA Accounting Approval (Human-in-the-loop gate)
4. Publish Approved Accounting Outputs to Central Shared Data Layer
5. Execute Taxation Module using newly published Accounting version
6. Wait for CA Taxation Approval (Human-in-the-loop gate)
7. Cross-Module Validation (verifies tie-out between statements and tax bridge)
8. Generate Consolidated Report & Exceptions
9. Final CA Sign-off

Future Extensibility:
- Audit Module can be slotted into this orchestrator as an independent downstream step
  without modifying Accounting or Taxation execution.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import Principal
from app.integrations.kafka import WORKFLOW_STATUS, get_event_publisher
from app.integrations.kafka.publisher import EventEnvelope
from app.models.identity import AccountingPeriod, Client
from app.models.reporting import FinancialReport
from app.models.shared_data import ApprovedModuleOutput
from app.models.taxation import (
    MultiModuleWorkflowRun,
    TaxEngagement,
    TaxReturnDraft,
    TaxWorkflowRun,
)
from app.models.workflows import WorkflowRun
from app.services.shared_data import (
    get_latest_approved_accounting_output,
    publish_approved_accounting_output,
)
from app.workflows.orchestrator import WorkflowOrchestrator
from app.workflows.states.orchestrator_state import CompleteCAWorkflowState
from app.workflows.taxation.orchestrator import TaxWorkflowOrchestrator

logger = logging.getLogger("app.workflows.complete_ca")


class CompleteCAWorkflowOrchestrator:
    """Orchestrates multi-module Accounting -> Gate -> Shared Layer -> Taxation -> Cross-Validation -> Final Sign-off."""

    async def initiate_complete_workflow(
        self,
        session: AsyncSession,
        *,
        firm_id: uuid.UUID,
        client_id: uuid.UUID,
        period_id: uuid.UUID,
        principal: Principal,
        tax_year: int = 2025,
    ) -> MultiModuleWorkflowRun:
        """Starts a new top-level Complete CA Workflow run."""
        # Find or create a tax engagement for this period
        eng_res = await session.scalars(
            select(TaxEngagement).where(
                TaxEngagement.firm_id == firm_id,
                TaxEngagement.client_id == client_id,
                TaxEngagement.period_id == period_id,
            )
        )
        tax_eng = eng_res.first()
        if not tax_eng:
            period = await session.get(AccountingPeriod, period_id)
            tax_eng = TaxEngagement(
                firm_id=firm_id,
                client_id=client_id,
                period_id=period_id,
                tax_year=tax_year,
                tax_period_label=period.label if period else f"TY{tax_year}",
                tax_type="composite",
                status="draft",
                assigned_to=principal.user_id,
            )
            session.add(tax_eng)
            await session.commit()
            await session.refresh(tax_eng)

        initial_state: CompleteCAWorkflowState = {
            "workflow_id": "",
            "firm_id": str(firm_id),
            "client_id": str(client_id),
            "period_id": str(period_id),
            "tax_engagement_id": str(tax_eng.id),
            "current_module": "accounting",
            "status": "running",
            "accounting_workflow_id": None,
            "accounting_output_id": None,
            "accounting_output_version": None,
            "accounting_approved": False,
            "taxation_workflow_id": None,
            "taxation_output_id": None,
            "taxation_output_version": None,
            "taxation_approved": False,
            "cross_module_validation": {},
            "consolidated_report": {},
            "ca_final_signoff": False,
            "error": None,
        }

        run = MultiModuleWorkflowRun(
            firm_id=firm_id,
            client_id=client_id,
            period_id=period_id,
            status="running",
            current_module="accounting",
            initiated_by=principal.user_id,
            state_data=initial_state,  # type: ignore[arg-type]
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)

        run.state_data["workflow_id"] = str(run.id)
        await session.commit()

        # Step 1: Launch Accounting Workflow
        acct_wf = WorkflowOrchestrator()
        acct_run = await acct_wf.initiate_workflow(
            session,
            firm_id=firm_id,
            client_id=client_id,
            period_id=period_id,
            user_id=principal.user_id,
        )
        run.state_data["accounting_workflow_id"] = str(acct_run.id)

        # Check if Accounting paused for CA approval
        if acct_run.status == "paused_approval":
            run.status = "paused_accounting_approval"
            run.current_module = "accounting_gate"
            run.checkpoint_id = f"complete_acct_gate_{run.id}"
            flag_modified(run, "state_data")
            await session.commit()
            await self._emit_status(run)
            return run

        # If accounting completed automatically without adjustments
        await self._continue_after_accounting(session, run, principal)
        return run

    async def resume_complete_workflow(
        self,
        session: AsyncSession,
        *,
        workflow_id: uuid.UUID,
        principal: Principal,
        notes: str | None = None,
    ) -> MultiModuleWorkflowRun:
        """Resumes Complete CA Workflow after approval at accounting, taxation, or final signoff gates."""
        run = await session.get(MultiModuleWorkflowRun, workflow_id)
        if not run:
            raise ValueError("MultiModuleWorkflowRun not found")

        state: CompleteCAWorkflowState = run.state_data  # type: ignore[assignment]

        # Gate 1: Accounting Approval Gate
        if run.status == "paused_accounting_approval":
            acct_run_id = uuid.UUID(state["accounting_workflow_id"])  # type: ignore[arg-type]
            acct_wf = WorkflowOrchestrator()
            await acct_wf.resume_after_ca_approval(session, acct_run_id)

            await self._continue_after_accounting(session, run, principal)
            return run

        # Gate 2: Taxation Approval Gate
        if run.status == "paused_taxation_approval":
            tax_run_id = uuid.UUID(state["taxation_workflow_id"])  # type: ignore[arg-type]
            tax_wf = TaxWorkflowOrchestrator()
            await tax_wf.resume_after_ca_approval(session, tax_run_id, principal, notes=notes)

            await self._continue_after_taxation(session, run, principal)
            return run

        # Gate 3: Final Consolidated Sign-Off
        if run.status == "paused_final_signoff":
            run.status = "completed"
            run.current_module = "completed"
            run.checkpoint_id = None
            state["ca_final_signoff"] = True
            state["status"] = "completed"
            state["current_module"] = "completed"
            flag_modified(run, "state_data")
            await session.commit()
            await self._emit_status(run)
            return run

        raise ValueError(f"Workflow cannot be resumed from status '{run.status}'")

    async def _continue_after_accounting(
        self,
        session: AsyncSession,
        run: MultiModuleWorkflowRun,
        principal: Principal,
    ) -> None:
        """Publishes approved accounting outputs and triggers Taxation."""
        state: CompleteCAWorkflowState = run.state_data  # type: ignore[assignment]
        client_id = uuid.UUID(state["client_id"])
        period_id = uuid.UUID(state["period_id"])

        # 1. Publish / verify approved accounting outputs in Central Shared Data Layer
        pub_out = await get_latest_approved_accounting_output(
            session, principal, client_id=client_id, period_id=period_id
        )
        if not pub_out:
            pub_out = await publish_approved_accounting_output(
                session, principal, client_id=client_id, period_id=period_id, notes="Auto-published from Complete CA Workflow"
            )

        state["accounting_approved"] = True
        state["accounting_output_id"] = str(pub_out.id)
        state["accounting_output_version"] = pub_out.version

        # 2. Trigger Taxation Module consuming this approved version
        tax_eng_id = uuid.UUID(state["tax_engagement_id"])  # type: ignore[arg-type]
        tax_wf = TaxWorkflowOrchestrator()
        tax_run = await tax_wf.initiate_workflow(
            session,
            firm_id=run.firm_id,
            client_id=client_id,
            period_id=period_id,
            engagement_id=tax_eng_id,
            principal=principal,
            source_origin="approved_accounting",
            accounting_version=pub_out.version,
        )
        state["taxation_workflow_id"] = str(tax_run.id)

        if tax_run.status == "paused_approval":
            run.status = "paused_taxation_approval"
            run.current_module = "taxation_gate"
            run.checkpoint_id = f"complete_tax_gate_{run.id}"
            flag_modified(run, "state_data")
            await session.commit()
            await self._emit_status(run)
            return

        await self._continue_after_taxation(session, run, principal)

    async def _continue_after_taxation(
        self,
        session: AsyncSession,
        run: MultiModuleWorkflowRun,
        principal: Principal,
    ) -> None:
        """Executes Cross-Module Validation and builds Consolidated Report."""
        state: CompleteCAWorkflowState = run.state_data  # type: ignore[assignment]
        client_id = uuid.UUID(state["client_id"])
        period_id = uuid.UUID(state["period_id"])
        tax_eng_id = uuid.UUID(state["tax_engagement_id"])  # type: ignore[arg-type]

        # 1. Cross-Module Validation
        # Tie P&L net profit from accounting output with PBT in tax computation
        acct_out = await get_latest_approved_accounting_output(
            session, principal, client_id=client_id, period_id=period_id
        )
        tax_draft_res = await session.scalars(
            select(TaxReturnDraft)
            .where(TaxReturnDraft.engagement_id == tax_eng_id)
            .order_by(desc(TaxReturnDraft.version))
        )
        tax_draft = tax_draft_res.first()

        acct_profit = float(acct_out.summary.get("net_profit", 0.0)) if acct_out else 0.0
        tax_pbt = float(tax_draft.return_fields.get("7005", 0.0)) if tax_draft else 0.0
        variance = round(acct_profit - tax_pbt, 2)
        is_tied = abs(variance) <= 1.0

        cross_val = {
            "accounting_net_profit": acct_profit,
            "taxation_pbt": tax_pbt,
            "difference": variance,
            "statements_tied_to_tax": is_tied,
            "accounting_version": acct_out.version if acct_out else None,
            "validation_timestamp": datetime.now(UTC).isoformat(),
        }
        state["cross_module_validation"] = cross_val

        # 2. Consolidated Multi-Module Deliverable
        client = await session.get(Client, client_id)
        period = await session.get(AccountingPeriod, period_id)
        consolidated = {
            "client_name": client.name if client else "",
            "period_label": period.label if period else "",
            "accounting_summary": acct_out.summary if acct_out else {},
            "taxation_summary": {
                "taxable_income": tax_draft.return_fields.get("7008", 0.0) if tax_draft else 0.0,
                "gross_tax_liability": tax_draft.return_fields.get("7013", 0.0) if tax_draft else 0.0,
                "net_tax_payable": tax_draft.return_fields.get("7017", 0.0) if tax_draft else 0.0,
            },
            "cross_module_status": "verified" if is_tied else "variance_flagged",
            "ready_for_final_signoff": is_tied,
        }
        state["consolidated_report"] = consolidated
        state["taxation_approved"] = True

        # Pause at Final CA Review Gate
        run.status = "paused_final_signoff"
        run.current_module = "final_ca_review"
        run.checkpoint_id = f"complete_final_signoff_{run.id}"
        flag_modified(run, "state_data")
        await session.commit()
        await self._emit_status(run)

    async def _emit_status(self, run: MultiModuleWorkflowRun) -> None:
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
                    "workflow_type": "complete_ca",
                    "workflow_id": str(run.id),
                    "status": run.status,
                    "current_module": run.current_module,
                },
            )
            await pub.publish(WORKFLOW_STATUS, str(run.id), envelope)
        except Exception:
            logger.warning("failed to emit complete-ca workflow status")
