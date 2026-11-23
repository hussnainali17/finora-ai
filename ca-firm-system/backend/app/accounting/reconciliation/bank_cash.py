"""Bank & Cash reconciliation module.

Checks performed:
- Match bank statement entries to cash book entries by date + amount + reference
- Flag unreconciled items (in bank but not in cash book, or vice versa)
- Timing differences (matched by amount but date differs by > 3 days)
- Unknown debits/credits (no reference or description)

Output:
- ``findings``: list[FindingData]
- ``schedules``: bank reconciliation schedule (outstanding deposits, cheques, adjusted balance)
- ``summary``: totals

All amounts use ``Decimal`` with explicit rounding to 4dp.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.accounting.reconciliation._types import FindingData, ReconciliationResult, ScheduleData, flatten_rows

logger = logging.getLogger("app.accounting.bank_cash")

FOUR_DP = Decimal("0.0001")
DATE_TOLERANCE_DAYS = 3
AMOUNT_TOLERANCE = Decimal("0.0100")  # 1 paisa tolerance for float-originating data


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


def _ref(row: dict[str, Any]) -> str:
    """Normalised reference string for matching."""
    r = str(row.get("reference") or row.get("cheque_number") or row.get("transaction_id") or "").strip()
    return r.lower()


def check_bank_cash(
    bank_statement_rows: list[dict[str, Any]],
    cash_book_rows: list[dict[str, Any]],
    period_start: date,
    period_end: date,
    currency: str = "PKR",
) -> ReconciliationResult:
    """Reconcile bank statement against the cash/ledger book.

    Args:
        bank_statement_rows: rows from the bank statement (normalized dict list).
        cash_book_rows: rows from the company's cash book / ledger.
        period_start: start of the period.
        period_end: end of the period.
        currency: ISO 4217 currency code.

    Returns:
        ReconciliationResult with findings, bank recon schedule, and summary.
    """
    findings: list[FindingData] = []
    bank_statement_rows = flatten_rows(bank_statement_rows)
    cash_book_rows = flatten_rows(cash_book_rows)

    # Index cash book rows by reference then amount for matching
    cash_by_ref: dict[str, list[int]] = defaultdict(list)
    cash_by_amount: dict[str, list[int]] = defaultdict(list)
    for idx, row in enumerate(cash_book_rows):
        ref = _ref(row)
        amt = _d(row.get("amount"))
        if ref:
            cash_by_ref[ref].append(idx)
        if amt is not None:
            cash_by_amount[str(amt)].append(idx)

    matched_cash: set[int] = set()
    matched_bank: set[int] = set()

    outstanding_deposits: list[dict[str, Any]] = []
    outstanding_cheques: list[dict[str, Any]] = []
    timing_differences: list[dict[str, Any]] = []

    for b_idx, b_row in enumerate(bank_statement_rows):
        b_ref = _ref(b_row)
        b_amount = _d(b_row.get("amount")) or Decimal(0)
        b_date = _date(b_row.get("date"))
        b_type = str(b_row.get("type") or b_row.get("dr_cr") or "").strip().lower()

        matched = False

        # Try reference match first
        if b_ref and b_ref in cash_by_ref:
            for c_idx in cash_by_ref[b_ref]:
                if c_idx in matched_cash:
                    continue
                c_row = cash_book_rows[c_idx]
                c_amount = _d(c_row.get("amount")) or Decimal(0)
                c_date = _date(c_row.get("date"))

                if abs(b_amount - c_amount) <= AMOUNT_TOLERANCE:
                    # Check date proximity
                    if b_date and c_date and abs((b_date - c_date).days) > DATE_TOLERANCE_DAYS:
                        timing_differences.append(
                            {
                                "bank_ref": b_ref,
                                "bank_date": str(b_date),
                                "book_date": str(c_date),
                                "amount": str(b_amount),
                                "days_difference": abs((b_date - c_date).days),
                            }
                        )
                    matched_cash.add(c_idx)
                    matched_bank.add(b_idx)
                    matched = True
                    break

        if not matched:
            # Unreconciled bank entry
            is_debit = b_type in ("dr", "debit", "d", "-")
            if not b_ref:
                findings.append(
                    FindingData(
                        finding_type="unknown_bank_entry",
                        severity="warning",
                        title="Bank entry with no reference",
                        description=(
                            f"Bank statement entry on {b_date}: {b_amount} {currency} "
                            f"has no reference number."
                        ),
                        source_ref={"row_index": b_idx},
                        amount=b_amount,
                        currency=currency,
                    )
                )
            if is_debit:
                outstanding_cheques.append(
                    {
                        "bank_row": b_idx,
                        "reference": b_ref or "(no ref)",
                        "date": str(b_date),
                        "amount": str(b_amount),
                    }
                )
            else:
                outstanding_deposits.append(
                    {
                        "bank_row": b_idx,
                        "reference": b_ref or "(no ref)",
                        "date": str(b_date),
                        "amount": str(b_amount),
                    }
                )
            findings.append(
                FindingData(
                    finding_type="unmatched_bank_entry",
                    severity="warning",
                    title="Unreconciled bank entry",
                    description=(
                        f"Bank entry ref='{b_ref or 'none'}' date={b_date} "
                        f"amount={b_amount} {currency} has no matching cash book entry."
                    ),
                    source_ref={"row_index": b_idx},
                    amount=b_amount,
                    currency=currency,
                )
            )

    # Cash book entries not matched in bank
    for c_idx, c_row in enumerate(cash_book_rows):
        if c_idx in matched_cash:
            continue
        c_amount = _d(c_row.get("amount")) or Decimal(0)
        c_date = _date(c_row.get("date"))
        c_ref = _ref(c_row)
        findings.append(
            FindingData(
                finding_type="unreconciled_book_entry",
                severity="warning",
                title="Cash book entry not found in bank statement",
                description=(
                    f"Cash book entry ref='{c_ref or 'none'}' date={c_date} "
                    f"amount={c_amount} {currency} has no matching bank statement entry."
                ),
                source_ref={"row_index": c_idx},
                amount=c_amount,
                currency=currency,
            )
        )

    # Bank recon schedule
    bank_total = sum((_d(r.get("amount")) or Decimal(0)) for r in bank_statement_rows)
    book_total = sum((_d(r.get("amount")) or Decimal(0)) for r in cash_book_rows)
    deposits_total = sum(Decimal(d["amount"]) for d in outstanding_deposits)
    cheques_total = sum(Decimal(d["amount"]) for d in outstanding_cheques)
    adjusted_bank = bank_total - cheques_total + deposits_total  # simplified

    recon_schedule = ScheduleData(
        schedule_type="bank_recon",
        label="Bank Reconciliation Statement",
        data={
            "currency": currency,
            "period_end": str(period_end),
            "bank_statement_balance": str(bank_total),
            "cash_book_balance": str(book_total),
            "outstanding_deposits": {
                "items": outstanding_deposits,
                "total": str(deposits_total),
            },
            "outstanding_cheques": {
                "items": outstanding_cheques,
                "total": str(cheques_total),
            },
            "timing_differences": timing_differences,
            "adjusted_bank_balance": str(adjusted_bank),
            "difference": str(adjusted_bank - book_total),
            "matched_count": len(matched_bank),
            "unmatched_bank_count": len(bank_statement_rows) - len(matched_bank),
            "unmatched_book_count": len(cash_book_rows) - len(matched_cash),
        },
    )

    by_severity: dict[str, int] = defaultdict(int)
    for f in findings:
        by_severity[f.severity] += 1

    summary = {
        "total_findings": len(findings),
        "by_severity": dict(by_severity),
        "bank_rows": len(bank_statement_rows),
        "book_rows": len(cash_book_rows),
        "matched": len(matched_bank),
        "bank_balance": str(bank_total),
        "book_balance": str(book_total),
        "difference": str(adjusted_bank - book_total),
    }

    return ReconciliationResult(findings=findings, schedules=[recon_schedule], summary=summary)
