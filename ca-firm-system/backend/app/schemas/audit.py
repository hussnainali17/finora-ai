import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    created_at: datetime
    action: str
    outcome: str
    actor_user_id: uuid.UUID | None
    actor_email: str | None
    target_type: str | None
    target_id: uuid.UUID | None
    client_id: uuid.UUID | None
    metadata: dict[str, Any] = Field(validation_alias="event_metadata")
    ip_address: str | None
    request_id: str | None
