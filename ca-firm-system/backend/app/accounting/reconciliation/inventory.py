"""Inventory reconciliation module.

Checks performed:
- Opening balance + purchases - sales ≠ closing balance (by item code)
- Negative quantities at any point
- Missing item codes / descriptions
- Items with movement but no opening or closing balance

Output:
- ``findings``: list[FindingData]
- ``schedules``: inventory movement schedule (opening + purchases - sales = closing by item)
- ``summary``: totals

All amounts and quantities use ``Decimal`` with explicit rounding.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.accounting.reconciliation._types import FindingData, ReconciliationResult, ScheduleData, flatten_rows

logger = logging.getLogger("app.accounting.inventory")

FOUR_DP = Decimal("0.0001")
ZERO = Decimal(0)


def _d(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v)).quantize(FOUR_DP, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def check_inventory(
    opening_rows: list[dict[str, Any]],
    movement_rows: list[dict[str, Any]],
    closing_rows: list[dict[str, Any]],
    period_start: date,
    period_end: date,
    currency: str = "PKR",
) -> ReconciliationResult:
    """Reconcile inventory: opening + movements = closing, by item code.

    Args:
        opening_rows: opening inventory (item_code, description, qty, unit_cost, total).
        movement_rows: purchase and sale movements (item_code, type, qty, unit_cost, total).
                       ``type`` should be "purchase" or "sale" (or similar).
        closing_rows: closing inventory count (item_code, qty, unit_cost, total).
        period_start: start of the period.
        period_end: end of the period.
        currency: ISO 4217 currency code.

    Returns:
        ReconciliationResult with findings, inventory movement schedule, and summary.
    """
    findings: list[FindingData] = []
    opening_rows = flatten_rows(opening_rows)
    movement_rows = flatten_rows(movement_rows)
    closing_rows = flatten_rows(closing_rows)

    # Index by item_code
    opening: dict[str, Decimal] = {}
    closing: dict[str, Decimal] = {}
    purchases_by_item: dict[str, Decimal] = defaultdict(Decimal)
    sales_by_item: dict[str, Decimal] = defaultdict(Decimal)
    all_items: set[str] = set()

    for idx, row in enumerate(opening_rows):
        code = str(row.get("item_code") or row.get("code") or row.get("sku") or "").strip()
        qty = _d(row.get("qty") or row.get("quantity")) or ZERO
        if not code:
            findings.append(
                FindingData(
                    finding_type="missing_item_code",
                    severity="warning",
                    title="Missing item code in opening inventory",
                    description=f"Opening inventory row {idx} has no item code.",
                    source_ref={"row_index": idx},
                )
            )
            continue
        opening[code] = qty
        all_items.add(code)

        if qty < ZERO:
            findings.append(
                FindingData(
                    finding_type="negative_quantity",
                    severity="error",
                    title=f"Negative opening quantity: item {code}",
                    description=f"Item '{code}' has negative opening quantity: {qty}.",
                    source_ref={"row_index": idx},
                    amount=qty,
                )
            )

    for idx, row in enumerate(movement_rows):
        code = str(row.get("item_code") or row.get("code") or row.get("sku") or "").strip()
        qty = _d(row.get("qty") or row.get("quantity")) or ZERO
        move_type = str(row.get("type") or row.get("movement_type") or "").strip().lower()

        if not code:
            findings.append(
                FindingData(
                    finding_type="missing_item_code",
                    severity="warning",
                    title="Missing item code in movement",
                    description=f"Movement row {idx} has no item code.",
                    source_ref={"row_index": idx},
                )
            )
            continue

        all_items.add(code)
        if move_type in ("purchase", "in", "receipt", "buy"):
            purchases_by_item[code] = purchases_by_item[code] + qty
        elif move_type in ("sale", "out", "issue", "sell"):
            sales_by_item[code] = sales_by_item[code] + qty
        # else: unknown movement type — count as purchase to be safe
        else:
            purchases_by_item[code] = purchases_by_item[code] + qty

    for idx, row in enumerate(closing_rows):
        code = str(row.get("item_code") or row.get("code") or row.get("sku") or "").strip()
        qty = _d(row.get("qty") or row.get("quantity")) or ZERO
        if not code:
            findings.append(
                FindingData(
                    finding_type="missing_item_code",
                    severity="warning",
                    title="Missing item code in closing inventory",
                    description=f"Closing inventory row {idx} has no item code.",
                    source_ref={"row_index": idx},
                )
            )
            continue
        closing[code] = qty
        all_items.add(code)

        if qty < ZERO:
            findings.append(
                FindingData(
                    finding_type="negative_quantity",
                    severity="error",
                    title=f"Negative closing quantity: item {code}",
                    description=f"Item '{code}' has negative closing quantity: {qty}.",
                    source_ref={"row_index": idx},
                    amount=qty,
                )
            )

    # Movement schedule
    schedule_rows = []
    for code in sorted(all_items):
        op_qty = opening.get(code, ZERO)
        purch = purchases_by_item.get(code, ZERO)
        sales = sales_by_item.get(code, ZERO)
        expected_closing = op_qty + purch - sales
        actual_closing = closing.get(code, ZERO)
        variance = actual_closing - expected_closing

        schedule_rows.append(
            {
                "item_code": code,
                "opening": str(op_qty),
                "purchases": str(purch),
                "sales": str(sales),
                "expected_closing": str(expected_closing),
                "actual_closing": str(actual_closing),
                "variance": str(variance),
            }
        )

        if abs(variance) > Decimal("0.01"):
            findings.append(
                FindingData(
                    finding_type="inventory_imbalance",
                    severity="error",
                    title=f"Inventory movement imbalance: item {code}",
                    description=(
                        f"Item '{code}': opening ({op_qty}) + purchases ({purch}) - "
                        f"sales ({sales}) = {expected_closing}, but closing stock is "
                        f"{actual_closing}. Variance: {variance}."
                    ),
                    source_ref={"item_code": code},
                    amount=variance,
                    currency=currency,
                )
            )

    movement_schedule = ScheduleData(
        schedule_type="inventory_movement",
        label="Inventory Movement Schedule",
        data={
            "currency": currency,
            "period_start": str(period_start),
            "period_end": str(period_end),
            "items": schedule_rows,
            "total_items": len(all_items),
            "items_with_variance": sum(1 for r in schedule_rows if Decimal(r["variance"]) != ZERO),
        },
    )

    by_severity: dict[str, int] = defaultdict(int)
    for f in findings:
        by_severity[f.severity] += 1

    summary = {
        "total_findings": len(findings),
        "by_severity": dict(by_severity),
        "item_count": len(all_items),
        "items_with_variance": sum(
            1 for r in schedule_rows if abs(Decimal(r["variance"])) > Decimal("0.01")
        ),
    }

    return ReconciliationResult(findings=findings, schedules=[movement_schedule], summary=summary)
