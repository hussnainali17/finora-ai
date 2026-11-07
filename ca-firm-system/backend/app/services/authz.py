"""Authorization: the Principal, permission checks and CLIENT-LEVEL SCOPING.

Rules enforced here (and nowhere else - routers and services must use these helpers):
1. Every query on tenant data is filtered by ``principal.firm_id``.
2. Users with ``client:access_all`` (Firm Admin) reach every client in their firm; everyone else
   reaches only clients they are explicitly assigned to (``user_client_access``).
3. A resource outside the caller's scope is reported as *not found* (404), never as forbidden, so
   other tenants'/clients' existence is not disclosed. A missing permission on an in-scope
   resource is 403.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, PermissionDeniedError
from app.models import Client, UserClientAccess


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    firm_id: uuid.UUID
    email: str
    full_name: str
    role_key: str
    permissions: frozenset[str]
    session_id: uuid.UUID

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    @property
    def can_access_all_clients(self) -> bool:
        return "client:access_all" in self.permissions


def require_permission(principal: Principal, permission: str) -> None:
    if not principal.has(permission):
        raise PermissionDeniedError("You do not have permission to perform this action")


def assigned_client_ids(principal: Principal) -> Select[Any]:
    return select(UserClientAccess.client_id).where(
        UserClientAccess.user_id == principal.user_id,
        UserClientAccess.firm_id == principal.firm_id,
    )


def client_scope(principal: Principal) -> list[ColumnElement[bool]]:
    """WHERE clauses restricting ``Client`` rows to those the principal may access."""
    clauses: list[ColumnElement[bool]] = [Client.firm_id == principal.firm_id]
    if not principal.can_access_all_clients:
        clauses.append(Client.id.in_(assigned_client_ids(principal)))
    return clauses


async def get_accessible_client(
    session: AsyncSession, principal: Principal, client_id: uuid.UUID
) -> Client:
    """The ONLY way services load a client by id on behalf of a user."""
    client = await session.scalar(
        select(Client).where(Client.id == client_id, *client_scope(principal))
    )
    if client is None:
        raise NotFoundError("Client not found")
    return client
