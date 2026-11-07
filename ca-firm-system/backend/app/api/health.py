from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.integrations.health import run_dependency_checks

router = APIRouter(prefix="/health", tags=["health"])


class LiveResponse(BaseModel):
    status: Literal["ok"] = "ok"


class DependencyResult(BaseModel):
    name: str
    ok: bool
    latency_ms: float
    detail: str | None = None


class ReadyResponse(BaseModel):
    status: Literal["ok", "degraded"]
    dependencies: list[DependencyResult]


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    """Process liveness only; does not touch dependencies."""
    return LiveResponse()


@router.get("/ready", response_model=ReadyResponse)
async def ready(
    response: Response, settings: Annotated[Settings, Depends(get_settings)]
) -> ReadyResponse:
    """Readiness: checks every infrastructure dependency. Returns 503 if any is down."""
    results = await run_dependency_checks(settings)
    all_ok = all(r.ok for r in results)
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(
        status="ok" if all_ok else "degraded",
        dependencies=[
            DependencyResult(name=r.name, ok=r.ok, latency_ms=r.latency_ms, detail=r.detail)
            for r in results
        ],
    )
