# ruff: noqa: E501
"""Firm model configuration: which approved models are enabled, per-agent defaults/fallbacks, per-task
overrides, policy, and usage reporting. Every change is authorised, validated against the approved catalog
and model capabilities, audited, and bumps the firm's ``config_version``."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
    PermissionDeniedError,
)
from app.llm.catalog import (
    AGENTS,
    MODELS,
    TASKS,
    ModelSpec,
    TaskSpec,
    agent_unsupported_reasons,
    tasks_for,
    unsupported_reasons,
)
from app.llm.gateway import LlmGateway
from app.llm.resolver import enabled_aliases, usable
from app.models import (
    LlmAgentConfig,
    LlmCallLog,
    LlmFirmPolicy,
    LlmModelSetting,
    LlmTaskOverride,
)
from app.services.audit import record_audit
from app.services.authz import Principal, require_permission


async def _policy(
    session: AsyncSession, firm_id: uuid.UUID, *, lock: bool = False
) -> LlmFirmPolicy:
    q = select(LlmFirmPolicy).where(LlmFirmPolicy.firm_id == firm_id)
    if lock:
        q = q.with_for_update()
    policy = await session.scalar(q)
    if policy is None:
        policy = LlmFirmPolicy(firm_id=firm_id, allow_task_overrides=False, config_version=1)
        session.add(policy)
        await session.flush()
    return policy


def _bump(policy: LlmFirmPolicy, principal: Principal) -> None:
    policy.config_version += 1
    policy.updated_by = principal.user_id


def _model(alias: str) -> ModelSpec:
    m = MODELS.get(alias)
    if m is None:
        raise NotFoundError(
            "Model not found"
        )  # only approved aliases exist, however they are spelled
    return m


async def _agent_cfgs(session: AsyncSession, firm_id: uuid.UUID) -> dict[str, LlmAgentConfig]:
    rows = await session.scalars(select(LlmAgentConfig).where(LlmAgentConfig.firm_id == firm_id))
    return {c.agent: c for c in rows.all()}


async def _overrides(session: AsyncSession, firm_id: uuid.UUID) -> list[LlmTaskOverride]:
    rows = await session.scalars(select(LlmTaskOverride).where(LlmTaskOverride.firm_id == firm_id))
    return list(rows.all())


# ----------------------------------------------------------------------------- models


@dataclass
class ModelView:
    spec: ModelSpec
    enabled: bool
    available: bool | None  # does the gateway currently serve this alias? None = unknown
    used_by: list[str]


async def list_models(
    session: AsyncSession, principal: Principal, gateway: LlmGateway
) -> tuple[list[ModelView], int]:
    require_permission(principal, "llm:read")
    policy = await _policy(session, principal.firm_id)
    enabled = await enabled_aliases(session, principal.firm_id)
    cfgs = await _agent_cfgs(session, principal.firm_id)
    ovs = await _overrides(session, principal.firm_id)
    served = await gateway.served_aliases()
    await session.commit()  # the policy row may have just been created
    views = []
    for spec in MODELS.values():
        used = sorted(
            {a for a, c in cfgs.items() if spec.alias in (c.default_alias, c.fallback_alias)}
            | {o.agent for o in ovs if o.alias == spec.alias}
        )
        views.append(
            ModelView(
                spec, spec.alias in enabled, None if served is None else spec.alias in served, used
            )
        )
    return views, policy.config_version


async def set_model_enabled(
    session: AsyncSession, principal: Principal, alias: str, enabled: bool
) -> int:
    require_permission(principal, "llm:manage")
    spec = _model(alias)
    policy = await _policy(session, principal.firm_id, lock=True)
    if not enabled:
        cfgs = await _agent_cfgs(session, principal.firm_id)
        ovs = await _overrides(session, principal.firm_id)
        users = sorted(
            {a for a, c in cfgs.items() if alias in (c.default_alias, c.fallback_alias)}
            | {f"{o.agent}.{o.task}" for o in ovs if o.alias == alias}
        )
        if users:
            raise ConflictError(
                f"{spec.display_name} is still used by: {', '.join(users)}. Change those first.",
                used_by=",".join(users),
            )
    row = await session.scalar(
        select(LlmModelSetting).where(
            LlmModelSetting.firm_id == principal.firm_id, LlmModelSetting.alias == alias
        )
    )
    before = bool(row and row.enabled)
    if row is None:
        row = LlmModelSetting(firm_id=principal.firm_id, alias=alias, enabled=enabled)
        session.add(row)
    row.enabled, row.updated_by = enabled, principal.user_id
    _bump(policy, principal)
    record_audit(
        session, action="llm.model_enabled" if enabled else "llm.model_disabled", actor=principal,
        target_type="llm_model", metadata={"alias": alias, "was_enabled": before, "config_version": policy.config_version},
    )  # fmt: skip
    await session.commit()
    return policy.config_version


# ----------------------------------------------------------------------------- agents


@dataclass
class TaskView:
    spec: TaskSpec
    effective_alias: str | None
    source: str | None
    override_alias: str | None
    eligible: list[str]


@dataclass
class AgentView:
    key: str
    label: str
    default_alias: str | None
    fallback_alias: str | None
    tasks: list[TaskView]
    eligible: list[str]  # enabled models capable of EVERY task of the agent


async def get_agents(
    session: AsyncSession, principal: Principal
) -> tuple[list[AgentView], bool, int]:
    require_permission(principal, "llm:read")
    policy = await _policy(session, principal.firm_id)
    enabled = await enabled_aliases(session, principal.firm_id)
    cfgs = await _agent_cfgs(session, principal.firm_id)
    ovs = {(o.agent, o.task): o for o in await _overrides(session, principal.firm_id)}
    await session.commit()
    out = []
    for key, label in AGENTS.items():
        cfg = cfgs.get(key)
        tasks = []
        for t in tasks_for(key):
            ov = ovs.get((key, t.task))
            ov_ok = bool(policy.allow_task_overrides and ov and usable(ov.alias, t, enabled))
            default_ok = bool(cfg and usable(cfg.default_alias, t, enabled))
            effective = (
                ov.alias if ov_ok and ov else (cfg.default_alias if default_ok and cfg else None)
            )
            tasks.append(
                TaskView(
                    t, effective, "task_override" if ov_ok else ("agent_default" if default_ok else None),
                    ov.alias if ov else None,
                    sorted(a for a in enabled if not unsupported_reasons(MODELS[a], t)),
                )
            )  # fmt: skip
        eligible = sorted(a for a in enabled if not agent_unsupported_reasons(MODELS[a], key))
        out.append(
            AgentView(
                key,
                label,
                cfg.default_alias if cfg else None,
                cfg.fallback_alias if cfg else None,
                tasks,
                eligible,
            )
        )
    return out, policy.allow_task_overrides, policy.config_version


def _require_usable_for_agent(spec: ModelSpec, agent: str, enabled: set[str], role: str) -> None:
    if spec.alias not in enabled:
        raise DomainValidationError(f"{spec.display_name} is not enabled for this firm ({role})")
    problems = agent_unsupported_reasons(spec, agent)
    if problems:
        detail = "; ".join(f"{t}: {', '.join(r)}" for t, r in problems.items())
        raise DomainValidationError(f"{spec.display_name} cannot be used as the {role}: {detail}")


async def set_agent_config(
    session: AsyncSession,
    principal: Principal,
    agent: str,
    default_alias: str,
    fallback_alias: str | None,
) -> int:
    require_permission(principal, "llm:manage")
    if agent not in AGENTS:
        raise NotFoundError("Agent not found")
    default = MODELS.get(default_alias)
    fallback = MODELS.get(fallback_alias) if fallback_alias else None
    if default is None or (fallback_alias and fallback is None):
        raise DomainValidationError("Only approved models can be selected")
    if fallback_alias and fallback_alias == default_alias:
        raise DomainValidationError("The fallback model must differ from the default model")
    policy = await _policy(session, principal.firm_id, lock=True)
    enabled = await enabled_aliases(session, principal.firm_id)
    _require_usable_for_agent(default, agent, enabled, "default")
    if fallback is not None:
        _require_usable_for_agent(fallback, agent, enabled, "fallback")
    cfg = (await _agent_cfgs(session, principal.firm_id)).get(agent)
    before: dict[str, Any] = (
        {"default": cfg.default_alias, "fallback": cfg.fallback_alias} if cfg else {}
    )
    if cfg is None:
        cfg = LlmAgentConfig(firm_id=principal.firm_id, agent=agent, default_alias=default_alias)
        session.add(cfg)
    cfg.default_alias, cfg.fallback_alias, cfg.updated_by = (
        default_alias,
        fallback_alias,
        principal.user_id,
    )
    _bump(policy, principal)
    record_audit(
        session, action="llm.agent_config_set", actor=principal, target_type="llm_agent",
        metadata={"agent": agent, "default": default_alias, "fallback": fallback_alias, "before": before, "config_version": policy.config_version},
    )  # fmt: skip
    await session.commit()
    return policy.config_version


# ----------------------------------------------------------------------------- task overrides


async def set_task_override(
    session: AsyncSession, principal: Principal, agent: str, task: str, alias: str
) -> int:
    require_permission(principal, "llm:select")
    spec_task = TASKS.get(f"{agent}.{task}")
    if spec_task is None:
        raise NotFoundError("Task not found")
    model = MODELS.get(alias)
    if model is None:
        raise DomainValidationError("Only approved models can be selected")
    policy = await _policy(session, principal.firm_id, lock=True)
    if not policy.allow_task_overrides:
        raise PermissionDeniedError("Your firm's policy does not allow choosing a model per task")
    enabled = await enabled_aliases(session, principal.firm_id)
    if alias not in enabled:
        raise DomainValidationError(f"{model.display_name} is not enabled for this firm")
    if problems := unsupported_reasons(model, spec_task):
        raise DomainValidationError(
            f"{model.display_name} cannot run this task: {', '.join(problems)}"
        )
    ov = await session.scalar(
        select(LlmTaskOverride).where(
            LlmTaskOverride.firm_id == principal.firm_id,
            LlmTaskOverride.agent == agent,
            LlmTaskOverride.task == task,
        )
    )
    before = ov.alias if ov else None
    if ov is None:
        ov = LlmTaskOverride(firm_id=principal.firm_id, agent=agent, task=task, alias=alias)
        session.add(ov)
    ov.alias, ov.set_by = alias, principal.user_id
    _bump(policy, principal)
    record_audit(
        session, action="llm.task_override_set", actor=principal, target_type="llm_task",
        metadata={"agent": agent, "task": task, "alias": alias, "before": before, "config_version": policy.config_version},
    )  # fmt: skip
    await session.commit()
    return policy.config_version


async def clear_task_override(
    session: AsyncSession, principal: Principal, agent: str, task: str
) -> int:
    require_permission(principal, "llm:select")
    if f"{agent}.{task}" not in TASKS:
        raise NotFoundError("Task not found")
    policy = await _policy(session, principal.firm_id, lock=True)
    ov = await session.scalar(
        select(LlmTaskOverride).where(
            LlmTaskOverride.firm_id == principal.firm_id,
            LlmTaskOverride.agent == agent,
            LlmTaskOverride.task == task,
        )
    )
    if ov is not None:
        await session.delete(ov)
        _bump(policy, principal)
        record_audit(
            session, action="llm.task_override_cleared", actor=principal, target_type="llm_task",
            metadata={"agent": agent, "task": task, "alias": ov.alias, "config_version": policy.config_version},
        )  # fmt: skip
    await session.commit()
    return policy.config_version


# ----------------------------------------------------------------------------- policy


async def set_policy(
    session: AsyncSession, principal: Principal, allow_task_overrides: bool
) -> int:
    require_permission(principal, "llm:manage")
    policy = await _policy(session, principal.firm_id, lock=True)
    before = policy.allow_task_overrides
    policy.allow_task_overrides = allow_task_overrides
    _bump(policy, principal)
    record_audit(
        session, action="llm.policy_set", actor=principal, target_type="llm_policy",
        metadata={"allow_task_overrides": allow_task_overrides, "was": before, "config_version": policy.config_version},
    )  # fmt: skip
    await session.commit()
    return policy.config_version


# ----------------------------------------------------------------------------- usage


async def list_usage(
    session: AsyncSession, principal: Principal, *, limit: int, offset: int, agent: str | None
) -> tuple[list[LlmCallLog], int]:
    require_permission(principal, "llm:manage")
    cond = [LlmCallLog.firm_id == principal.firm_id]
    if agent:
        cond.append(LlmCallLog.agent == agent)
    total = await session.scalar(select(func.count()).select_from(LlmCallLog).where(*cond))
    rows = await session.scalars(
        select(LlmCallLog).where(*cond).order_by(LlmCallLog.id.desc()).limit(limit).offset(offset)
    )
    return list(rows.all()), total or 0


async def usage_summary(session: AsyncSession, principal: Principal) -> list[dict[str, Any]]:
    require_permission(principal, "llm:manage")
    q = (
        select(
            LlmCallLog.alias,
            LlmCallLog.agent,
            func.count().label("calls"),
            func.count().filter(LlmCallLog.status == "error").label("errors"),
            func.count().filter(LlmCallLog.fallback_used.is_(True)).label("fallbacks"),
            func.coalesce(func.sum(LlmCallLog.total_tokens), 0).label("tokens"),
            func.sum(LlmCallLog.cost_usd).label("cost_usd"),
            func.avg(LlmCallLog.latency_ms).label("avg_latency_ms"),
        )
        .where(LlmCallLog.firm_id == principal.firm_id)
        .group_by(LlmCallLog.alias, LlmCallLog.agent)
        .order_by(LlmCallLog.alias, LlmCallLog.agent)
    )
    return [dict(r._mapping) for r in await session.execute(q)]
