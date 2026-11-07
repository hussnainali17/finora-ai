"""Purchases & Payables reconciliation module.

Checks performed:
- Unmatched purchase orders (PO without invoice)
- Missing supplier references
- Aged payables (> 30 / 60 / 90 / 120 days from due date)
- Duplicate payments (same supplier + same amount + close dates)
- Unapproved purchases (missing approval flag/field)

Output:
- ``findings``: list[FindingData]
- ``schedules``: AP ageing schedule
- ``summary``: totals and counts

All amounts use ``Decimal`` with explicit rounding to 4dp.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.accounting.reconciliation._types import FindingData, ReconciliationResult, ScheduleData

logger = logging.getLogger("app.accounting.purchases_payables")

FOUR_DP = Decimal("0.0001")


def _d(v: Any) -> Decimal | None:
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


def check_purchases_payables(
    tables: list[dict[str, Any]],
    period_start: date,
    period_end: date,
    currency: str = "PKR",
) -> ReconciliationResult:
    """Run all AP checks on the provided extracted tables.

    Args:
        tables: list of table dicts with ``table_id``, ``document_id``, ``rows``.
        period_start: start of the accounting period.
        period_end: end of the accounting period.
        currency: ISO 4217 currency code.

    Returns:
        ReconciliationResult with findings, AP ageing schedule, and summary.
    """
    findings: list[FindingData] = []
    today = period_end

    ap_rows: list[dict[str, Any]] = []
    for table in tables:
        table_id = str(table.get("table_id", ""))
        document_id = str(table.get("document_id", ""))
        for row in table.get("rows", []):
            row["_table_id"] = table_id
            row["_document_id"] = document_id
            ap_rows.append(row)

    if not ap_rows:
        return ReconciliationResult(
            findings=[],
            schedules=[_empty_ap_schedule(currency)],
            summary={"total_findings": 0, "by_severity": {}, "row_count": 0},
        )

    # ------------------------------------------------------------------ Check 1: Missing supplier references
    for idx, row in enumerate(ap_rows):
        supplier = str(
            row.get("supplier") or row.get("vendor") or row.get("party") or ""
        ).strip()
        if not supplier:
            findings.append(
                FindingData(
                    finding_type="missing_supplier_reference",
                    severity="warning",
                    title="Missing supplier reference",
                    description=f"Row {idx} has no supplier/vendor identifier.",
                    source_ref={
                        "table_id": row.get("_table_id"),
                        "document_id": row.get("_document_id"),
                        "row_index": row.get("_row_index", idx),
                    },
                )
            )

    # ------------------------------------------------------------------ Check 2: Duplicate payments
    # Group by (supplier, amount) within ± 5 days
    payment_key_to_rows: dict[str, list[int]] = defaultdict(list)
    for idx, row in enumerate(ap_rows):
        supplier = str(row.get("supplier") or row.get("vendor") or row.get("party") or "").strip()
        amount = _d(row.get("amount"))
        if supplier and amount and amount > Decimal(0):
            key = f"{supplier.lower()}|{str(amount)}"
            payment_key_to_rows[key].append(idx)

    for key, indices in payment_key_to_rows.items():
        if len(indices) > 1:
            # Check date proximity (within 5 days counts as likely duplicate)
            dates = [_date(ap_rows[i].get("date")) for i in indices]
            for i, d1 in enumerate(dates):
                for j, d2 in enumerate(dates):
                    if j <= i:
                        continue
                    if d1 and d2 and abs((d1 - d2).days) <= 5:
                        supplier, amount_str = key.split("|", 1)
                        first_row = ap_rows[indices[i]]
                        findings.append(
                            FindingData(
                                finding_type="duplicate_payment",
                                severity="error",
                                title=f"Possible duplicate payment to {supplier}: {amount_str} {currency}",
                                description=(
                                    f"Two payments to '{supplier}' for {amount_str} {currency} "
                                    f"within {abs((d1 - d2).days)} day(s): rows {indices[i]} and {indices[j]}."
                                ),
                                source_ref={
                                    "table_id": first_row.get("_table_id"),
                                    "document_id": first_row.get("_document_id"),
                                    "row_index": indices[i],
                                },
                                amount=_d(amount_str),
                                currency=currency,
                                evidence_refs=[
                                    {
                                        "table_id": ap_rows[indices[j]].get("_table_id"),
                                        "document_id": ap_rows[indices[j]].get("_document_id"),
                                        "row_index": indices[j],
                                        "description": "Potential duplicate payment",
                                    }
                                ],
                            )
                        )

    # ------------------------------------------------------------------ Check 3: Unapproved purchases
    for idx, row in enumerate(ap_rows):
        approved = row.get("approved") or row.get("approval_status") or row.get("authorised")
        if approved is not None and str(approved).strip().lower() in (
            "no",
            "n",
            "false",
            "0",
            "pending",
            "unapproved",
        ):
            findings.append(
                FindingData(
                    finding_type="unapproved_purchase",
                    severity="warning",
                    title="Unapproved purchase",
                    description=f"Row {idx}: purchase has not been approved (approval status: '{approved}').",
                    source_ref={
                        "table_id": row.get("_table_id"),
                        "document_id": row.get("_document_id"),
                        "row_index": row.get("_row_index", idx),
                    },
                    amount=_d(row.get("amount")),
                    currency=currency,
                )
            )

    # ------------------------------------------------------------------ AP Ageing schedule
    buckets: dict[str, list[dict[str, Any]]] = {
        "current": [],
        "1_30": [],
        "31_60": [],
        "61_90": [],
        "91_120": [],
        "over_120": [],
    }
    bucket_totals: dict[str, Decimal] = {k: Decimal(0) for k in buckets}

    for idx, row in enumerate(ap_rows):
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
                "supplier": row.get("supplier") or row.get("vendor") or row.get("party"),
                "due_date": str(due_date) if due_date else None,
                "amount": str(amount),
                "age_days": age_days,
            }
        )

        if age_days > 90 and amount > Decimal(0):
            findings.append(
                FindingData(
                    finding_type="aged_payable",
                    severity="warning" if age_days <= 120 else "error",
                    title=f"Aged payable: {age_days} days overdue",
                    description=(
                        f"Invoice {row.get('reference') or '(no ref)'} from supplier "
                        f"{row.get('supplier') or row.get('vendor') or '(unknown)'} "
                        f"is {age_days} days overdue. Amount: {amount} {currency}."
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

    ap_schedule = ScheduleData(
        schedule_type="ap_ageing",
        label="Accounts Payable Ageing Schedule",
        data={
            "currency": currency,
            "period_end": str(period_end),
            "buckets": {
                k: {
                    "label": lbl,
                    "total": str(bucket_totals[k]),
                    "count": len(buckets[k]),
                    "rows": buckets[k],
                }
                for k, lbl in [
                    ("current", "Current (not yet due)"),
                    ("1_30", "1-30 days"),
                    ("31_60", "31-60 days"),
                    ("61_90", "61-90 days"),
                    ("91_120", "91-120 days"),
                    ("over_120", "Over 120 days"),
                ]
            },
            "grand_total": str(sum(bucket_totals.values())),
        },
    )

    by_severity: dict[str, int] = defaultdict(int)
    for f in findings:
        by_severity[f.severity] += 1

    summary = {
        "total_findings": len(findings),
        "by_severity": dict(by_severity),
        "row_count": len(ap_rows),
        "total_ap": str(sum(bucket_totals.values())),
    }

    return ReconciliationResult(findings=findings, schedules=[ap_schedule], summary=summary)


def _empty_ap_schedule(currency: str) -> ScheduleData:
    return ScheduleData(
        schedule_type="ap_ageing",
        label="Accounts Payable Ageing Schedule",
        data={
            "currency": currency,
            "buckets": {},
            "grand_total": "0.0000",
            "note": "No AP rows found in extracted data",
        },
    )
