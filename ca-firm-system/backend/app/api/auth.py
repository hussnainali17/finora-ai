from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from sqlalchemy import select

from app.api.deps import PrincipalDep, SessionDep, SettingsDep, enforce_trusted_origin
from app.core.config import Settings
from app.core.errors import AuthenticationError
from app.models import Firm
from app.schemas.auth import ChangePasswordRequest, CurrentUser, LoginRequest, TokenResponse
from app.services import auth as auth_service
from app.services.auth import SessionTokens

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "ca_refresh"  # HttpOnly; scoped to the /auth path


def _set_refresh_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=f"{settings.api_prefix}/auth",  # sent only to auth endpoints
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=f"{settings.api_prefix}/auth",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _token_response(tokens: SessionTokens) -> TokenResponse:
    user = tokens.user
    return TokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        user=CurrentUser(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            firm_id=user.firm_id,
            firm_name=user.firm.name,
            role=user.role_key,
            permissions=sorted(rp.permission_key for rp in user.role.permissions),
        ),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, response: Response, session: SessionDep, settings: SettingsDep
) -> TokenResponse:
    tokens = await auth_service.login(
        session, settings, email=str(body.email), password=body.password
    )
    _set_refresh_cookie(response, settings, tokens.refresh_token)
    response.headers["Cache-Control"] = "no-store"
    return _token_response(tokens)


@router.post(
    "/refresh", response_model=TokenResponse, dependencies=[Depends(enforce_trusted_origin)]
)
async def refresh(
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    request_cookie: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> TokenResponse:
    if not request_cookie:
        raise AuthenticationError("Not authenticated")
    try:
        tokens = await auth_service.refresh(session, settings, raw_token=request_cookie)
    except AuthenticationError:
        _clear_refresh_cookie(response, settings)
        raise
    _set_refresh_cookie(response, settings, tokens.refresh_token)
    response.headers["Cache-Control"] = "no-store"
    return _token_response(tokens)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_trusted_origin)],
)
async def logout(
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    request_cookie: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> None:
    await auth_service.logout(session, raw_token=request_cookie)
    _clear_refresh_cookie(response, settings)


@router.get("/me", response_model=CurrentUser)
async def me(principal: PrincipalDep, session: SessionDep) -> CurrentUser:
    firm_name = await session.scalar(select(Firm.name).where(Firm.id == principal.firm_id))
    return CurrentUser(
        id=principal.user_id,
        email=principal.email,
        full_name=principal.full_name,
        firm_id=principal.firm_id,
        firm_name=firm_name or "",
        role=principal.role_key,
        permissions=sorted(principal.permissions),
    )


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    principal: PrincipalDep,
    session: SessionDep,
    response: Response,
    settings: SettingsDep,
) -> None:
    await auth_service.change_password(
        session,
        principal,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    _clear_refresh_cookie(response, settings)
