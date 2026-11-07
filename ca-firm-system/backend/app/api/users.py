import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import PrincipalDep, SessionDep
from app.core.permissions import ROLES
from app.schemas.common import Page
from app.schemas.users import RoleOut, UserCreate, UserOut, UserUpdate
from app.services import users as users_service

router = APIRouter(tags=["users"])


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(_: PrincipalDep) -> list[RoleOut]:
    return [
        RoleOut(key=key, name=name, description=desc, permissions=sorted(perms))
        for key, (name, desc, perms) in ROLES.items()
    ]


@router.get("/users", response_model=Page[UserOut])
async def list_users(
    principal: PrincipalDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[UserOut]:
    rows, total = await users_service.list_users(session, principal, limit=limit, offset=offset)
    return Page(
        items=[UserOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, principal: PrincipalDep, session: SessionDep) -> UserOut:
    user = await users_service.create_user(
        session,
        principal,
        email=str(body.email),
        full_name=body.full_name,
        role_key=body.role_key,
        password=body.password,
    )
    return UserOut.model_validate(user)


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: uuid.UUID, principal: PrincipalDep, session: SessionDep) -> UserOut:
    return UserOut.model_validate(await users_service.get_user(session, principal, user_id))


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, principal: PrincipalDep, session: SessionDep
) -> UserOut:
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    user = await users_service.update_user(session, principal, user_id, changes=changes)
    return UserOut.model_validate(user)
