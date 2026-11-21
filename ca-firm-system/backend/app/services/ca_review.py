"""Service layer for the CA Review & AI Interaction Module.

Coordinates conversation persistence, LangGraph graph execution, message history,
proposal tracking, and agent re-execution workflows.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ca_review import (
    CACorrectionProposal,
    CAConversation,
    CAMessage,
)
from app.workflows.ca_review.graph import create_ca_review_workflow
from app.workflows.ca_review.reexecution_engine import (
    apply_correction_and_reexecute,
    reject_correction_proposal,
)

logger = logging.getLogger("app.services.ca_review")


async def list_conversations(
    session: AsyncSession,
    *,
    firm_id: uuid.UUID,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
) -> list[CAConversation]:
    """Lists conversations for this client/period ordered by most recent."""
    stmt = (
        select(CAConversation)
        .where(
            CAConversation.firm_id == firm_id,
            CAConversation.client_id == client_id,
            CAConversation.period_id == period_id,
        )
        .order_by(CAConversation.updated_at.desc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_or_create_default_conversation(
    session: AsyncSession,
    *,
    firm_id: uuid.UUID,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> CAConversation:
    """Gets the active conversation or creates a default one if none exists."""
    convs = await list_conversations(session, firm_id=firm_id, client_id=client_id, period_id=period_id)
    if convs:
        return await get_conversation_with_messages(session, firm_id=firm_id, conversation_id=convs[0].id)

    return await create_conversation(
        session,
        firm_id=firm_id,
        client_id=client_id,
        period_id=period_id,
        user_id=user_id,
        title="CA Review & AI Interaction Session",
    )


async def create_conversation(
    session: AsyncSession,
    *,
    firm_id: uuid.UUID,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    user_id: uuid.UUID | None,
    title: str = "New Review Session",
) -> CAConversation:
    """Creates a new conversation session and adds a welcoming system message."""
    conv = CAConversation(
        firm_id=firm_id,
        client_id=client_id,
        period_id=period_id,
        title=title,
        status="active",
        created_by=user_id,
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)

    welcome_msg = CAMessage(
        conversation_id=conv.id,
        firm_id=firm_id,
        sender_type="assistant",
        sender_id=None,
        content=(
            "### 👋 Welcome to the CA Review Assistant\n\n"
            "I am connected to all 4 pipeline agents for this company:\n"
            "- **Agent 1 (Intake & OCR):** Document Extraction & Data Quality Gate\n"
            "- **Agent 2 (Accounting Review):** Reconciliation, Schedules & Anomaly Detection\n"
            "- **Agent 3 (Period Adjustments):** Accruals, Prepayments & Depreciation\n"
            "- **Agent 4 (Financial Reporting):** Trial Balance & Statement Validation\n\n"
            "How can I assist you today? You can:\n"
            "- 💬 Ask questions about any numbers, balances, or agent decisions\n"
            "- ⚠️ Identify mistakes (*\"The sales figure is incorrect. Invoice shows Rs. 450,000 instead of Rs. 500,000. Correct it.\"*)\n"
            "- 🔍 Give new instructions (*\"Recheck all transactions above Rs. 100,000 without invoices\"*)"
        ),
        intent="general",
        target_agent="general",
        message_metadata={"is_welcome": True},
    )
    session.add(welcome_msg)
    await session.commit()

    return await get_conversation_with_messages(session, firm_id=firm_id, conversation_id=conv.id)


async def get_conversation_with_messages(
    session: AsyncSession,
    *,
    firm_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> CAConversation:
    """Retrieves conversation with ordered messages and proposals."""
    stmt = (
        select(CAConversation)
        .where(
            CAConversation.id == conversation_id,
            CAConversation.firm_id == firm_id,
        )
        .options(
            selectinload(CAConversation.messages),
            selectinload(CAConversation.proposals),
        )
    )
    res = await session.execute(stmt)
    conv = res.scalar_one_or_none()
    if not conv:
        raise ValueError("Conversation not found")
    return conv


async def post_message_and_execute_turn(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    firm_id: uuid.UUID,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    user_id: uuid.UUID | None,
    content: str,
    llm_gateway: Any = None,
) -> tuple[CAMessage, CACorrectionProposal | None]:
    """Posts a user message, runs the LangGraph workflow, persists outputs and returns assistant message."""
    conv = await session.get(CAConversation, conversation_id)
    if not conv:
        raise ValueError("Conversation not found")

    # 1. Record User Message
    user_msg = CAMessage(
        conversation_id=conversation_id,
        firm_id=firm_id,
        sender_type="user",
        sender_id=user_id,
        content=content,
    )
    session.add(user_msg)
    await session.commit()
    await session.refresh(user_msg)

    # 2. Load History for Context
    history_res = await session.execute(
        select(CAMessage)
        .where(CAMessage.conversation_id == conversation_id)
        .order_by(CAMessage.created_at.asc())
    )
    history_items = [
        {"role": m.sender_type, "content": m.content, "intent": m.intent}
        for m in history_res.scalars().all()
    ]

    # 3. Initialize LangGraph State
    initial_state = {
        "conversation_id": str(conversation_id),
        "firm_id": str(firm_id),
        "client_id": str(client_id),
        "period_id": str(period_id),
        "user_id": str(user_id) if user_id else None,
        "user_message": content,
        "history": history_items,
        "intent": "general",
        "target_agent": "general",
        "intent_confidence": 0.0,
        "parsed_entities": {},
        "context_data": {},
        "assistant_reply": "",
        "proposal": None,
        "instruction_result": None,
        "reexecution_result": None,
        "status": "completed",
        "error": None,
    }

    # 4. Compile and Run LangGraph Workflow
    workflow = create_ca_review_workflow(session, llm_gateway=llm_gateway)
    thread_config = {"configurable": {"thread_id": str(conversation_id)}}

    final_state = await workflow.ainvoke(initial_state, config=thread_config)

    # 5. Handle Proposal if generated
    saved_proposal: CACorrectionProposal | None = None
    proposal_dict = final_state.get("proposal")
    if proposal_dict:
        saved_proposal = CACorrectionProposal(
            conversation_id=conversation_id,
            firm_id=firm_id,
            client_id=client_id,
            period_id=period_id,
            target_agent=proposal_dict.get("target_agent", "accounting_review"),
            target_entity_type=proposal_dict.get("target_entity_type", "extracted_row"),
            target_entity_id=str(proposal_dict.get("target_entity_id", "0")),
            title=proposal_dict.get("title", "Correction Proposal"),
            description=proposal_dict.get("description", ""),
            original_data=proposal_dict.get("original_data", {}),
            proposed_data=proposal_dict.get("proposed_data", {}),
            status="pending",
            reexecution_plan=proposal_dict.get("reexecution_plan", []),
            reexecution_result={},
        )
        session.add(saved_proposal)
        await session.commit()
        await session.refresh(saved_proposal)

    # 6. Save Assistant Response Message
    metadata: dict[str, Any] = {
        "intent": final_state.get("intent"),
        "confidence": final_state.get("intent_confidence"),
        "parsed_entities": final_state.get("parsed_entities"),
    }
    if final_state.get("instruction_result"):
        metadata["instruction_result"] = final_state["instruction_result"]
    if saved_proposal:
        metadata["proposal_id"] = str(saved_proposal.id)
        metadata["proposal"] = {
            "id": str(saved_proposal.id),
            "title": saved_proposal.title,
            "status": saved_proposal.status,
            "original_data": saved_proposal.original_data,
            "proposed_data": saved_proposal.proposed_data,
            "reexecution_plan": saved_proposal.reexecution_plan,
        }

    assistant_msg = CAMessage(
        conversation_id=conversation_id,
        firm_id=firm_id,
        sender_type="assistant",
        sender_id=None,
        content=final_state.get("assistant_reply") or "I have processed your request.",
        intent=final_state.get("intent"),
        target_agent=final_state.get("target_agent"),
        proposal_id=saved_proposal.id if saved_proposal else None,
        message_metadata=metadata,
    )
    session.add(assistant_msg)
    await session.commit()
    await session.refresh(assistant_msg)

    return assistant_msg, saved_proposal


async def list_proposals(
    session: AsyncSession,
    *,
    firm_id: uuid.UUID,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    status: str | None = None,
) -> list[CACorrectionProposal]:
    """Lists correction proposals, optionally filtered by status."""
    stmt = select(CACorrectionProposal).where(
        CACorrectionProposal.firm_id == firm_id,
        CACorrectionProposal.client_id == client_id,
        CACorrectionProposal.period_id == period_id,
    )
    if status:
        stmt = stmt.where(CACorrectionProposal.status == status)
    stmt = stmt.order_by(CACorrectionProposal.created_at.desc())
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def review_proposal_decision(
    session: AsyncSession,
    *,
    proposal_id: uuid.UUID,
    user_id: uuid.UUID | None,
    decision: str,  # 'approve' or 'reject'
    reviewer_notes: str | None = None,
    llm_gateway: Any = None,
) -> tuple[CACorrectionProposal, CAMessage]:
    """Approves (and re-executes) or rejects a correction proposal, posting an update message in chat."""
    proposal = await session.get(CACorrectionProposal, proposal_id)
    if not proposal:
        raise ValueError(f"Proposal {proposal_id} not found")

    firm_id = proposal.firm_id
    conversation_id = proposal.conversation_id

    if decision.lower() in ("approve", "approved"):
        # Apply change and re-execute pipeline
        reexecution_result = await apply_correction_and_reexecute(
            session,
            proposal_id=proposal_id,
            user_id=user_id,
            reviewer_notes=reviewer_notes,
            llm_gateway=llm_gateway,
        )
        await session.refresh(proposal)

        val = reexecution_result.get("validations", {})
        val_status = reexecution_result.get("validation_status", "passed")
        executed = reexecution_result.get("executed_agents", [])

        exec_names = ", ".join(
            {"accounting_review": "Agent 2 (Accounting Review)", "adjustments": "Agent 3 (Adjustments)", "reporting": "Agent 4 (Reporting)"}.get(a, a)
            for a in executed
        )

        update_content = (
            f"### ✅ Correction Approved & Pipeline Re-executed\n\n"
            f"**Proposal:** {proposal.title}\n"
            f"- **Status:** Approved & Applied to project data\n"
            f"- **Re-executed Agents:** `{exec_names}`\n"
            f"- **Validation Gate Status:** `{val_status.upper()}`\n\n"
            f"**Updated Outputs:**\n"
            f"- Source transaction successfully updated.\n"
            f"- Dependent reconciliations and financial statements have been regenerated.\n"
            f"- Action logged in immutable system Audit Log with user identity."
        )

        msg = CAMessage(
            conversation_id=conversation_id,
            firm_id=firm_id,
            sender_type="assistant",
            content=update_content,
            intent="approval_action",
            target_agent="general",
            proposal_id=proposal_id,
            message_metadata={
                "action": "proposal_approved",
                "proposal_id": str(proposal_id),
                "reexecution_result": reexecution_result,
            },
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return proposal, msg

    else:
        # Rejection
        await reject_correction_proposal(
            session,
            proposal_id=proposal_id,
            user_id=user_id,
            reviewer_notes=reviewer_notes,
        )
        await session.refresh(proposal)

        msg = CAMessage(
            conversation_id=conversation_id,
            firm_id=firm_id,
            sender_type="assistant",
            content=(
                f"### ❌ Correction Proposal Rejected\n\n"
                f"**Proposal:** {proposal.title}\n"
                f"- **Decision:** Rejected by CA reviewer\n"
                f"- **Notes:** {reviewer_notes or 'No rejection reason specified'}\n"
                f"- Original data and existing agent outputs remain intact."
            ),
            intent="approval_action",
            target_agent="general",
            proposal_id=proposal_id,
            message_metadata={"action": "proposal_rejected", "proposal_id": str(proposal_id)},
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return proposal, msg
