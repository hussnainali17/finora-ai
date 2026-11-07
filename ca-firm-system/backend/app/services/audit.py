"""Audit trail writer. Events are written in the SAME transaction as the action they describe,
so an action and its audit record commit or roll back together."""

import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import client_ip_var, correlation_id_var
from app.models import AuditEvent
from app.services.authz import Principal

_SENSITIVE_KEY = re.compile(
    r"pass(word)?|token|secret|authorization|api[_-]?key|hash", re.IGNORECASE
)


def sanitize_metadata(data: dict[str, Any] | None) -> dict[str, Any]:
    """Drops sensitive keys so credentials can never be written to the audit trail."""
    clean: dict[str, Any] = {}
    for key, value in (data or {}).items():
        if _SENSITIVE_KEY.search(key):
            continue
        clean[key] = sanitize_metadata(value) if isinstance(value, dict) else _jsonable(value)
    return clean


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    return str(value)


def record_audit(
    session: AsyncSession,
    *,
    action: str,
    actor: Principal | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_email: str | None = None,
    firm_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    outcome: str = "success",
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """Adds an audit event to the session (caller commits together with the business change)."""
    event = AuditEvent(
        firm_id=actor.firm_id if actor else firm_id,
        actor_user_id=actor.user_id if actor else actor_user_id,
        actor_email=actor.email if actor else actor_email,
        action=action,
        target_type=target_type,
        target_id=target_id,
        client_id=client_id,
        outcome=outcome,
        event_metadata=sanitize_metadata(metadata),
        ip_address=client_ip_var.get(),
        request_id=correlation_id_var.get(),
    )
    session.add(event)
    return event
