# ruff: noqa: E501
"""Decides which approved model a task uses, from the firm's stored configuration.

Order: per-task override (only if the firm policy allows overrides) > the agent's default. A model is only
usable if it is in the approved catalog, ENABLED for the firm and capable of the task. Nothing is ever
resolved from user input directly, and nothing is enabled by default."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.catalog import AGENTS, MODELS, TASKS, ModelSpec, TaskSpec, unsupported_reasons
from app.llm.errors import ModelUnavailableError
from app.models import LlmAgentConfig, LlmFirmPolicy, LlmModelSetting, LlmTaskOverride


@dataclass(frozen=True)
class Resolution:
    task: TaskSpec
    model: ModelSpec
    fallback: ModelSpec | None
    config_version: int
    source: str  # task_override | agent_default


async def enabled_aliases(session: AsyncSession, firm_id: uuid.UUID) -> set[str]:
    rows = await session.scalars(
        select(LlmModelSetting.alias).where(
            LlmModelSetting.firm_id == firm_id, LlmModelSetting.enabled.is_(True)
        )
    )
    return {a for a in rows.all() if a in MODELS}  # aliases removed from the catalog are ignored


def usable(alias: str | None, task: TaskSpec, enabled: set[str]) -> ModelSpec | None:
    if alias is None or alias not in MODELS or alias not in enabled:
        return None
    model = MODELS[alias]
    return None if unsupported_reasons(model, task) else model


async def resolve(
    session: AsyncSession, firm_id: uuid.UUID, agent: str, task_name: str
) -> Resolution:
    task = TASKS.get(f"{agent}.{task_name}")
    if agent not in AGENTS or task is None:
        raise ModelUnavailableError("This AI task is not registered")
    policy = await session.get(LlmFirmPolicy, firm_id)
    version = policy.config_version if policy else 0
    enabled = await enabled_aliases(session, firm_id)
    cfg = await session.scalar(
        select(LlmAgentConfig).where(
            LlmAgentConfig.firm_id == firm_id, LlmAgentConfig.agent == agent
        )
    )
    chosen, source = None, "agent_default"
    if policy is not None and policy.allow_task_overrides:
        ov = await session.scalar(
            select(LlmTaskOverride).where(
                LlmTaskOverride.firm_id == firm_id,
                LlmTaskOverride.agent == agent,
                LlmTaskOverride.task == task_name,
            )
        )
        if ov is not None and (m := usable(ov.alias, task, enabled)):
            chosen, source = m, "task_override"
    if chosen is None:
        chosen = usable(cfg.default_alias if cfg else None, task, enabled)
    if chosen is None:
        raise ModelUnavailableError(
            "No approved AI model is enabled for this task. A firm administrator can configure one "
            "in model settings."
        )
    fallback = usable(cfg.fallback_alias if cfg else None, task, enabled)
    if fallback is not None and fallback.alias == chosen.alias:
        fallback = None
    return Resolution(task, chosen, fallback, version, source)
