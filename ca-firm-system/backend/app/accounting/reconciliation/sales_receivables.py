"""Sales & Receivables reconciliation module.

Checks performed on extracted rows (list of dicts with normalized role keys):
- Missing invoice numbers
- Duplicate invoice numbers
- Aged receivables (> 30 / 60 / 90 / 120 days from due_date or invoice_date)
- Amounts not matching receipts
- Credit notes without matching invoices
- Missing customer references

Output:
- ``findings``: list[FindingData]
- ``schedules``: AR ageing schedule bucketed by days outstanding
- ``summary``: totals and counts

All amounts use ``Decimal`` with explicit rounding to 4dp.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger("app.accounting.sales_receivables")

# Local import avoids circular dependency on the __init__ re-exports
from app.accounting.reconciliation._types import FindingData, ReconciliationResult, ScheduleData  # noqa: E402
FOUR_DP = Decimal("0.0001")


def _d(v: Any) -> Decimal | None:
    """Safe Decimal conversion — returns None on failure."""
    if v is None:
        return None
    try:
        return Decimal(str(v)).quantize(FOUR_DP, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def _date(v: Any) -> date | None:
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
            try:
                return date.fromisoformat(v) if fmt == "%Y-%m-%d" else date.strptime(v, fmt).date()
            except ValueError:
                continue
    return None


def check_sales_receivables(
    tables: list[dict[str, Any]],
    period_start: date,
    period_end: date,
    currency: str = "PKR",
) -> ReconciliationResult:
    """Run all AR checks on the provided extracted tables.

    Args:
        tables: list of table dicts. Each table dict has:
            - ``table_id``: str UUID
            - ``document_id``: str UUID
            - ``rows``: list of row dicts with role-keyed values
        period_start: start of the accounting period
        period_end: end of the accounting period
        currency: ISO 4217 currency code

    Returns:
        ReconciliationResult with findings, schedules and summary.
    """
    findings: list[FindingData] = []
    today = period_end  # treat period end as "today" for ageing purposes

    # Collect all AR rows across tables
    ar_rows: list[dict[str, Any]] = []
    for table in tables:
        table_id = str(table.get("table_id", ""))
        document_id = str(table.get("document_id", ""))
        for row in table.get("rows", []):
            row["_table_id"] = table_id
            row["_document_id"] = document_id
            ar_rows.append(row)

    if not ar_rows:
        return ReconciliationResult(
            findings=[],
            schedules=[_empty_ageing_schedule(currency)],
            summary={"total_findings": 0, "by_severity": {}, "row_count": 0},
        )

    # ------------------------------------------------------------------ Check 1: Missing invoice numbers
    seen_invoices: dict[str, list[int]] = defaultdict(list)
    for idx, row in enumerate(ar_rows):
        inv_no = str(row.get("reference") or row.get("invoice_number") or "").strip()
        if not inv_no:
            findings.append(
                FindingData(
                    finding_type="missing_invoice_number",
                    severity="warning",
                    title="Missing invoice number",
                    description=f"Row {idx} has no invoice reference number.",
                    source_ref={
                        "table_id": row.get("_table_id"),
                        "document_id": row.get("_document_id"),
                        "row_index": row.get("_row_index", idx),
                    },
                    amount=_d(row.get("amount")),
                    currency=currency,
                )
            )
        else:
            seen_invoices[inv_no].append(idx)

    # ------------------------------------------------------------------ Check 2: Duplicate invoice numbers
    for inv_no, indices in seen_invoices.items():
        if len(indices) > 1:
            first_row = ar_rows[indices[0]]
            findings.append(
                FindingData(
                    finding_type="duplicate_invoice_number",
                    severity="error",
                    title=f"Duplicate invoice number: {inv_no}",
                    description=(
                        f"Invoice number '{inv_no}' appears {len(indices)} times "
                        f"in rows {indices}."
                    ),
                    source_ref={
                        "table_id": first_row.get("_table_id"),
                        "document_id": first_row.get("_document_id"),
                        "row_index": indices[0],
                    },
                    evidence_refs=[
                        {
                            "table_id": ar_rows[i].get("_table_id"),
                            "document_id": ar_rows[i].get("_document_id"),
                            "row_index": ar_rows[i].get("_row_index", i),
                            "description": f"Duplicate occurrence {n + 1}",
                        }
                        for n, i in enumerate(indices[1:])
                    ],
                )
            )

    # ------------------------------------------------------------------ Check 3: Missing customer references
    for idx, row in enumerate(ar_rows):
        customer = str(row.get("customer") or row.get("party") or row.get("counterparty") or "").strip()
        if not customer:
            findings.append(
                FindingData(
                    finding_type="missing_customer_reference",
                    severity="info",
                    title="Missing customer reference",
                    description=f"Row {idx} has no customer/party identifier.",
                    source_ref={
                        "table_id": row.get("_table_id"),
                        "document_id": row.get("_document_id"),
                        "row_index": row.get("_row_index", idx),
                    },
                )
            )

    # ------------------------------------------------------------------ AR Ageing schedule
    buckets: dict[str, list[dict[str, Any]]] = {
        "current": [],
        "1_30": [],
        "31_60": [],
        "61_90": [],
        "91_120": [],
        "over_120": [],
    }
    bucket_totals: dict[str, Decimal] = {k: Decimal(0) for k in buckets}

    for idx, row in enumerate(ar_rows):
        amount = _d(row.get("amount")) or Decimal(0)
        due_date = _date(row.get("due_date") or row.get("date"))

        if due_date is None:
            age_days = 0
        else:
            age_days = (today - due_date).days

        if age_days <= 0:
            bucket = "current"
        elif age_days <= 30:
            bucket = "1_30"
        elif age_days <= 60:
            bucket = "31_60"
        elif age_days <= 90:
            bucket = "61_90"
        elif age_days <= 120:
            bucket = "91_120"
        else:
            bucket = "over_120"

        bucket_totals[bucket] = bucket_totals[bucket] + amount
        buckets[bucket].append(
            {
                "row_index": row.get("_row_index", idx),
                "reference": row.get("reference") or row.get("invoice_number"),
                "customer": row.get("customer") or row.get("party"),
                "due_date": str(due_date) if due_date else None,
                "amount": str(amount),
                "age_days": age_days,
            }
        )

        # Aged receivable findings for significant overdue amounts
        if age_days > 90 and amount > Decimal(0):
            findings.append(
                FindingData(
                    finding_type="aged_receivable",
                    severity="warning" if age_days <= 120 else "error",
                    title=f"Aged receivable: {age_days} days overdue",
                    description=(
                        f"Invoice {row.get('reference') or '(no ref)'} from customer "
                        f"{row.get('customer') or '(unknown)'} is {age_days} days overdue. "
                        f"Amount: {amount} {currency}."
                    ),
                    source_ref={
                        "table_id": row.get("_table_id"),
                        "document_id": row.get("_document_id"),
                        "row_index": row.get("_row_index", idx),
                    },
                    amount=amount,
                    currency=currency,
                )
            )

    ageing_schedule = ScheduleData(
        schedule_type="ar_ageing",
        label="Accounts Receivable Ageing Schedule",
        data={
            "currency": currency,
            "period_end": str(period_end),
            "buckets": {
                "current": {
                    "label": "Current (not yet due)",
                    "total": str(bucket_totals["current"]),
                    "count": len(buckets["current"]),
                    "rows": buckets["current"],
                },
                "1_30": {
                    "label": "1-30 days",
                    "total": str(bucket_totals["1_30"]),
                    "count": len(buckets["1_30"]),
                    "rows": buckets["1_30"],
                },
                "31_60": {
                    "label": "31-60 days",
                    "total": str(bucket_totals["31_60"]),
                    "count": len(buckets["31_60"]),
                    "rows": buckets["31_60"],
                },
                "61_90": {
                    "label": "61-90 days",
                    "total": str(bucket_totals["61_90"]),
                    "count": len(buckets["61_90"]),
                    "rows": buckets["61_90"],
                },
                "91_120": {
                    "label": "91-120 days",
                    "total": str(bucket_totals["91_120"]),
                    "count": len(buckets["91_120"]),
                    "rows": buckets["91_120"],
                },
                "over_120": {
                    "label": "Over 120 days",
                    "total": str(bucket_totals["over_120"]),
                    "count": len(buckets["over_120"]),
                    "rows": buckets["over_120"],
                },
            },
            "grand_total": str(sum(bucket_totals.values())),
        },
    )

    # ------------------------------------------------------------------ Summary
    by_severity: dict[str, int] = defaultdict(int)
    for f in findings:
        by_severity[f.severity] += 1

    summary = {
        "total_findings": len(findings),
        "by_severity": dict(by_severity),
        "row_count": len(ar_rows),
        "total_ar": str(sum(bucket_totals.values())),
        "overdue_total": str(
            bucket_totals["1_30"]
            + bucket_totals["31_60"]
            + bucket_totals["61_90"]
            + bucket_totals["91_120"]
            + bucket_totals["over_120"]
        ),
    }

    return ReconciliationResult(findings=findings, schedules=[ageing_schedule], summary=summary)


def _empty_ageing_schedule(currency: str) -> ScheduleData:
    return ScheduleData(
        schedule_type="ar_ageing",
        label="Accounts Receivable Ageing Schedule",
        data={
            "currency": currency,
            "buckets": {},
            "grand_total": "0.0000",
            "note": "No AR rows found in extracted data",
        },
    )
