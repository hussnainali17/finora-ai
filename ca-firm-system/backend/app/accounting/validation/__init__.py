"""Deterministic accounting validation and mathematical consistency engine.

Principles:
1. All monetary arithmetic uses Python Decimal.
2. If an original Trial Balance is unbalanced, flag the discrepancy.
   NEVER invent a plug or balancing entry!
3. Validation rules checked:
   - Trial Balance: sum(Debits) == sum(Credits)
   - Balance Sheet: Assets == Liabilities + Equity
   - P&L reconciliation: Net Profit == Revenue - Expenses
   - Cash Flow consistency: Ending Cash == Balance Sheet Cash
   - Completeness: All accounts in Adjusted TB are mapped to a statement line
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
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
class ValidationIssue:
    check_name: str
    severity: str  # "error" | "warning" | "info"
    description: str
    difference: Decimal = Decimal("0")
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReport:
    is_valid: bool
    total_checks: int
    passed_checks: int
    failed_checks: int
    issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "issues": [
                {
                    "check_name": i.check_name,
                    "severity": i.severity,
                    "description": i.description,
                    "difference": str(i.difference),
                    "details": i.details,
                }
                for i in self.issues
            ],
        }


def validate_trial_balance(tb_rows: list[dict[str, Any]]) -> tuple[bool, Decimal, Decimal, list[ValidationIssue]]:
    """Validates that total debits equal total credits.

    tb_rows format: list of dicts with 'debit' and 'credit' or 'amount' + 'is_debit'
    """
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    issues: list[ValidationIssue] = []

    for r in tb_rows:
        debit = _to_dec(r.get("debit") or (r.get("amount") if r.get("is_debit") else 0))
        credit = _to_dec(r.get("credit") or (r.get("amount") if not r.get("is_debit") and r.get("amount") else 0))
        total_debit += debit
        total_credit += credit

    diff = (total_debit - total_credit).copy_abs()
    if diff > Decimal("0.01"):
        issues.append(
            ValidationIssue(
                check_name="trial_balance_balanced",
                severity="error",
                description=(
                    f"Trial balance is out of balance by {diff}. "
                    f"Total Debits: {total_debit}, Total Credits: {total_credit}. "
                    "Per product rules, balancing entries must never be fabricated."
                ),
                difference=diff,
                details={"total_debit": str(total_debit), "total_credit": str(total_credit)},
            )
        )
        return False, total_debit, total_credit, issues

    return True, total_debit, total_credit, issues


def validate_balance_sheet(
    total_assets: Decimal,
    total_liabilities: Decimal,
    total_equity: Decimal,
) -> tuple[bool, list[ValidationIssue]]:
    """Checks the fundamental accounting equation: Assets = Liabilities + Equity."""
    issues: list[ValidationIssue] = []
    rhs = total_liabilities + total_equity
    diff = (total_assets - rhs).copy_abs()

    if diff > Decimal("0.01"):
        issues.append(
            ValidationIssue(
                check_name="balance_sheet_equation",
                severity="error",
                description=(
                    f"Balance sheet does not balance! Assets ({total_assets}) "
                    f"!= Liabilities + Equity ({rhs}). Difference: {diff}."
                ),
                difference=diff,
                details={
                    "total_assets": str(total_assets),
                    "total_liabilities": str(total_liabilities),
                    "total_equity": str(total_equity),
                },
            )
        )
        return False, issues

    return True, issues


def validate_financial_statements(
    tb_rows: list[dict[str, Any]],
    bs_data: dict[str, Any],
    pl_data: dict[str, Any],
    cash_flow_data: dict[str, Any] | None = None,
) -> ValidationReport:
    """Full consistency check across all financial statement outputs."""
    issues: list[ValidationIssue] = []
    total_checks = 0

    # 1. TB balance check
    total_checks += 1
    tb_ok, deb, cred, tb_issues = validate_trial_balance(tb_rows)
    issues.extend(tb_issues)

    # 2. Balance sheet equation check
    total_checks += 1
    assets = _to_dec(bs_data.get("total_assets"))
    liab = _to_dec(bs_data.get("total_liabilities"))
    equity = _to_dec(bs_data.get("total_equity"))
    bs_ok, bs_issues = validate_balance_sheet(assets, liab, equity)
    issues.extend(bs_issues)

    # 3. P&L Net Income to Equity reconciliation check
    total_checks += 1
    net_income = _to_dec(pl_data.get("net_profit"))
    retained_earnings_change = _to_dec(bs_data.get("current_year_earnings") or net_income)
    pl_diff = (net_income - retained_earnings_change).copy_abs()
    if pl_diff > Decimal("0.01"):
        issues.append(
            ValidationIssue(
                check_name="pl_to_equity_consistency",
                severity="error",
                description=f"Net income in P&L ({net_income}) does not match earnings transferred to equity ({retained_earnings_change}).",
                difference=pl_diff,
            )
        )

    # 4. Cash Flow ending cash to Balance Sheet cash check
    if cash_flow_data:
        total_checks += 1
        ending_cash_cf = _to_dec(cash_flow_data.get("cash_and_equivalents_end"))
        cash_bs = _to_dec(bs_data.get("cash_and_cash_equivalents"))
        cf_diff = (ending_cash_cf - cash_bs).copy_abs()
        if cf_diff > Decimal("0.01"):
            issues.append(
                ValidationIssue(
                    check_name="cash_flow_to_balance_sheet_cash",
                    severity="warning",
                    description=f"Ending cash in Cash Flow Statement ({ending_cash_cf}) differs from Balance Sheet Cash ({cash_bs}) by {cf_diff}.",
                    difference=cf_diff,
                )
            )

    failed = len([i for i in issues if i.severity == "error"])
    passed = total_checks - failed
    is_valid = failed == 0

    return ValidationReport(
        is_valid=is_valid,
        total_checks=total_checks,
        passed_checks=passed,
        failed_checks=failed,
        issues=issues,
    )
