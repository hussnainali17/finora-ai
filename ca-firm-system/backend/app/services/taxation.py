"""Taxation Service layer.

Coordinates database operations, client authorization, and execution
of the Pakistan Tax agents and workflows.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, require_permission
from app.core.errors import NotFoundError
from app.models.taxation import (
    TaxCalculationRun,
    TaxEngagement,
    TaxpayerProfile,
    TaxReturnDraft,
    TaxWorkflowRun,
    TaxWorkpaper,
)
from app.services.clients import get_accessible_client

logger = logging.getLogger("app.services.taxation")


async def create_tax_engagement(
    session: AsyncSession,
    principal: Principal,
    *,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    tax_year: int,
    tax_period_label: str = "TY",
    tax_type: str = "composite",
    notes: str | None = None,
) -> TaxEngagement:
    """Creates a new tax engagement for a client and period."""
    require_permission(principal, "tax:manage")
    await get_accessible_client(session, principal, client_id)

    engagement = TaxEngagement(
        firm_id=principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        tax_year=tax_year,
        tax_period_label=tax_period_label,
        tax_type=tax_type,
        status="draft",
        assigned_to=principal.user_id,
        notes=notes,
    )
    session.add(engagement)
    await session.commit()
    await session.refresh(engagement)
    return engagement


async def list_tax_engagements(
    session: AsyncSession,
    principal: Principal,
    *,
    client_id: uuid.UUID,
    period_id: uuid.UUID | None = None,
) -> list[TaxEngagement]:
    """Lists tax engagements for a client."""
    require_permission(principal, "tax:read")
    await get_accessible_client(session, principal, client_id)

    query = select(TaxEngagement).where(
        TaxEngagement.firm_id == principal.firm_id,
        TaxEngagement.client_id == client_id,
    )
    if period_id is not None:
        query = query.where(TaxEngagement.period_id == period_id)

    query = query.order_by(desc(TaxEngagement.tax_year), desc(TaxEngagement.created_at))
    res = await session.scalars(query)
    return list(res.all())


async def get_tax_engagement(
    session: AsyncSession,
    principal: Principal,
    engagement_id: uuid.UUID,
) -> TaxEngagement:
    """Retrieves a tax engagement by ID."""
    require_permission(principal, "tax:read")
    engagement = await session.get(TaxEngagement, engagement_id)
    if not engagement or engagement.firm_id != principal.firm_id:
        raise NotFoundError("Tax engagement not found")
    await get_accessible_client(session, principal, engagement.client_id)
    return engagement


async def get_taxpayer_profile(
    session: AsyncSession,
    principal: Principal,
    engagement_id: uuid.UUID,
) -> TaxpayerProfile | None:
    """Gets the latest verified profile for an engagement."""
    require_permission(principal, "tax:read")
    res = await session.scalars(
        select(TaxpayerProfile)
        .where(
            TaxpayerProfile.firm_id == principal.firm_id,
            TaxpayerProfile.engagement_id == engagement_id,
        )
        .order_by(desc(TaxpayerProfile.version))
    )
    return res.first()


async def list_tax_workpapers(
    session: AsyncSession,
    principal: Principal,
    engagement_id: uuid.UUID,
) -> list[TaxWorkpaper]:
    """Lists tax workpapers for an engagement."""
    require_permission(principal, "tax:read")
    res = await session.scalars(
        select(TaxWorkpaper).where(
            TaxWorkpaper.firm_id == principal.firm_id,
            TaxWorkpaper.engagement_id == engagement_id,
        )
    )
    return list(res.all())


async def get_latest_calculation_run(
    session: AsyncSession,
    principal: Principal,
    engagement_id: uuid.UUID,
) -> TaxCalculationRun | None:
    """Gets the latest calculation run for an engagement."""
    require_permission(principal, "tax:read")
    res = await session.scalars(
        select(TaxCalculationRun)
        .where(
            TaxCalculationRun.firm_id == principal.firm_id,
            TaxCalculationRun.engagement_id == engagement_id,
        )
        .order_by(desc(TaxCalculationRun.created_at))
    )
    return res.first()


async def list_tax_drafts(
    session: AsyncSession,
    principal: Principal,
    engagement_id: uuid.UUID,
) -> list[TaxReturnDraft]:
    """Lists return drafts for an engagement."""
    require_permission(principal, "tax:read")
    res = await session.scalars(
        select(TaxReturnDraft)
        .where(
            TaxReturnDraft.firm_id == principal.firm_id,
            TaxReturnDraft.engagement_id == engagement_id,
        )
        .order_by(desc(TaxReturnDraft.version))
    )
    return list(res.all())
