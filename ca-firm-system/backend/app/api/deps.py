"""FastAPI dependencies: database session, authenticated Principal, permission gates."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.db.session import get_session
from app.services import auth as auth_service
from app.services.authz import Principal, require_permission

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
_bearer = HTTPBearer(auto_error=False, description="Short-lived access token from /auth/login")


async def get_principal(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None:
        raise AuthenticationError("Not authenticated")
    claims = decode_access_token(settings, credentials.credentials)
    return await auth_service.load_principal(session, claims)


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def requires(permission: str) -> Callable[[Principal], Coroutine[Any, Any, Principal]]:
    """Dependency factory: route-level permission gate (services re-check; defence in depth)."""

    async def _dep(principal: PrincipalDep) -> Principal:
        require_permission(principal, permission)
        return principal

    return _dep


def enforce_trusted_origin(request: Request, settings: SettingsDep) -> None:
    """CSRF defence for cookie-authenticated endpoints (refresh/logout), on top of
    SameSite=Strict: if the browser sent an Origin header it must be an allowed origin."""
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.cors_allowed_origins:
        raise PermissionDeniedError("Untrusted origin")
