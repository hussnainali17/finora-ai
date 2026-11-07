import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import PrincipalDep, SessionDep
from app.schemas.clients import (
    AccessGrant,
    AccessOut,
    ClientCreate,
    ClientOut,
    ClientUpdate,
    PeriodCreate,
    PeriodOut,
    PeriodUpdate,
)
from app.schemas.common import Page
from app.services import clients as svc

router = APIRouter(prefix="/clients", tags=["clients"])

_NULLABLE_CLIENT_FIELDS = {"legal_name", "notes"}


@router.get("", response_model=Page[ClientOut])
async def list_clients(
    principal: PrincipalDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[Literal["active", "archived"] | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[ClientOut]:
    rows, total = await svc.list_clients(
        session, principal, limit=limit, offset=offset, status=status_filter, q=q
    )
    return Page(
        items=[ClientOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
async def create_client(
    body: ClientCreate, principal: PrincipalDep, session: SessionDep
) -> ClientOut:
    client = await svc.create_client(session, principal, **body.model_dump())
    return ClientOut.model_validate(client)


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(
    client_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> ClientOut:
    return ClientOut.model_validate(await svc.get_client(session, principal, client_id))


@router.patch("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: uuid.UUID, body: ClientUpdate, principal: PrincipalDep, session: SessionDep
) -> ClientOut:
    changes = {
        k: v
        for k, v in body.model_dump(exclude_unset=True).items()
        if v is not None or k in _NULLABLE_CLIENT_FIELDS
    }
    return ClientOut.model_validate(
        await svc.update_client(session, principal, client_id, changes=changes)
    )


# ------------------------------------------------------------------------------ periods


@router.get("/{client_id}/periods", response_model=list[PeriodOut])
async def list_periods(
    client_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> list[PeriodOut]:
    return [
        PeriodOut.model_validate(p) for p in await svc.list_periods(session, principal, client_id)
    ]


@router.post("/{client_id}/periods", response_model=PeriodOut, status_code=status.HTTP_201_CREATED)
async def create_period(
    client_id: uuid.UUID, body: PeriodCreate, principal: PrincipalDep, session: SessionDep
) -> PeriodOut:
    period = await svc.create_period(session, principal, client_id, **body.model_dump())
    return PeriodOut.model_validate(period)


@router.get("/{client_id}/periods/{period_id}", response_model=PeriodOut)
async def get_period(
    client_id: uuid.UUID, period_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> PeriodOut:
    return PeriodOut.model_validate(await svc.get_period(session, principal, client_id, period_id))


@router.patch("/{client_id}/periods/{period_id}", response_model=PeriodOut)
async def update_period(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    body: PeriodUpdate,
    principal: PrincipalDep,
    session: SessionDep,
) -> PeriodOut:
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    return PeriodOut.model_validate(
        await svc.update_period(session, principal, client_id, period_id, changes=changes)
    )


@router.post("/{client_id}/periods/{period_id}/close", response_model=PeriodOut)
async def close_period(
    client_id: uuid.UUID, period_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> PeriodOut:
    return PeriodOut.model_validate(
        await svc.set_period_status(session, principal, client_id, period_id, close=True)
    )


@router.post("/{client_id}/periods/{period_id}/reopen", response_model=PeriodOut)
async def reopen_period(
    client_id: uuid.UUID, period_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> PeriodOut:
    return PeriodOut.model_validate(
        await svc.set_period_status(session, principal, client_id, period_id, close=False)
    )


# ------------------------------------------------------------------------------- access


def _access_out(access: object, user: object) -> AccessOut:
    return AccessOut(
        user_id=user.id,  # type: ignore[attr-defined]
        email=user.email,  # type: ignore[attr-defined]
        full_name=user.full_name,  # type: ignore[attr-defined]
        role_key=user.role_key,  # type: ignore[attr-defined]
        granted_at=access.created_at,  # type: ignore[attr-defined]
    )


@router.get("/{client_id}/access", response_model=list[AccessOut])
async def list_access(
    client_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> list[AccessOut]:
    return [_access_out(a, u) for a, u in await svc.list_access(session, principal, client_id)]


@router.post("/{client_id}/access", response_model=AccessOut, status_code=status.HTTP_201_CREATED)
async def grant_access(
    client_id: uuid.UUID, body: AccessGrant, principal: PrincipalDep, session: SessionDep
) -> AccessOut:
    access, user = await svc.grant_access(session, principal, client_id, body.user_id)
    return _access_out(access, user)


@router.delete("/{client_id}/access/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_access(
    client_id: uuid.UUID, user_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> Response:
    await svc.revoke_access(session, principal, client_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
