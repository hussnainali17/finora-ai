"""Pydantic schemas for the CA Review & AI Interaction Module."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


class ConversationCreate(BaseModel):
    title: str = Field(default="CA Review Session", max_length=200)


class ProposalReviewRequest(BaseModel):
    decision: str = Field(..., description="'approve' or 'reject'")
    notes: str | None = Field(default=None, max_length=2000)


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_type: str
    sender_id: uuid.UUID | None = None
    content: str
    intent: str | None = None
    target_agent: str | None = None
    proposal_id: uuid.UUID | None = None
    message_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class ProposalOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    target_agent: str
    target_entity_type: str
    target_entity_id: str
    title: str
    description: str
    original_data: dict[str, Any] = Field(default_factory=dict)
    proposed_data: dict[str, Any] = Field(default_factory=dict)
    status: str
    reexecution_plan: list[str] = Field(default_factory=list)
    reexecution_result: dict[str, Any] = Field(default_factory=dict)
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    reviewer_notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: uuid.UUID
    firm_id: uuid.UUID
    client_id: uuid.UUID
    period_id: uuid.UUID
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut] = Field(default_factory=list)
    proposals: list[ProposalOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ConversationSummaryOut(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}
