"""Context retriever for the CA Review workflow.

Pulls comprehensive data from the existing multi-agent pipeline:
- Agent 1: Uploaded documents & extracted tables/rows
- Agent 2: Accounting review findings & reconciliation schedules
- Agent 3: Period-end adjustments (accruals, prepayments, depreciation, provisions)
- Agent 4: Financial reports (Trial Balance, P&L, Balance Sheet, validation checks)
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DataQualityFinding,
    Document,
    ExtractedColumn,
    ExtractedRow,
    ExtractedTable,
)
from app.models.accounting_review import (
    ReconciliationSchedule,
    ReviewFinding,
    ReviewRun,
)
from app.models.adjustments import PeriodAdjustment
from app.models.reporting import FinancialReport
from app.models.workflows import WorkflowRun

logger = logging.getLogger("app.workflows.ca_review.context")


async def retrieve_ca_context(
    session: AsyncSession,
    *,
    firm_id: uuid.UUID,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    query_text: str | None = None,
    row_limit: int = 100,
) -> dict[str, Any]:
    """Retrieves live data from all agents for this client/period."""
    # 1. Documents
    docs_res = await session.execute(
        select(Document)
        .where(
            Document.firm_id == firm_id,
            Document.client_id == client_id,
            Document.period_id == period_id,
        )
        .order_by(Document.created_at.desc())
    )
    documents = [
        {
            "id": str(d.id),
            "filename": getattr(d, "original_filename", getattr(d, "filename", "document")),
            "original_filename": getattr(d, "original_filename", getattr(d, "filename", "document")),
            "category": d.category,
            "status": d.status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs_res.scalars().all()
    ]

    # 2. Extracted Tables & Sample Rows
    tables_res = await session.execute(
        select(ExtractedTable).where(
            ExtractedTable.firm_id == firm_id,
            ExtractedTable.client_id == client_id,
            ExtractedTable.period_id == period_id,
        )
    )
    tables_list = list(tables_res.scalars().all())

    tables_data: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []

    for t in tables_list:
        # Get columns
        cols_res = await session.execute(
            select(ExtractedColumn).where(ExtractedColumn.table_id == t.id)
        )
        cols = [
            {
                "col_index": c.col_index,
                "header": c.header_normalized or c.header_raw,
                "role": c.confirmed_role or c.suggested_role,
            }
            for c in cols_res.scalars().all()
        ]

        # Get rows (up to row_limit)
        rows_res = await session.execute(
            select(ExtractedRow)
            .where(ExtractedRow.table_id == t.id)
            .order_by(ExtractedRow.row_index)
            .limit(row_limit)
        )
        table_rows = []
        for r in rows_res.scalars().all():
            row_info = {
                "id": r.id,
                "table_id": str(t.id),
                "table_type": t.confirmed_type or t.detected_type,
                "row_index": r.row_index,
                "raw": r.raw,
                "normalized": r.normalized,
                "flags": r.flags,
            }
            table_rows.append(row_info)
            all_rows.append(row_info)

        tables_data.append(
            {
                "id": str(t.id),
                "name": t.name,
                "detected_type": t.detected_type,
                "confirmed_type": t.confirmed_type,
                "type": t.confirmed_type or t.detected_type,
                "n_rows": t.n_rows,
                "currency": t.detected_currency,
                "columns": cols,
                "rows_sample": table_rows[:25],
            }
        )

    # 3. Agent 2: Accounting Review Runs & Findings
    rev_runs_res = await session.execute(
        select(ReviewRun)
        .where(
            ReviewRun.firm_id == firm_id,
            ReviewRun.client_id == client_id,
            ReviewRun.period_id == period_id,
        )
        .order_by(ReviewRun.created_at.desc())
        .limit(3)
    )
    review_runs = [
        {
            "id": str(r.id),
            "status": r.status,
            "trigger": r.trigger,
            "module_summary": r.module_summary,
            "error_message": r.error_message,
        }
        for r in rev_runs_res.scalars().all()
    ]

    findings_res = await session.execute(
        select(ReviewFinding)
        .where(
            ReviewFinding.firm_id == firm_id,
            ReviewFinding.client_id == client_id,
            ReviewFinding.period_id == period_id,
        )
        .order_by(ReviewFinding.created_at.desc())
    )
    review_findings = [
        {
            "id": str(f.id),
            "module": f.module,
            "finding_type": f.finding_type,
            "severity": f.severity,
            "title": f.title,
            "description": f.description,
            "amount": float(f.amount) if f.amount is not None else None,
            "currency": f.currency,
            "status": f.status,
            "source_ref": f.source_ref,
            "reviewer_note": f.reviewer_note,
        }
        for f in findings_res.scalars().all()
    ]

    # Reconciliation Schedules
    schedules_res = await session.execute(
        select(ReconciliationSchedule).where(
            ReconciliationSchedule.firm_id == firm_id,
            ReconciliationSchedule.client_id == client_id,
            ReconciliationSchedule.period_id == period_id,
        )
    )
    reconciliation_schedules = [
        {
            "id": str(s.id),
            "module": s.module,
            "schedule_type": s.schedule_type,
            "label": s.label,
            "data": s.data,
        }
        for s in schedules_res.scalars().all()
    ]

    # 4. Agent 3: Period Adjustments
    adjustments_res = await session.execute(
        select(PeriodAdjustment)
        .where(
            PeriodAdjustment.firm_id == firm_id,
            PeriodAdjustment.client_id == client_id,
            PeriodAdjustment.period_id == period_id,
        )
        .order_by(PeriodAdjustment.created_at.desc())
    )
    period_adjustments = [
        {
            "id": str(a.id),
            "category": a.category,
            "status": a.status,
            "version": a.version,
            "debit_account_code": a.debit_account_code,
            "debit_account_name": a.debit_account_name,
            "credit_account_code": a.credit_account_code,
            "credit_account_name": a.credit_account_name,
            "amount": float(a.amount),
            "currency": a.currency,
            "accounting_rationale": a.accounting_rationale,
            "calculation_details": a.calculation_details,
            "reviewer_decision": a.reviewer_decision,
        }
        for a in adjustments_res.scalars().all()
    ]

    # 5. Agent 4: Financial Reports
    reports_res = await session.execute(
        select(FinancialReport)
        .where(
            FinancialReport.firm_id == firm_id,
            FinancialReport.client_id == client_id,
            FinancialReport.period_id == period_id,
        )
        .order_by(FinancialReport.created_at.desc())
    )
    financial_reports = [
        {
            "id": str(r.id),
            "report_type": r.report_type,
            "status": r.status,
            "version": r.version,
            "currency": getattr(r, "currency", "PKR"),
            "data": r.data,
            "validation_details": getattr(r, "validation_results", {}),
            "narrative_summary": getattr(r, "narrative_summary", ""),
        }
        for r in reports_res.scalars().all()
    ]

    # 6. LangGraph Workflow runs
    wf_res = await session.execute(
        select(WorkflowRun)
        .where(
            WorkflowRun.firm_id == firm_id,
            WorkflowRun.client_id == client_id,
            WorkflowRun.period_id == period_id,
        )
        .order_by(WorkflowRun.created_at.desc())
        .limit(3)
    )
    workflow_runs = [
        {
            "id": str(w.id),
            "status": w.status,
            "current_step": w.current_step,
            "checkpoint_id": w.checkpoint_id,
            "state_data": w.state_data,
        }
        for w in wf_res.scalars().all()
    ]

    # Compute high-level snapshot numbers
    trial_balance_debits = Decimal("0")
    trial_balance_credits = Decimal("0")
    tb_rows_count = 0
    for r in all_rows:
        if r.get("table_type") in ("trial_balance", "tb"):
            tb_rows_count += 1
            norm = r.get("normalized") or {}
            deb = norm.get("debit") or (norm.get("amount") if norm.get("is_debit") else 0)
            cred = norm.get("credit") or (norm.get("amount") if not norm.get("is_debit") and norm.get("amount") else 0)
            try:
                trial_balance_debits += Decimal(str(deb or 0))
                trial_balance_credits += Decimal(str(cred or 0))
            except Exception:
                pass

    tb_balanced = (trial_balance_debits == trial_balance_credits) and (trial_balance_debits > 0)

    summary = {
        "documents_count": len(documents),
        "tables_count": len(tables_data),
        "total_extracted_rows": len(all_rows),
        "review_findings_count": len(review_findings),
        "open_findings_count": sum(1 for f in review_findings if f["status"] == "open"),
        "adjustments_count": len(period_adjustments),
        "proposed_adjustments_count": sum(1 for a in period_adjustments if a["status"] == "proposed"),
        "approved_adjustments_count": sum(1 for a in period_adjustments if a["status"] == "approved"),
        "financial_reports_count": len(financial_reports),
        "trial_balance": {
            "rows_count": tb_rows_count,
            "total_debits": float(trial_balance_debits),
            "total_credits": float(trial_balance_credits),
            "is_balanced": tb_balanced,
            "variance": float(abs(trial_balance_debits - trial_balance_credits)),
        },
        "latest_workflow_status": workflow_runs[0]["status"] if workflow_runs else "none",
    }

    return {
        "summary": summary,
        "documents": documents,
        "tables": tables_data,
        "rows": all_rows,
        "review_runs": review_runs,
        "review_findings": review_findings,
        "reconciliation_schedules": reconciliation_schedules,
        "period_adjustments": period_adjustments,
        "financial_reports": financial_reports,
        "workflow_runs": workflow_runs,
    }
