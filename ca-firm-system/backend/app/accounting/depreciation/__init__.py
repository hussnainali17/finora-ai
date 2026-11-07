"""Deterministic depreciation calculation service.

All calculations use Python `Decimal` with explicit rounding rules (ROUND_HALF_UP).
Floating point arithmetic is strictly forbidden for financial calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

FOUR_DP = Decimal("0.0001")
TWO_DP = Decimal("0.01")


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


def calculate_straight_line_depreciation(
    cost: Decimal,
    salvage_value: Decimal,
    useful_life_years: Decimal,
    days_held: int,
    period_days: int = 365,
) -> Decimal:
    """Calculate straight-line depreciation for a given period.

    Formula: ((Cost - Salvage) / Useful_Life) * (Days_Held / Period_Days)
    """
    if useful_life_years <= 0:
        return Decimal("0.0000")
    depreciable_base = max(Decimal("0"), cost - salvage_value)
    annual_depreciation = depreciable_base / useful_life_years
    period_depreciation = (annual_depreciation * Decimal(days_held)) / Decimal(period_days)
    return period_depreciation.quantize(FOUR_DP, rounding=ROUND_HALF_UP)


def calculate_reducing_balance_depreciation(
    carrying_amount: Decimal,
    rate: Decimal,
    days_held: int,
    period_days: int = 365,
) -> Decimal:
    """Calculate declining balance depreciation.

    Formula: Carrying_Amount * Rate * (Days_Held / Period_Days)
    """
    if carrying_amount <= 0 or rate <= 0:
        return Decimal("0.0000")
    annual = carrying_amount * rate
    depreciation = (annual * Decimal(days_held)) / Decimal(period_days)
    return min(carrying_amount, depreciation).quantize(FOUR_DP, rounding=ROUND_HALF_UP)


@dataclass
class ProposedDepreciationAdjustment:
    asset_code: str
    asset_name: str
    amount: Decimal
    currency: str
    debit_account_code: str
    debit_account_name: str
    credit_account_code: str
    credit_account_name: str
    method: str
    calculation_details: dict[str, Any]
    source_ref: dict[str, Any]


def calculate_asset_depreciation(
    asset_rows: list[dict[str, Any]],
    period_start: date,
    period_end: date,
    currency: str = "PKR",
) -> list[ProposedDepreciationAdjustment]:
    """Inspects asset register rows and proposes depreciation adjustments.

    Expects asset rows with normalized roles:
    cost, net_book_value / carrying_amount, depreciation_rate, useful_life,
    asset_code, description, acquisition_date.
    """
    results: list[ProposedDepreciationAdjustment] = []
    total_period_days = (period_end - period_start).days + 1
    if total_period_days <= 0:
        total_period_days = 365

    for row in asset_rows:
        cost = _to_dec(row.get("cost") or row.get("original_cost") or row.get("amount"))
        nbv = _to_dec(row.get("net_book_value") or row.get("carrying_amount") or cost)
        rate = _to_dec(row.get("depreciation_rate") or row.get("rate"))
        useful_life = _to_dec(row.get("useful_life") or row.get("life_years"))
        asset_code = str(row.get("asset_code") or row.get("reference") or "FA-UNKNOWN").strip()
        asset_name = str(row.get("description") or row.get("name") or "Fixed Asset").strip()

        # Skip already fully written off assets
        if nbv <= 0:
            continue

        method = "straight_line"
        dep_amount = Decimal("0")
        details: dict[str, Any] = {}

        if rate > 0:
            # If percentage given (e.g. 10 or 0.10)
            if rate > Decimal("1.0"):
                rate = rate / Decimal("100")
            method = "reducing_balance"
            dep_amount = calculate_reducing_balance_depreciation(
                carrying_amount=nbv,
                rate=rate,
                days_held=total_period_days,
                period_days=365,
            )
            details = {
                "method": "reducing_balance",
                "carrying_amount": str(nbv),
                "rate": str(rate),
                "days_held": total_period_days,
                "formula": "carrying_amount * rate * (days / 365)",
            }
        elif useful_life > 0:
            method = "straight_line"
            dep_amount = calculate_straight_line_depreciation(
                cost=cost,
                salvage_value=Decimal("0"),
                useful_life_years=useful_life,
                days_held=total_period_days,
                period_days=365,
            )
            details = {
                "method": "straight_line",
                "cost": str(cost),
                "useful_life_years": str(useful_life),
                "days_held": total_period_days,
                "formula": "(cost / useful_life) * (days / 365)",
            }
        else:
            # Default fallback: 10% straight line assumption flagged in calculation details
            rate = Decimal("0.10")
            method = "straight_line_default_10pct"
            dep_amount = calculate_reducing_balance_depreciation(
                carrying_amount=cost,
                rate=rate,
                days_held=total_period_days,
                period_days=365,
            )
            details = {
                "method": "straight_line_default_10pct",
                "assumed_rate": "0.10",
                "cost": str(cost),
                "formula": "cost * 0.10 * (days / 365)",
            }

        # Do not depreciate more than remaining NBV
        dep_amount = min(dep_amount, nbv)
        if dep_amount <= 0:
            continue

        results.append(
            ProposedDepreciationAdjustment(
                asset_code=asset_code,
                asset_name=asset_name,
                amount=dep_amount,
                currency=currency,
                debit_account_code="6010",
                debit_account_name="Depreciation Expense",
                credit_account_code="1590",
                credit_account_name="Accumulated Depreciation",
                method=method,
                calculation_details=details,
                source_ref={
                    "table_id": row.get("_table_id"),
                    "document_id": row.get("_document_id"),
                    "row_index": row.get("_row_index"),
                    "asset_code": asset_code,
                },
            )
        )

    return results
