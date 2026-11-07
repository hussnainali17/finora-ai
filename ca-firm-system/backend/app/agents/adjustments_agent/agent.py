"""Agent 3: Period-End Adjustments Agent.

Identifies, calculates, and registers proposed period-end adjustments:
- Depreciation (Fixed assets)
- Prepayments amortization
- Accruals (Accrued expenses, unbilled revenues)
- Provisions (Bad debt provision from AR ageing)

All arithmetic is deterministic Python with Decimal.
Adjustments are stored in status 'proposed' and NEVER posted to a ledger.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.adjustments import (
    ProposedAdjustmentCandidate,
    calculate_bad_debt_provision,
    calculate_prepayment_amortization,
)
from app.accounting.depreciation import calculate_asset_depreciation
from app.models import ExtractedRow, ExtractedTable
from app.models.accounting_review import ReconciliationSchedule, ReviewFinding
from app.models.adjustments import PeriodAdjustment

logger = logging.getLogger("app.agents.adjustments")


class AdjustmentsAgent:
    """Agent 3: Period-End Adjustments generator."""

    async def generate_adjustments_for_period(
        self,
        session: AsyncSession,
        client_id: uuid.UUID,
        period_id: uuid.UUID,
        firm_id: uuid.UUID,
        llm_gateway: Any = None,
    ) -> list[PeriodAdjustment]:
        """Scans extracted tables, reconciliation schedules, and review findings

        to calculate and propose period-end adjustments.
        """
        logger.info(
            "adjustments agent running",
            extra={"client_id": str(client_id), "period_id": str(period_id)},
        )

        # 1. Fetch tables for period
        tables_res = await session.execute(
            select(ExtractedTable).where(
                ExtractedTable.firm_id == firm_id,
                ExtractedTable.client_id == client_id,
                ExtractedTable.period_id == period_id,
            )
        )
        tables = list(tables_res.scalars().all())

        # Determine period date window
        today = datetime.utcnow().date()
        period_start = today.replace(month=1, day=1)
        period_end = today
        for t in tables:
            if t.period_start and t.period_end:
                period_start = t.period_start
                period_end = t.period_end
                break

        # Load normalized rows
        fixed_asset_rows: list[dict[str, Any]] = []
        prepayment_rows: list[dict[str, Any]] = []

        for table in tables:
            rows_res = await session.execute(
                select(ExtractedRow).where(ExtractedRow.table_id == table.id)
            )
            for r in rows_res.scalars().all():
                row_dict = {
                    **r.normalized,
                    "_row_index": r.row_index,
                    "_table_id": str(table.id),
                    "_document_id": str(table.document_id),
                }
                tbl_type = (table.confirmed_type or table.detected_type or "").lower()
                tbl_name = (table.name or "").lower()

                if any(k in tbl_type or k in tbl_name for k in ("asset", "fa", "ppe", "depreciation")):
                    fixed_asset_rows.append(row_dict)
                elif any(k in tbl_type or k in tbl_name for k in ("prepay", "prepaid", "insurance", "contract")):
                    prepayment_rows.append(row_dict)

        candidates: list[ProposedAdjustmentCandidate] = []

        # A. Depreciation candidates
        if fixed_asset_rows:
            dep_proposals = calculate_asset_depreciation(
                fixed_asset_rows, period_start, period_end
            )
            for dp in dep_proposals:
                candidates.append(
                    ProposedAdjustmentCandidate(
                        category="depreciation",
                        debit_account_code=dp.debit_account_code,
                        debit_account_name=dp.debit_account_name,
                        credit_account_code=dp.credit_account_code,
                        credit_account_name=dp.credit_account_name,
                        amount=dp.amount,
                        currency=dp.currency,
                        accounting_rationale=f"Periodic depreciation for asset {dp.asset_code} ({dp.asset_name}) calculated via {dp.method}.",
                        calculation_details=dp.calculation_details,
                        source_refs=[dp.source_ref],
                    )
                )

        # B. Prepayment amortization candidates
        if prepayment_rows:
            prep_proposals = calculate_prepayment_amortization(
                prepayment_rows, period_start, period_end
            )
            candidates.extend(prep_proposals)

        # C. Bad debt provisions from AR ageing schedule
        schedules_res = await session.execute(
            select(ReconciliationSchedule).where(
                ReconciliationSchedule.firm_id == firm_id,
                ReconciliationSchedule.client_id == client_id,
                ReconciliationSchedule.period_id == period_id,
                ReconciliationSchedule.schedule_type == "ar_ageing",
            )
        )
        ar_sched = schedules_res.scalars().first()
        if ar_sched and isinstance(ar_sched.data, dict):
            prov_proposals = calculate_bad_debt_provision(ar_sched.data)
            candidates.extend(prov_proposals)

        # D. Accruals from unresolved review findings (e.g. unrecorded interest/bills)
        findings_res = await session.execute(
            select(ReviewFinding).where(
                ReviewFinding.firm_id == firm_id,
                ReviewFinding.client_id == client_id,
                ReviewFinding.period_id == period_id,
                ReviewFinding.finding_type.in_(["unrecorded_expense", "accrued_liability"]),
            )
        )
        for f in findings_res.scalars().all():
            if f.amount and f.amount > 0:
                candidates.append(
                    ProposedAdjustmentCandidate(
                        category="accruals",
                        debit_account_code="6050",
                        debit_account_name="Accrued Operating Expense",
                        credit_account_code="2120",
                        credit_account_name="Accrued Liabilities",
                        amount=Decimal(str(f.amount)),
                        currency=f.currency or "PKR",
                        accounting_rationale=f"Accrual based on review finding: {f.title}. {f.description}",
                        calculation_details={"finding_id": str(f.id), "origin": "review_finding"},
                        source_refs=[f.source_ref] if f.source_ref else [],
                    )
                )

        created_adjustments: list[PeriodAdjustment] = []
        for c in candidates:
            adj = PeriodAdjustment(
                firm_id=firm_id,
                client_id=client_id,
                period_id=period_id,
                category=c.category,
                status="proposed",
                version=1,
                debit_account_code=c.debit_account_code,
                debit_account_name=c.debit_account_name,
                credit_account_code=c.credit_account_code,
                credit_account_name=c.credit_account_name,
                amount=c.amount,
                currency=c.currency,
                accounting_rationale=c.accounting_rationale,
                calculation_details=c.calculation_details,
                source_refs=c.source_refs,
                prepared_by_agent="adjustments_agent",
                history=[
                    {
                        "action": "proposed",
                        "timestamp": datetime.utcnow().isoformat(),
                        "actor": "adjustments_agent",
                        "note": "Initial generation by Agent 3",
                    }
                ],
            )
            session.add(adj)
            created_adjustments.append(adj)

        await session.commit()
        for adj in created_adjustments:
            await session.refresh(adj)

        logger.info(
            "adjustments agent generated proposals",
            extra={"count": len(created_adjustments)},
        )
        return created_adjustments
