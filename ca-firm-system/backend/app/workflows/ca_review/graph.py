"""LangGraph StateGraph workflow for the CA Review & AI Interaction Module.

Coordinates:
- Intent Classification Node
- Context Retrieval Node
- Dynamic routing to Question, Correction, Instruction, or Approval handlers
- Response Synthesis Node
- LangGraph checkpointing and state persistence
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.gateway import LlmGateway
from app.workflows.ca_review.context import retrieve_ca_context
from app.workflows.ca_review.correction_engine import build_correction_proposal
from app.workflows.ca_review.instruction_engine import execute_ca_instruction
from app.workflows.ca_review.intent import classify_intent
from app.workflows.ca_review.qa_engine import answer_ca_question
from app.workflows.ca_review.state import CAReviewState

logger = logging.getLogger("app.workflows.ca_review.graph")


def create_ca_review_workflow(
    session: AsyncSession,
    *,
    llm_gateway: LlmGateway | None = None,
) -> Any:
    """Builds and compiles the LangGraph StateGraph workflow."""

    async def classify_intent_node(state: CAReviewState) -> dict[str, Any]:
        """Node 1: Classify CA user intent."""
        firm_id = uuid.UUID(state["firm_id"])
        intent, agent, confidence, entities = await classify_intent(
            state["user_message"],
            firm_id=firm_id,
            history=state.get("history", []),
            llm_gateway=llm_gateway,
        )
        return {
            "intent": intent,
            "target_agent": agent,
            "intent_confidence": confidence,
            "parsed_entities": entities,
        }

    async def retrieve_context_node(state: CAReviewState) -> dict[str, Any]:
        """Node 2: Retrieve multi-agent context data."""
        firm_id = uuid.UUID(state["firm_id"])
        client_id = uuid.UUID(state["client_id"])
        period_id = uuid.UUID(state["period_id"])

        ctx = await retrieve_ca_context(
            session,
            firm_id=firm_id,
            client_id=client_id,
            period_id=period_id,
            query_text=state["user_message"],
        )
        return {"context_data": ctx}

    def route_intent(state: CAReviewState) -> str:
        """Conditional branch routing based on intent."""
        intent = state.get("intent", "general")
        if intent in ("error_report", "correction_request"):
            return "handle_correction"
        elif intent == "instruction":
            return "handle_instruction"
        elif intent == "approval_action":
            return "handle_approval"
        else:
            return "handle_question"

    async def handle_question_node(state: CAReviewState) -> dict[str, Any]:
        """Node 3A: Answer question using verified project context."""
        firm_id = uuid.UUID(state["firm_id"])
        reply = await answer_ca_question(
            state["user_message"],
            firm_id=firm_id,
            context_data=state.get("context_data", {}),
            llm_gateway=llm_gateway,
        )
        return {
            "assistant_reply": reply,
            "status": "completed",
        }

    async def handle_correction_node(state: CAReviewState) -> dict[str, Any]:
        """Node 3B: Formulate correction proposal with diff and reexecution plan."""
        proposal_dict, reply = build_correction_proposal(
            firm_id=state["firm_id"],
            client_id=state["client_id"],
            period_id=state["period_id"],
            conversation_id=state["conversation_id"],
            user_message=state["user_message"],
            parsed_entities=state.get("parsed_entities", {}),
            context_data=state.get("context_data", {}),
        )
        return {
            "proposal": proposal_dict,
            "assistant_reply": reply,
            "status": "pending_approval",
        }

    async def handle_instruction_node(state: CAReviewState) -> dict[str, Any]:
        """Node 3C: Execute agent instruction across transactions."""
        instruction_res, reply = execute_ca_instruction(
            user_message=state["user_message"],
            parsed_entities=state.get("parsed_entities", {}),
            context_data=state.get("context_data", {}),
        )
        return {
            "instruction_result": instruction_res,
            "assistant_reply": reply,
            "status": "completed",
        }

    async def handle_approval_node(state: CAReviewState) -> dict[str, Any]:
        """Node 3D: Guide user to interactive approval or note status."""
        action = state.get("parsed_entities", {}).get("approval_action", "approve")
        reply = (
            f"### ⚡ Action: {action.title()} Requested\n\n"
            f"To maintain complete audit compliance and human-in-the-loop authorization, "
            f"please click the **{action.title()}** button on the proposal card above, "
            f"or submit your decision with notes. This will record your identity in the audit trail."
        )
        return {
            "assistant_reply": reply,
            "status": "completed",
        }

    async def synthesize_node(state: CAReviewState) -> dict[str, Any]:
        """Final node: finalize state attributes."""
        return {
            "error": None,
        }

    # Construct the graph
    workflow = StateGraph(CAReviewState)

    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("retrieve_context", retrieve_context_node)
    workflow.add_node("handle_question", handle_question_node)
    workflow.add_node("handle_correction", handle_correction_node)
    workflow.add_node("handle_instruction", handle_instruction_node)
    workflow.add_node("handle_approval", handle_approval_node)
    workflow.add_node("synthesize", synthesize_node)

    workflow.add_edge(START, "classify_intent")
    workflow.add_edge("classify_intent", "retrieve_context")
    workflow.add_conditional_edges(
        "retrieve_context",
        route_intent,
        {
            "handle_question": "handle_question",
            "handle_correction": "handle_correction",
            "handle_instruction": "handle_instruction",
            "handle_approval": "handle_approval",
        },
    )

    workflow.add_edge("handle_question", "synthesize")
    workflow.add_edge("handle_correction", "synthesize")
    workflow.add_edge("handle_instruction", "synthesize")
    workflow.add_edge("handle_approval", "synthesize")
    workflow.add_edge("synthesize", END)

    memory_checkpointer = MemorySaver()
    return workflow.compile(checkpointer=memory_checkpointer)
