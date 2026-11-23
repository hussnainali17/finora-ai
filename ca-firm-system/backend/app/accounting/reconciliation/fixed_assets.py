"""Fixed Assets (PPE) reconciliation module.

Checks performed:
- Assets without depreciation rates
- Fully depreciated assets still marked active
- Disposals without recorded proceeds
- Missing acquisition dates
- Assets with negative net book value

Output:
- ``findings``: list[FindingData]
- ``schedules``: PPE movement schedule (opening + additions - disposals = closing NBV)
- ``summary``: totals

All amounts use ``Decimal`` with explicit rounding to 4dp.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.accounting.reconciliation._types import FindingData, ReconciliationResult, ScheduleData, flatten_rows

logger = logging.getLogger("app.accounting.fixed_assets")

FOUR_DP = Decimal("0.0001")
ZERO = Decimal(0)


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


def check_fixed_assets(
    asset_register_rows: list[dict[str, Any]],
    period_start: date,
    period_end: date,
    currency: str = "PKR",
) -> ReconciliationResult:
    """Check fixed asset register for common issues and produce PPE movement schedule.

    Expected row keys (normalized roles):
        - ``asset_id`` / ``code``: unique asset identifier
        - ``description``: asset name/description
        - ``acquisition_date``: date of purchase
        - ``cost``: original cost
        - ``accumulated_depreciation``: total depreciation to date
        - ``net_book_value`` (or derived as cost - accum_dep)
        - ``depreciation_rate``: annual rate (0.0–1.0 or percentage)
        - ``status``: "active" | "disposed" | "fully_depreciated"
        - ``disposal_date``: date of disposal (if disposed)
        - ``disposal_proceeds``: proceeds from disposal (if disposed)
        - ``is_addition``: True if added in this period
        - ``is_disposal``: True if disposed in this period

    Args:
        asset_register_rows: rows from the fixed asset register.
        period_start: start of the period.
        period_end: end of the period.
        currency: ISO 4217 currency code.

    Returns:
        ReconciliationResult with findings, PPE movement schedule, and summary.
    """
    findings: list[FindingData] = []
    schedule_rows = []
    asset_register_rows = flatten_rows(asset_register_rows)

    opening_total = ZERO
    additions_total = ZERO
    disposals_total = ZERO
    closing_total = ZERO

    for idx, row in enumerate(asset_register_rows):
        asset_id = str(
            row.get("asset_id") or row.get("code") or row.get("asset_code") or ""
        ).strip()
        description = str(row.get("description") or row.get("name") or "").strip()
        label = asset_id or description or f"row_{idx}"

        cost = _d(row.get("cost") or row.get("original_cost")) or ZERO
        accum_dep = _d(row.get("accumulated_depreciation") or row.get("accum_dep")) or ZERO
        nbv = _d(row.get("net_book_value"))
        if nbv is None:
            nbv = cost - accum_dep

        dep_rate = _d(row.get("depreciation_rate") or row.get("dep_rate"))
        status = str(row.get("status") or "active").strip().lower()
        is_addition = str(row.get("is_addition") or "").strip().lower() in (
            "yes",
            "true",
            "1",
            "y",
        )
        is_disposal = str(row.get("is_disposal") or "").strip().lower() in (
            "yes",
            "true",
            "1",
            "y",
        )
        acq_date = _date(row.get("acquisition_date") or row.get("purchase_date"))
        disposal_date = _date(row.get("disposal_date"))
        disposal_proceeds = _d(row.get("disposal_proceeds") or row.get("proceeds"))

        source_ref = {"row_index": idx, "asset_id": asset_id}

        # ---- Check: missing acquisition date
        if acq_date is None and cost > ZERO:
            findings.append(
                FindingData(
                    finding_type="missing_acquisition_date",
                    severity="warning",
                    title=f"Missing acquisition date: {label}",
                    description=f"Asset '{label}' has cost {cost} {currency} but no acquisition date.",
                    source_ref=source_ref,
                    amount=cost,
                    currency=currency,
                )
            )

        # ---- Check: missing depreciation rate
        if dep_rate is None and cost > ZERO and status == "active":
            findings.append(
                FindingData(
                    finding_type="missing_depreciation_rate",
                    severity="error",
                    title=f"Missing depreciation rate: {label}",
                    description=(
                        f"Active asset '{label}' (cost: {cost} {currency}) has no depreciation rate. "
                        f"Depreciation cannot be calculated without a rate."
                    ),
                    source_ref=source_ref,
                    amount=cost,
                    currency=currency,
                )
            )

        # ---- Check: fully depreciated asset still active
        if status == "active" and nbv <= ZERO and cost > ZERO:
            findings.append(
                FindingData(
                    finding_type="fully_depreciated_active_asset",
                    severity="warning",
                    title=f"Fully depreciated asset still active: {label}",
                    description=(
                        f"Asset '{label}' has net book value {nbv} {currency} "
                        f"(fully depreciated) but is still marked 'active'."
                    ),
                    source_ref=source_ref,
                    amount=nbv,
                    currency=currency,
                )
            )

        # ---- Check: disposal without proceeds
        if is_disposal and disposal_proceeds is None:
            findings.append(
                FindingData(
                    finding_type="disposal_without_proceeds",
                    severity="warning",
                    title=f"Disposal with no proceeds recorded: {label}",
                    description=(
                        f"Asset '{label}' is marked as disposed "
                        f"(date: {disposal_date}) but no disposal proceeds are recorded."
                    ),
                    source_ref=source_ref,
                    amount=cost,
                    currency=currency,
                )
            )

        # ---- Check: negative net book value
        if nbv < ZERO:
            findings.append(
                FindingData(
                    finding_type="negative_net_book_value",
                    severity="error",
                    title=f"Negative net book value: {label}",
                    description=(
                        f"Asset '{label}' has net book value {nbv} {currency}, "
                        f"which is negative (accumulated depreciation exceeds cost)."
                    ),
                    source_ref=source_ref,
                    amount=nbv,
                    currency=currency,
                )
            )

        # ---- PPE movement schedule accumulation
        if is_addition:
            additions_total += cost
        elif is_disposal:
            disposals_total += cost
        else:
            opening_total += nbv

        closing_total += max(nbv, ZERO)

        schedule_rows.append(
            {
                "asset_id": asset_id,
                "description": description,
                "cost": str(cost),
                "accumulated_depreciation": str(accum_dep),
                "net_book_value": str(nbv),
                "depreciation_rate": str(dep_rate) if dep_rate is not None else None,
                "status": status,
                "is_addition": is_addition,
                "is_disposal": is_disposal,
                "acquisition_date": str(acq_date) if acq_date else None,
            }
        )

    ppe_schedule = ScheduleData(
        schedule_type="ppe_movement",
        label="Property, Plant & Equipment Movement Schedule",
        data={
            "currency": currency,
            "period_start": str(period_start),
            "period_end": str(period_end),
            "opening_nbv": str(opening_total),
            "additions": str(additions_total),
            "disposals": str(disposals_total),
            "closing_nbv": str(closing_total),
            "asset_count": len(asset_register_rows),
            "assets": schedule_rows,
        },
    )

    by_severity: dict[str, int] = defaultdict(int)
    for f in findings:
        by_severity[f.severity] += 1

    summary = {
        "total_findings": len(findings),
        "by_severity": dict(by_severity),
        "asset_count": len(asset_register_rows),
        "opening_nbv": str(opening_total),
        "additions": str(additions_total),
        "disposals": str(disposals_total),
        "closing_nbv": str(closing_total),
    }

    return ReconciliationResult(findings=findings, schedules=[ppe_schedule], summary=summary)
