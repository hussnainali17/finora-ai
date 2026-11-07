# ruff: noqa: E501
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import PrincipalDep, SessionDep, SettingsDep
from app.core.errors import NotFoundError
from app.db.session import get_sessionmaker
from app.llm.catalog import MODELS
from app.llm.errors import LlmError
from app.llm.gateway import LlmGateway
from app.schemas.common import Page
from app.schemas.llm import (
    AgentConfigIn,
    AgentOut,
    AgentsOut,
    EnableIn,
    ModelOut,
    ModelsOut,
    ModelTestOut,
    PolicyIn,
    TaskOut,
    TaskOverrideIn,
    UsageOut,
    UsageSummaryRow,
    VersionOut,
)
from app.services import llm_config as svc
from app.services.audit import record_audit
from app.services.authz import require_permission

router = APIRouter(prefix="/llm", tags=["llm"])


def get_gateway(settings: SettingsDep) -> LlmGateway:
    return LlmGateway(get_sessionmaker(), settings)


GatewayDep = Annotated[LlmGateway, Depends(get_gateway)]


@router.get("/models", response_model=ModelsOut)
async def list_models(
    principal: PrincipalDep, session: SessionDep, gateway: GatewayDep
) -> ModelsOut:
    views, version = await svc.list_models(session, principal, gateway)
    return ModelsOut(
        models=[
            ModelOut(
                alias=v.spec.alias, display_name=v.spec.display_name, provider=v.spec.provider,
                description=v.spec.description, context_window=v.spec.context_window,
                capabilities=sorted(v.spec.capabilities), tier=v.spec.tier, enabled=v.enabled,
                available=v.available, used_by=v.used_by,
            )
            for v in views
        ],
        config_version=version,
    )  # fmt: skip


@router.put("/models/{alias}/enabled", response_model=VersionOut)
async def set_enabled(
    alias: str, body: EnableIn, principal: PrincipalDep, session: SessionDep
) -> VersionOut:
    return VersionOut(
        config_version=await svc.set_model_enabled(session, principal, alias, body.enabled)
    )


@router.post("/models/{alias}/test", response_model=ModelTestOut)
async def test_model(
    alias: str, principal: PrincipalDep, session: SessionDep, gateway: GatewayDep
) -> ModelTestOut:
    require_permission(principal, "llm:manage")
    if alias not in MODELS:
        raise NotFoundError("Model not found")
    try:
        r = await gateway.test_alias(
            firm_id=principal.firm_id, user_id=principal.user_id, alias=alias
        )
        out = ModelTestOut(
            ok=True, alias=alias, latency_ms=r.latency_ms, attempts=r.attempts, error_code=None
        )
    except LlmError as exc:
        out = ModelTestOut(
            ok=False, alias=alias, latency_ms=None, attempts=None, error_code=exc.code
        )
    record_audit(
        session, action="llm.model_tested", actor=principal, target_type="llm_model",
        outcome="success" if out.ok else "failure", metadata={"alias": alias, "error_code": out.error_code},
    )  # fmt: skip
    await session.commit()
    return out


@router.get("/agents", response_model=AgentsOut)
async def get_agents(principal: PrincipalDep, session: SessionDep) -> AgentsOut:
    agents, allow, version = await svc.get_agents(session, principal)
    return AgentsOut(
        agents=[
            AgentOut(
                key=a.key, label=a.label, default_alias=a.default_alias, fallback_alias=a.fallback_alias,
                eligible=a.eligible,
                tasks=[
                    TaskOut(
                        task=t.spec.task, description=t.spec.description, requires=sorted(t.spec.requires),
                        min_context=t.spec.min_context, effective_alias=t.effective_alias, source=t.source,
                        override_alias=t.override_alias, eligible=t.eligible,
                    )
                    for t in a.tasks
                ],
            )
            for a in agents
        ],
        allow_task_overrides=allow, config_version=version,
    )  # fmt: skip


@router.put("/agents/{agent}", response_model=VersionOut)
async def set_agent(
    agent: str, body: AgentConfigIn, principal: PrincipalDep, session: SessionDep
) -> VersionOut:
    v = await svc.set_agent_config(
        session, principal, agent, body.default_alias, body.fallback_alias
    )
    return VersionOut(config_version=v)


@router.put("/agents/{agent}/tasks/{task}", response_model=VersionOut)
async def set_task(
    agent: str, task: str, body: TaskOverrideIn, principal: PrincipalDep, session: SessionDep
) -> VersionOut:
    return VersionOut(
        config_version=await svc.set_task_override(session, principal, agent, task, body.alias)
    )


@router.delete("/agents/{agent}/tasks/{task}", response_model=VersionOut)
async def clear_task(
    agent: str, task: str, principal: PrincipalDep, session: SessionDep
) -> VersionOut:
    return VersionOut(config_version=await svc.clear_task_override(session, principal, agent, task))


@router.put("/policy", response_model=VersionOut)
async def set_policy(body: PolicyIn, principal: PrincipalDep, session: SessionDep) -> VersionOut:
    return VersionOut(
        config_version=await svc.set_policy(session, principal, body.allow_task_overrides)
    )


@router.get("/usage", response_model=Page[UsageOut])
async def usage(
    principal: PrincipalDep, session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    agent: Annotated[str | None, Query(max_length=32)] = None,
) -> Page[UsageOut]:  # fmt: skip
    rows, total = await svc.list_usage(session, principal, limit=limit, offset=offset, agent=agent)
    return Page[UsageOut](
        items=[UsageOut.model_validate(r, from_attributes=True) for r in rows],
        total=total, limit=limit, offset=offset,
    )  # fmt: skip


@router.get("/usage/summary", response_model=list[UsageSummaryRow])
async def usage_summary(principal: PrincipalDep, session: SessionDep) -> list[UsageSummaryRow]:
    return [UsageSummaryRow(**r) for r in await svc.usage_summary(session, principal)]
