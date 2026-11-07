"""Deterministic calculation services for period-end adjustments.

Covers:
1. Accruals (expenses incurred but not yet billed/paid, revenue earned but not invoiced)
2. Prepayments (amortization of prepaid insurance, rent, software licenses)
3. Provisions (bad debt allowance, warranty provision)

All arithmetic uses Python `Decimal`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

FOUR_DP = Decimal("0.0001")


def _to_dec(val: Any, default: Decimal = Decimal("0")) -> Decimal:
    if val is None:
        return default
    if isinstance(val, Decimal):
        return val
    try:
        clean = str(val).replace(",", "").strip()
        if not clean:
            return default
        return Decimal(clean)
    except Exception:
        return default


@dataclass
class ProposedAdjustmentCandidate:
    category: str  # "accruals" | "prepayments" | "depreciation" | "provisions" | "other"
    debit_account_code: str
    debit_account_name: str
    credit_account_code: str
    credit_account_name: str
    amount: Decimal
    currency: str
    accounting_rationale: str
    calculation_details: dict[str, Any]
    source_refs: list[dict[str, Any]]


def calculate_prepayment_amortization(
    prepayment_rows: list[dict[str, Any]],
    period_start: date,
    period_end: date,
    currency: str = "PKR",
) -> list[ProposedAdjustmentCandidate]:
    """Calculates expense recognition for prepaid contracts/expenses.

    Formula: Total_Prepaid_Amount * (Period_Days_Elapsed / Total_Coverage_Days)
    """
    candidates: list[ProposedAdjustmentCandidate] = []

    for row in prepayment_rows:
        total_amount = _to_dec(row.get("amount") or row.get("total_amount") or row.get("cost"))
        start_date = row.get("start_date") or row.get("from_date")
        end_date = row.get("end_date") or row.get("to_date")
        desc = str(row.get("description") or "Prepaid Expense").strip()

        if total_amount <= 0 or not start_date or not end_date:
            continue

        if isinstance(start_date, str):
            try:
                start_date = date.fromisoformat(start_date)
            except ValueError:
                continue
        if isinstance(end_date, str):
            try:
                end_date = date.fromisoformat(end_date)
            except ValueError:
                continue

        coverage_days = (end_date - start_date).days + 1
        if coverage_days <= 0:
            continue

        # Overlap between contract coverage and accounting period
        eff_start = max(period_start, start_date)
        eff_end = min(period_end, end_date)
        if eff_end < eff_start:
            continue

        days_in_period = (eff_end - eff_start).days + 1
        amortized_amount = (
            (total_amount * Decimal(days_in_period)) / Decimal(coverage_days)
        ).quantize(FOUR_DP, rounding=ROUND_HALF_UP)

        if amortized_amount > Decimal("0"):
            candidates.append(
                ProposedAdjustmentCandidate(
                    category="prepayments",
                    debit_account_code="6020",
                    debit_account_name=f"{desc} Expense",
                    credit_account_code="1410",
                    credit_account_name="Prepaid Expenses",
                    amount=amortized_amount,
                    currency=currency,
                    accounting_rationale=(
                        f"Amortization of prepaid {desc} for {days_in_period} elapsed days "
                        f"within reporting period out of total {coverage_days} coverage days."
                    ),
                    calculation_details={
                        "formula": "total_amount * (days_in_period / coverage_days)",
                        "total_amount": str(total_amount),
                        "days_in_period": days_in_period,
                        "coverage_days": coverage_days,
                        "start_date": str(start_date),
                        "end_date": str(end_date),
                    },
                    source_refs=[
                        {
                            "table_id": row.get("_table_id"),
                            "document_id": row.get("_document_id"),
                            "row_index": row.get("_row_index"),
                            "description": desc,
                        }
                    ],
                )
            )

    return candidates


def calculate_bad_debt_provision(
    aged_ar_schedule_data: dict[str, Any],
    currency: str = "PKR",
) -> list[ProposedAdjustmentCandidate]:
    """Calculates allowance for doubtful accounts based on AR ageing buckets.

    Standard prudent CA policy:
    - 0-30 days: 1%
    - 31-60 days: 5%
    - 61-90 days: 10%
    - 91-120 days: 25%
    - Over 120 days: 50%
    """
    candidates: list[ProposedAdjustmentCandidate] = []
    buckets = aged_ar_schedule_data.get("buckets", {})
    rates = {
        "1_30": Decimal("0.01"),
        "31_60": Decimal("0.05"),
        "61_90": Decimal("0.10"),
        "91_120": Decimal("0.25"),
        "over_120": Decimal("0.50"),
    }

    total_provision = Decimal("0")
    breakdown: dict[str, str] = {}

    for bucket_key, rate in rates.items():
        b_info = buckets.get(bucket_key, {})
        b_total = _to_dec(b_info.get("total", "0"))
        if b_total > Decimal("0"):
            b_prov = (b_total * rate).quantize(FOUR_DP, rounding=ROUND_HALF_UP)
            total_provision += b_prov
            breakdown[bucket_key] = f"{b_total} * {rate} = {b_prov}"

    if total_provision > Decimal("0"):
        candidates.append(
            ProposedAdjustmentCandidate(
                category="provisions",
                debit_account_code="6090",
                debit_account_name="Bad Debt Expense",
                credit_account_code="1290",
                credit_account_name="Allowance for Expected Credit Losses",
                amount=total_provision,
                currency=currency,
                accounting_rationale="Provision for expected credit loss on aged accounts receivable based on default ageing risk bands.",
                calculation_details={
                    "formula": "sum(bucket_total * default_risk_rate)",
                    "breakdown": breakdown,
                    "total_provision": str(total_provision),
                },
                source_refs=[{"schedule_type": "ar_ageing", "policy": "prudent_aging_matrix"}],
            )
        )

    return candidates
