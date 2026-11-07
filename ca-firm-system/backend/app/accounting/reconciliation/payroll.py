"""Payroll reconciliation module.

Checks performed:
- Gross pay ≠ net pay + total deductions (for each employee row)
- Missing employee IDs
- Negative net pay
- Payroll total vs GL/control total (if provided in a summary row)

Output:
- ``findings``: list[FindingData]
- ``schedules``: payroll summary schedule (total gross, deductions, net)
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

logger = logging.getLogger("app.accounting.payroll")

FOUR_DP = Decimal("0.0001")
ZERO = Decimal(0)
# Tolerance for float-originating payroll data (1 paisa)
TOLERANCE = Decimal("0.0100")


def _d(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v)).quantize(FOUR_DP, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def check_payroll(
    payroll_rows: list[dict[str, Any]],
    period_start: date,
    period_end: date,
    currency: str = "PKR",
    gl_total: Decimal | None = None,
) -> ReconciliationResult:
    """Run payroll checks for the given period.

    Expected row keys (normalized roles):
        - ``employee_id``: unique employee identifier
        - ``employee_name``: employee full name
        - ``gross_pay``: total gross salary / wages
        - ``net_pay``: take-home pay after deductions
        - ``total_deductions``: sum of all deductions (tax, PF, insurance, etc.)
          OR individual deduction columns that the checker will sum:
          ``tax``, ``pf``, ``eobi``, ``insurance``, ``other_deductions``

    Args:
        payroll_rows: rows from the payroll sheet.
        period_start: start of the period.
        period_end: end of the period.
        currency: ISO 4217 currency code.
        gl_total: optional GL/control total to compare against payroll net total.

    Returns:
        ReconciliationResult with findings, payroll summary schedule, and summary.
    """
    findings: list[FindingData] = []

    total_gross = ZERO
    total_net = ZERO
    total_deductions = ZERO

    for idx, row in enumerate(payroll_rows):
        emp_id = str(row.get("employee_id") or row.get("emp_id") or row.get("id") or "").strip()
        emp_name = str(row.get("employee_name") or row.get("name") or row.get("full_name") or "").strip()
        label = emp_id or emp_name or f"row_{idx}"

        gross = _d(row.get("gross_pay") or row.get("gross")) or ZERO
        net = _d(row.get("net_pay") or row.get("net")) or ZERO

        # Deductions: use explicit total if available, otherwise sum individual columns
        deductions_explicit = _d(row.get("total_deductions") or row.get("deductions"))
        if deductions_explicit is not None:
            deductions = deductions_explicit
        else:
            tax = _d(row.get("tax") or row.get("income_tax")) or ZERO
            pf = _d(row.get("pf") or row.get("provident_fund")) or ZERO
            eobi = _d(row.get("eobi")) or ZERO
            insurance = _d(row.get("insurance") or row.get("health_insurance")) or ZERO
            other = _d(row.get("other_deductions") or row.get("other")) or ZERO
            deductions = tax + pf + eobi + insurance + other

        source_ref = {"row_index": idx, "employee_id": emp_id, "employee_name": emp_name}

        # ---- Check: missing employee ID
        if not emp_id:
            findings.append(
                FindingData(
                    finding_type="missing_employee_id",
                    severity="warning",
                    title="Missing employee ID",
                    description=f"Payroll row {idx} (name: '{emp_name}') has no employee ID.",
                    source_ref=source_ref,
                )
            )

        # ---- Check: gross ≠ net + deductions
        expected_net = gross - deductions
        if abs(expected_net - net) > TOLERANCE:
            findings.append(
                FindingData(
                    finding_type="payroll_deduction_mismatch",
                    severity="error",
                    title=f"Payroll deduction mismatch: {label}",
                    description=(
                        f"Employee '{label}': gross ({gross}) - deductions ({deductions}) = "
                        f"{expected_net}, but net pay is {net}. "
                        f"Difference: {abs(expected_net - net)} {currency}."
                    ),
                    source_ref=source_ref,
                    amount=abs(expected_net - net),
                    currency=currency,
                )
            )

        # ---- Check: negative net pay
        if net < ZERO:
            findings.append(
                FindingData(
                    finding_type="negative_net_pay",
                    severity="error",
                    title=f"Negative net pay: {label}",
                    description=(
                        f"Employee '{label}' has negative net pay: {net} {currency}. "
                        "Total deductions exceed gross pay."
                    ),
                    source_ref=source_ref,
                    amount=net,
                    currency=currency,
                )
            )

        total_gross += gross
        total_net += net
        total_deductions += deductions

    # ---- Check: payroll total vs GL total
    if gl_total is not None:
        variance = abs(total_net - gl_total)
        if variance > TOLERANCE:
            findings.append(
                FindingData(
                    finding_type="payroll_gl_variance",
                    severity="error",
                    title="Payroll net total does not match GL control total",
                    description=(
                        f"Payroll net total: {total_net} {currency}. "
                        f"GL control total: {gl_total} {currency}. "
                        f"Variance: {variance} {currency}."
                    ),
                    source_ref={"note": "Compare payroll register net total against GL"},
                    amount=variance,
                    currency=currency,
                )
            )

    payroll_schedule = ScheduleData(
        schedule_type="payroll_summary",
        label="Payroll Summary Schedule",
        data={
            "currency": currency,
            "period_start": str(period_start),
            "period_end": str(period_end),
            "employee_count": len(payroll_rows),
            "total_gross": str(total_gross),
            "total_deductions": str(total_deductions),
            "total_net": str(total_net),
            "gl_total": str(gl_total) if gl_total is not None else None,
            "gl_variance": str(abs(total_net - gl_total)) if gl_total is not None else None,
        },
    )

    by_severity: dict[str, int] = defaultdict(int)
    for f in findings:
        by_severity[f.severity] += 1

    summary = {
        "total_findings": len(findings),
        "by_severity": dict(by_severity),
        "employee_count": len(payroll_rows),
        "total_gross": str(total_gross),
        "total_deductions": str(total_deductions),
        "total_net": str(total_net),
    }

    return ReconciliationResult(findings=findings, schedules=[payroll_schedule], summary=summary)
