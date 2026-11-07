"""Accounting Review service (Phase 6).

This service manages ReviewRun lifecycle, persists findings and schedules,
and dispatches Agent 2 for a client/period. It is the single entry point for
all accounting review operations — the API and workers both call this service.

No ledger is created, no accounting entries are posted. This is REVIEW only.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.models.accounting_review import (
    ReconciliationSchedule,
    ReviewFinding,
    ReviewRun,
)
from app.services.authz import Principal, get_accessible_client, require_permission

logger = logging.getLogger("app.services.accounting_review")

ALLOWED_FINDING_STATUSES = frozenset({"open", "explained", "resolved", "escalated"})


# ---------------------------------------------------------------------------
# Review run management
# ---------------------------------------------------------------------------


async def create_review_run(
    session: AsyncSession,
    principal: Principal,
    *,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    trigger: str = "manual",
) -> ReviewRun:
    """Create a new ReviewRun for the given client/period.

    Returns the existing run if one is already pending or running (idempotent
    per active run — prevents duplicate concurrent executions).
    """
    require_permission(principal, "review:manage")
    # Ensure the principal can access this client
    await get_accessible_client(session, principal, client_id)

    # Check for an already-active run
    existing = await session.scalar(
        select(ReviewRun).where(
            ReviewRun.firm_id == principal.firm_id,
            ReviewRun.client_id == client_id,
            ReviewRun.period_id == period_id,
            ReviewRun.status.in_(["pending", "running"]),
        )
    )
    if existing is not None:
        logger.info(
            "review run already active — returning existing",
            extra={"review_run_id": str(existing.id)},
        )
        return existing

    run = ReviewRun(
        firm_id=principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        status="pending",
        trigger=trigger,
        triggered_by=principal.user_id,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    logger.info(
        "review run created",
        extra={
            "review_run_id": str(run.id),
            "client_id": str(client_id),
            "period_id": str(period_id),
        },
    )
    return run


async def get_review_run(
    session: AsyncSession,
    principal: Principal,
    review_run_id: uuid.UUID,
) -> ReviewRun:
    """Load a ReviewRun by id — enforces firm and client isolation."""
    require_permission(principal, "review:read")
    run = await session.scalar(
        select(ReviewRun).where(
            ReviewRun.id == review_run_id,
            ReviewRun.firm_id == principal.firm_id,
        )
    )
    if run is None:
        raise NotFoundError("Review run not found")
    # Verify the principal can access the client
    await get_accessible_client(session, principal, run.client_id)
    return run


async def list_review_runs(
    session: AsyncSession,
    principal: Principal,
    *,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[ReviewRun]:
    require_permission(principal, "review:read")
    await get_accessible_client(session, principal, client_id)
    result = await session.scalars(
        select(ReviewRun)
        .where(
            ReviewRun.firm_id == principal.firm_id,
            ReviewRun.client_id == client_id,
            ReviewRun.period_id == period_id,
        )
        .order_by(ReviewRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.all())


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


async def list_findings(
    session: AsyncSession,
    principal: Principal,
    review_run_id: uuid.UUID,
    *,
    module: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ReviewFinding]:
    require_permission(principal, "review:read")
    run = await get_review_run(session, principal, review_run_id)

    q = select(ReviewFinding).where(
        ReviewFinding.review_run_id == run.id,
        ReviewFinding.firm_id == principal.firm_id,
    )
    if module:
        q = q.where(ReviewFinding.module == module)
    if severity:
        q = q.where(ReviewFinding.severity == severity)
    if status:
        q = q.where(ReviewFinding.status == status)

    q = q.order_by(ReviewFinding.severity.desc(), ReviewFinding.created_at).limit(limit).offset(offset)
    result = await session.scalars(q)
    return list(result.all())


async def update_finding_status(
    session: AsyncSession,
    principal: Principal,
    finding_id: uuid.UUID,
    *,
    new_status: str,
    reviewer_note: str | None = None,
) -> ReviewFinding:
    """Transition a finding's status. Requires review:resolve permission."""
    require_permission(principal, "review:resolve")

    if new_status not in ALLOWED_FINDING_STATUSES:
        raise ValueError(f"Invalid status '{new_status}'. Allowed: {sorted(ALLOWED_FINDING_STATUSES)}")

    finding = await session.scalar(
        select(ReviewFinding).where(
            ReviewFinding.id == finding_id,
            ReviewFinding.firm_id == principal.firm_id,
        )
    )
    if finding is None:
        raise NotFoundError("Finding not found")
    # Client-level isolation
    await get_accessible_client(session, principal, finding.client_id)

    finding.status = new_status
    finding.reviewer_id = principal.user_id
    finding.reviewed_at = datetime.now(UTC)
    if reviewer_note is not None:
        finding.reviewer_note = reviewer_note
    finding.updated_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(finding)
    return finding


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------


async def list_schedules(
    session: AsyncSession,
    principal: Principal,
    review_run_id: uuid.UUID,
) -> list[ReconciliationSchedule]:
    require_permission(principal, "review:read")
    run = await get_review_run(session, principal, review_run_id)
    result = await session.scalars(
        select(ReconciliationSchedule).where(
            ReconciliationSchedule.review_run_id == run.id,
            ReconciliationSchedule.firm_id == principal.firm_id,
        )
    )
    return list(result.all())


async def get_schedule(
    session: AsyncSession,
    principal: Principal,
    review_run_id: uuid.UUID,
    schedule_id: uuid.UUID,
) -> ReconciliationSchedule:
    require_permission(principal, "review:read")
    run = await get_review_run(session, principal, review_run_id)
    schedule = await session.scalar(
        select(ReconciliationSchedule).where(
            ReconciliationSchedule.id == schedule_id,
            ReconciliationSchedule.review_run_id == run.id,
            ReconciliationSchedule.firm_id == principal.firm_id,
        )
    )
    if schedule is None:
        raise NotFoundError("Schedule not found")
    return schedule


# ---------------------------------------------------------------------------
# Agent execution loop (called by the FastAPI background loop)
# ---------------------------------------------------------------------------


async def run_pending_reviews(session: AsyncSession) -> int:
    """Execute all 'running' ReviewRuns via Agent 2. Returns count processed.

    Called from the FastAPI lifespan background loop (similar to run_intake_loop).
    Workers set the status to 'running'; this function does the actual work.
    """
    from app.agents.accounting_review_agent.agent import AccountingReviewAgent

    runs_result = await session.scalars(
        select(ReviewRun).where(ReviewRun.status == "running").limit(5)
    )
    runs = list(runs_result.all())

    processed = 0
    for run in runs:
        try:
            agent = AccountingReviewAgent()
            await agent.run_review(
                session,
                review_run_id=run.id,
                client_id=run.client_id,
                period_id=run.period_id,
                firm_id=run.firm_id,
            )
            processed += 1
        except Exception:
            logger.exception(
                "review agent failed",
                extra={"review_run_id": str(run.id)},
            )
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            run.error_message = "Internal error during review execution"
            await session.commit()

    return processed
