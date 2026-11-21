"""Agent re-execution engine for approved CA corrections.

Updates the target data, re-executes only the affected agents in dependency order,
validates updated outputs, and records an immutable audit trail.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.validation import (
    validate_balance_sheet,
    validate_financial_statements,
    validate_trial_balance,
)
from app.agents.accounting_review_agent.agent import AccountingReviewAgent
from app.agents.adjustments_agent.agent import AdjustmentsAgent
from app.agents.reporting_agent.agent import ReportingAgent
from app.models import AuditEvent, ExtractedRow
from app.models.accounting_review import ReviewRun
from app.models.adjustments import PeriodAdjustment
from app.models.ca_review import CACorrectionProposal

logger = logging.getLogger("app.workflows.ca_review.reexecution")


async def apply_correction_and_reexecute(
    session: AsyncSession,
    *,
    proposal_id: uuid.UUID,
    user_id: uuid.UUID | None,
    reviewer_notes: str | None = None,
    llm_gateway: Any = None,
) -> dict[str, Any]:
    """Applies an approved correction and re-executes dependent agents."""
    proposal = await session.get(CACorrectionProposal, proposal_id)
    if not proposal:
        raise ValueError(f"Correction proposal {proposal_id} not found")
    if proposal.status != "pending":
        raise ValueError(f"Proposal cannot be approved from status '{proposal.status}'")

    firm_id = proposal.firm_id
    client_id = proposal.client_id
    period_id = proposal.period_id
    target_type = proposal.target_entity_type
    target_id = proposal.target_entity_id
    proposed_data = proposal.proposed_data or {}

    logger.info(
        "Applying approved correction and re-executing agents",
        extra={
            "proposal_id": str(proposal_id),
            "target_type": target_type,
            "target_id": target_id,
        },
    )

    # 1. Update the target entity data
    target_applied = False
    if target_type == "extracted_row":
        try:
            row_pk = int(target_id)
            row = await session.get(ExtractedRow, row_pk)
            if row:
                # Update normalized data with corrected amount
                norm = dict(row.normalized or {})
                new_amt = proposed_data.get("corrected_amount")
                if new_amt is not None:
                    # Update whatever field holds the amount
                    for k in ["amount", "gross_amount", "net_amount", "total", "credit", "debit"]:
                        if k in norm:
                            norm[k] = new_amt
                    norm["corrected_amount"] = new_amt
                    norm["ca_verified"] = True
                    norm["correction_proposal_id"] = str(proposal_id)
                    row.normalized = norm
                    # Flag the row as CA-corrected
                    flags = list(row.flags or [])
                    flags.append({
                        "type": "ca_correction",
                        "corrected_at": datetime.now(timezone.utc).isoformat(),
                        "previous_value": proposed_data.get("original_amount"),
                        "new_value": new_amt,
                    })
                    row.flags = flags
                    target_applied = True
        except Exception as exc:
            logger.warning("Error updating extracted row %s: %s", target_id, exc)

    elif target_type == "period_adjustment":
        try:
            adj = await session.get(PeriodAdjustment, uuid.UUID(target_id))
            if adj:
                new_amt = proposed_data.get("corrected_amount")
                if new_amt:
                    adj.amount = Decimal(str(new_amt))
                adj.reviewer_comments = reviewer_notes or "Updated per CA Review"
                target_applied = True
        except Exception as exc:
            logger.warning("Error updating adjustment %s: %s", target_id, exc)

    # 2. Record approval on proposal
    proposal.status = "approved"
    proposal.reviewed_by = user_id
    proposal.reviewed_at = datetime.now(timezone.utc)
    proposal.reviewer_notes = reviewer_notes

    await session.commit()

    # 3. Re-execute only the affected agents
    reexecution_plan = proposal.reexecution_plan or ["accounting_review", "adjustments", "reporting"]
    reexecution_results: dict[str, Any] = {
        "executed_agents": [],
        "agent_outputs": {},
        "validations": {},
        "reexecution_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        # Re-execute Agent 2 if in plan
        if "accounting_review" in reexecution_plan:
            logger.info("Re-executing Agent 2 (Accounting Review)")
            new_run = ReviewRun(
                firm_id=firm_id,
                client_id=client_id,
                period_id=period_id,
                status="running",
                trigger="manual",
                triggered_by=user_id,
            )
            session.add(new_run)
            await session.commit()
            await session.refresh(new_run)

            rev_agent = AccountingReviewAgent()
            rev_summary = await rev_agent.run_review(
                session,
                review_run_id=new_run.id,
                client_id=client_id,
                period_id=period_id,
                firm_id=firm_id,
                llm_gateway=llm_gateway,
            )
            reexecution_results["executed_agents"].append("accounting_review")
            reexecution_results["agent_outputs"]["accounting_review"] = {
                "review_run_id": str(new_run.id),
                "summary": rev_summary,
            }

        # Re-execute Agent 3 if in plan
        if "adjustments" in reexecution_plan:
            logger.info("Re-executing Agent 3 (Period Adjustments)")
            adj_agent = AdjustmentsAgent()
            adjs = await adj_agent.generate_adjustments_for_period(
                session,
                client_id=client_id,
                period_id=period_id,
                firm_id=firm_id,
                llm_gateway=llm_gateway,
            )
            reexecution_results["executed_agents"].append("adjustments")
            reexecution_results["agent_outputs"]["adjustments"] = {
                "adjustments_count": len(adjs),
            }

        # Re-execute Agent 4 if in plan
        if "reporting" in reexecution_plan:
            logger.info("Re-executing Agent 4 (Financial Reporting & Validation)")
            rep_agent = ReportingAgent()
            rep_pack = await rep_agent.generate_reporting_pack(
                session,
                client_id=client_id,
                period_id=period_id,
                firm_id=firm_id,
            )
            reexecution_results["executed_agents"].append("reporting")
            reexecution_results["agent_outputs"]["reporting"] = {
                "validation": rep_pack.get("validation", {}),
                "statements_generated": list(rep_pack.get("statements", {}).keys()),
            }
            reexecution_results["validations"] = rep_pack.get("validation", {})

        # Validation checks
        validation_status = "passed"
        validation_errors = []
        if reexecution_results.get("validations"):
            val = reexecution_results["validations"]
            if not val.get("is_valid", True):
                validation_status = "warning"
                validation_errors = val.get("issues", [])

        reexecution_results["status"] = "success"
        reexecution_results["validation_status"] = validation_status

        # 4. Mark proposal applied
        proposal.status = "applied"
        proposal.reexecution_result = reexecution_results

        # 5. Insert immutable AuditEvent
        audit_event = AuditEvent(
            firm_id=firm_id,
            actor_user_id=user_id,
            action="ca_review.correction_applied",
            target_type=target_type,
            target_id=uuid.UUID(target_id) if len(target_id) == 36 else None,
            client_id=client_id,
            outcome="success",
            event_metadata={
                "proposal_id": str(proposal_id),
                "reexecution_plan": reexecution_plan,
                "executed_agents": reexecution_results["executed_agents"],
                "validation_status": validation_status,
                "notes": reviewer_notes,
            },
        )
        session.add(audit_event)
        await session.commit()

    except Exception as exc:
        logger.exception("Error during agent re-execution for proposal %s", proposal_id)
        proposal.status = "failed"
        reexecution_results["status"] = "failed"
        reexecution_results["error"] = str(exc)
        proposal.reexecution_result = reexecution_results
        await session.commit()
        raise

    return reexecution_results


async def reject_correction_proposal(
    session: AsyncSession,
    *,
    proposal_id: uuid.UUID,
    user_id: uuid.UUID | None,
    reviewer_notes: str | None = None,
) -> CACorrectionProposal:
    """Rejects a proposed correction."""
    proposal = await session.get(CACorrectionProposal, proposal_id)
    if not proposal:
        raise ValueError(f"Proposal {proposal_id} not found")
    if proposal.status != "pending":
        raise ValueError(f"Proposal cannot be rejected from status '{proposal.status}'")

    proposal.status = "rejected"
    proposal.reviewed_by = user_id
    proposal.reviewed_at = datetime.now(timezone.utc)
    proposal.reviewer_notes = reviewer_notes
    await session.commit()
    await session.refresh(proposal)
    return proposal
