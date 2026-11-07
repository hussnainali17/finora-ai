"""Domain exceptions (framework-free) and their HTTP mapping."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class AuthenticationError(AppError):
    status_code = 401


class PermissionDeniedError(AppError):
    """Authenticated, but lacks the permission for this action (403)."""

    status_code = 403


class NotFoundError(AppError):
    """Also used for out-of-scope resources (tenant/client), so existence is not leaked."""

    status_code = 404


class ConflictError(AppError):
    status_code = 409


class DomainValidationError(AppError):
    status_code = 422


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle(_: Request, exc: AppError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if isinstance(exc, AuthenticationError) else None
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers)
