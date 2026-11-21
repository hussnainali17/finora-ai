"""CA Review & AI Interaction Module API routes.

Mounted under /clients/{client_id}/periods/{period_id}/ca-review.
Enforces:
- `ca_review:read` or `workflow:read` for viewing conversations, messages, proposals
- `ca_review:write` or `workflow:execute` for sending messages and agent instructions
- `ca_review:approve` or `workflow:execute` for approving proposals and triggering re-execution
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, PrincipalDep, SessionDep
from app.api.llm import get_gateway
from app.core.errors import PermissionDeniedError
from app.llm.gateway import LlmGateway
from app.schemas.ca_review import (
    ConversationCreate,
    ConversationOut,
    ConversationSummaryOut,
    MessageCreate,
    MessageOut,
    ProposalOut,
    ProposalReviewRequest,
)
from app.services import ca_review as review_service
from app.services.authz import get_accessible_client
from app.workflows.ca_review.context import retrieve_ca_context

logger = logging.getLogger("app.api.ca_review")

router = APIRouter(
    prefix="/clients/{client_id}/periods/{period_id}/ca-review",
    tags=["ca_review"],
)


def _check_perm(principal: Principal, primary: str, fallback: str) -> None:
    if primary not in principal.permissions and fallback not in principal.permissions:
        raise PermissionDeniedError(f"Missing permission: {primary} or {fallback}")


@router.get(
    "/conversations",
    response_model=list[ConversationSummaryOut],
    summary="List CA Review conversations for client period",
)
async def list_conversations(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep,
) -> list[ConversationSummaryOut]:
    _check_perm(principal, "ca_review:read", "workflow:read")
    await get_accessible_client(session, principal, client_id)
    convs = await review_service.list_conversations(
        session,
        firm_id=principal.firm_id,
        client_id=client_id,
        period_id=period_id,
    )
    return [
        ConversationSummaryOut(
            id=c.id,
            title=c.title,
            status=c.status,
            created_at=c.created_at,
            updated_at=c.updated_at,
            message_count=0,
        )
        for c in convs
    ]


@router.post(
    "/conversations",
    response_model=ConversationOut,
    status_code=201,
    summary="Create a new CA Review conversation",
)
async def create_conversation(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    payload: ConversationCreate,
    session: SessionDep,
    principal: PrincipalDep,
) -> ConversationOut:
    _check_perm(principal, "ca_review:write", "workflow:execute")
    await get_accessible_client(session, principal, client_id)
    conv = await review_service.create_conversation(
        session,
        firm_id=principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        user_id=principal.user_id,
        title=payload.title,
    )
    return ConversationOut.model_validate(conv)


@router.get(
    "/conversations/active",
    response_model=ConversationOut,
    summary="Get or initialize active conversation session",
)
async def get_active_conversation(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep,
) -> ConversationOut:
    _check_perm(principal, "ca_review:read", "workflow:read")
    await get_accessible_client(session, principal, client_id)
    conv = await review_service.get_or_create_default_conversation(
        session,
        firm_id=principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        user_id=principal.user_id,
    )
    return ConversationOut.model_validate(conv)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationOut,
    summary="Get conversation with message history and proposals",
)
async def get_conversation(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    conversation_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep,
) -> ConversationOut:
    _check_perm(principal, "ca_review:read", "workflow:read")
    await get_accessible_client(session, principal, client_id)
    conv = await review_service.get_conversation_with_messages(
        session,
        firm_id=principal.firm_id,
        conversation_id=conversation_id,
    )
    return ConversationOut.model_validate(conv)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=201,
    summary="Send message in CA Review conversation (executes LangGraph workflow)",
)
async def post_message(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    session: SessionDep,
    principal: PrincipalDep,
    llm_gateway: LlmGateway = Depends(get_gateway),
) -> MessageOut:
    _check_perm(principal, "ca_review:write", "workflow:execute")
    await get_accessible_client(session, principal, client_id)
    assistant_msg, _ = await review_service.post_message_and_execute_turn(
        session,
        conversation_id=conversation_id,
        firm_id=principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        user_id=principal.user_id,
        content=payload.content,
        llm_gateway=llm_gateway,
    )
    return MessageOut.model_validate(assistant_msg)


@router.get(
    "/proposals",
    response_model=list[ProposalOut],
    summary="List correction proposals for this client period",
)
async def list_proposals(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep,
    status: str | None = Query(default=None),
) -> list[ProposalOut]:
    _check_perm(principal, "ca_review:read", "workflow:read")
    await get_accessible_client(session, principal, client_id)
    props = await review_service.list_proposals(
        session,
        firm_id=principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        status=status,
    )
    return [ProposalOut.model_validate(p) for p in props]


@router.post(
    "/proposals/{proposal_id}/review",
    response_model=ProposalOut,
    summary="Approve (and re-execute dependent agents) or reject correction proposal",
)
async def review_proposal(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    proposal_id: uuid.UUID,
    payload: ProposalReviewRequest,
    session: SessionDep,
    principal: PrincipalDep,
    llm_gateway: LlmGateway = Depends(get_gateway),
) -> ProposalOut:
    _check_perm(principal, "ca_review:approve", "workflow:execute")
    await get_accessible_client(session, principal, client_id)
    proposal, _ = await review_service.review_proposal_decision(
        session,
        proposal_id=proposal_id,
        user_id=principal.user_id,
        decision=payload.decision,
        reviewer_notes=payload.notes,
        llm_gateway=llm_gateway,
    )
    return ProposalOut.model_validate(proposal)


@router.get(
    "/context-snapshot",
    response_model=dict[str, Any],
    summary="Get multi-agent pipeline context snapshot for inspector drawer",
)
async def get_context_snapshot(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    session: SessionDep,
    principal: PrincipalDep,
) -> dict[str, Any]:
    _check_perm(principal, "ca_review:read", "workflow:read")
    await get_accessible_client(session, principal, client_id)
    return await retrieve_ca_context(
        session,
        firm_id=principal.firm_id,
        client_id=client_id,
        period_id=period_id,
    )
