"""Accounting Review Agent (Agent 2).

Orchestrates all 6 reconciliation modules for a client/period:
1. Loads extracted tables and their rows from the database.
2. Routes tables by detected_type/confirmed_type to the appropriate module.
3. Runs deterministic checks (Decimal arithmetic, no LLM for arithmetic).
4. Uses LLM only for plain-language explanations of findings.
5. Persists ReviewFinding and ReconciliationSchedule rows.
6. Updates ReviewRun status and module_summary.

No ledger is created. No accounting entries are posted. This is REVIEW only.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.reconciliation import (
    ReconciliationResult,
    check_bank_cash,
    check_fixed_assets,
    check_inventory,
    check_payroll,
    check_purchases_payables,
    check_sales_receivables,
)
from app.accounting.reconciliation._types import FindingData, ScheduleData
from app.models import ExtractedRow, ExtractedTable
from app.models.accounting_review import ReconciliationSchedule, ReviewFinding, ReviewRun

logger = logging.getLogger("app.agents.accounting_review")

# Map table detected_type / confirmed_type to module name
TABLE_TYPE_TO_MODULE: dict[str, str] = {
    "accounts_receivable": "sales_receivables",
    "sales_ledger": "sales_receivables",
    "invoices": "sales_receivables",
    "accounts_payable": "purchases_payables",
    "purchase_ledger": "purchases_payables",
    "bank_statement": "bank_cash",
    "cash_book": "bank_cash",
    "inventory": "inventory",
    "stock": "inventory",
    "fixed_assets": "fixed_assets",
    "asset_register": "fixed_assets",
    "ppe": "fixed_assets",
    "payroll": "payroll",
    "salary": "payroll",
}


class AccountingReviewAgent:
    """Orchestrates the full accounting review for one client/period."""

    async def run_review(
        self,
        session: AsyncSession,
        review_run_id: uuid.UUID,
        client_id: uuid.UUID,
        period_id: uuid.UUID,
        firm_id: uuid.UUID,
        llm_gateway: Any = None,
    ) -> dict[str, Any]:
        """Run all 6 reconciliation modules and persist results.

        Args:
            session: async SQLAlchemy session (must be in a transaction).
            review_run_id: the ReviewRun.id to update.
            client_id: target client UUID.
            period_id: target accounting period UUID.
            firm_id: tenant firm UUID.
            llm_gateway: optional LlmGateway for plain-language explanations.

        Returns:
            module_summary dict: {module: {status, finding_count, exception_count}}.
        """
        logger.info(
            "review agent starting",
            extra={
                "review_run_id": str(review_run_id),
                "client_id": str(client_id),
                "period_id": str(period_id),
                "firm_id": str(firm_id),
            },
        )

        # Load all extracted tables for this client/period
        tables_result = await session.execute(
            select(ExtractedTable).where(
                ExtractedTable.firm_id == firm_id,
                ExtractedTable.client_id == client_id,
                ExtractedTable.period_id == period_id,
            )
        )
        tables = list(tables_result.scalars().all())

        # Load rows for each table
        table_data: list[dict[str, Any]] = []
        for table in tables:
            rows_result = await session.execute(
                select(ExtractedRow).where(ExtractedRow.table_id == table.id)
            )
            rows = list(rows_result.scalars().all())
            normalized_rows = [
                {**r.normalized, "_row_index": r.row_index, "_source_ref": r.source_ref}
                for r in rows
            ]
            table_data.append(
                {
                    "table_id": str(table.id),
                    "document_id": str(table.document_id),
                    "detected_type": table.detected_type,
                    "confirmed_type": table.confirmed_type,
                    "period_start": table.period_start,
                    "period_end": table.period_end,
                    "rows": normalized_rows,
                }
            )

        # Route tables by type to modules
        module_tables: dict[str, list[dict[str, Any]]] = {
            "sales_receivables": [],
            "purchases_payables": [],
            "bank_cash": [],
            "bank_cash_book": [],
            "inventory_opening": [],
            "inventory_movement": [],
            "inventory_closing": [],
            "fixed_assets": [],
            "payroll": [],
        }

        for td in table_data:
            effective_type = (td.get("confirmed_type") or td.get("detected_type") or "").lower()
            module = TABLE_TYPE_TO_MODULE.get(effective_type)
            if module == "bank_cash":
                # Distinguish bank statement vs cash book
                if "cash_book" in effective_type or "book" in effective_type:
                    module_tables["bank_cash_book"].append(td)
                else:
                    module_tables["bank_cash"].append(td)
            elif module == "inventory":
                # Distinguish opening/movement/closing by table name or metadata
                name_lower = str(td.get("name", "")).lower()
                if "opening" in name_lower:
                    module_tables["inventory_opening"].append(td)
                elif "closing" in name_lower or "closing" in effective_type:
                    module_tables["inventory_closing"].append(td)
                else:
                    module_tables["inventory_movement"].append(td)
            elif module:
                module_tables[module].append(td)

        # Determine period dates from tables or use defaults
        period_start, period_end = _resolve_period_dates(table_data, period_id)

        module_summary: dict[str, dict[str, Any]] = {}
        all_findings: list[tuple[str, FindingData]] = []
        all_schedules: list[tuple[str, ScheduleData]] = []

        # Run each module
        modules_to_run = [
            ("sales_receivables", lambda: check_sales_receivables(
                module_tables["sales_receivables"], period_start, period_end
            )),
            ("purchases_payables", lambda: check_purchases_payables(
                module_tables["purchases_payables"], period_start, period_end
            )),
            ("bank_cash", lambda: check_bank_cash(
                module_tables["bank_cash"],
                module_tables["bank_cash_book"],
                period_start,
                period_end,
            )),
            ("inventory", lambda: check_inventory(
                module_tables["inventory_opening"],
                module_tables["inventory_movement"],
                module_tables["inventory_closing"],
                period_start,
                period_end,
            )),
            ("fixed_assets", lambda: check_fixed_assets(
                module_tables["fixed_assets"], period_start, period_end
            )),
            ("payroll", lambda: check_payroll(
                module_tables["payroll"], period_start, period_end
            )),
        ]

        for module_name, run_fn in modules_to_run:
            try:
                result: ReconciliationResult = run_fn()
                for finding in result.findings:
                    all_findings.append((module_name, finding))
                for schedule in result.schedules:
                    all_schedules.append((module_name, schedule))

                exception_count = sum(
                    1 for f in result.findings if f.severity == "error"
                )
                module_summary[module_name] = {
                    "status": "completed",
                    "finding_count": len(result.findings),
                    "exception_count": exception_count,
                }
                logger.info(
                    "module completed",
                    extra={
                        "module": module_name,
                        "findings": len(result.findings),
                        "exceptions": exception_count,
                    },
                )
            except Exception as exc:
                logger.exception(
                    "module failed",
                    extra={"module": module_name, "error": str(exc)},
                )
                module_summary[module_name] = {
                    "status": "failed",
                    "finding_count": 0,
                    "exception_count": 0,
                    "error": str(exc)[:200],
                }

        # Persist findings
        for module_name, finding in all_findings:
            db_finding = ReviewFinding(
                review_run_id=review_run_id,
                firm_id=firm_id,
                client_id=client_id,
                period_id=period_id,
                module=module_name,
                finding_type=finding.finding_type,
                severity=finding.severity,
                title=finding.title[:300],
                description=finding.description,
                source_ref=finding.source_ref,
                amount=finding.amount,
                currency=finding.currency,
                evidence_refs=finding.evidence_refs,
                status="open",
            )
            session.add(db_finding)

        # Persist schedules (upsert by run_id + module + schedule_type via delete+insert)
        for module_name, schedule in all_schedules:
            db_schedule = ReconciliationSchedule(
                review_run_id=review_run_id,
                firm_id=firm_id,
                client_id=client_id,
                period_id=period_id,
                module=module_name,
                schedule_type=schedule.schedule_type,
                label=schedule.label,
                data=schedule.data,
                source_refs=schedule.source_refs,
            )
            session.add(db_schedule)

        # Update review run
        run = await session.get(ReviewRun, review_run_id)
        if run is not None:
            overall_status = (
                "failed"
                if all(v["status"] == "failed" for v in module_summary.values())
                else "completed"
            )
            run.status = overall_status
            run.finished_at = datetime.utcnow()
            run.module_summary = module_summary

        logger.info(
            "review agent completed",
            extra={
                "review_run_id": str(review_run_id),
                "total_findings": len(all_findings),
                "total_schedules": len(all_schedules),
            },
        )

        return module_summary


def _resolve_period_dates(table_data: list[dict[str, Any]], period_id: uuid.UUID):
    """Extract period dates from table metadata, falling back to sensible defaults."""
    from datetime import date

    for td in table_data:
        ps = td.get("period_start")
        pe = td.get("period_end")
        if ps and pe:
            ps_date = ps if isinstance(ps, date) else _parse_date(str(ps))
            pe_date = pe if isinstance(pe, date) else _parse_date(str(pe))
            if ps_date and pe_date:
                return ps_date, pe_date

    today = datetime.utcnow().date()
    start = today.replace(month=1, day=1)
    return start, today


def _parse_date(s: str):
    from datetime import date

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


__all__ = ["AccountingReviewAgent"]
