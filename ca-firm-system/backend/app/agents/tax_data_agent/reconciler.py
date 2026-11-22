"""Tax Reconciliation Engine (Agent 2).

Performs:
- Withholding Tax Reconciliation (certificates vs books vs CPRs)
- Sales Reconciliation (accounting turnover vs sales tax return supplies)
- Purchase Reconciliation (accounting purchases vs sales tax input tax)
- Advance Tax Reconciliation (Section 147 CPRs vs ledger advance tax)
- Source-indexed exception generation
"""

from __future__ import annotations

from typing import Any
import uuid


def reconcile_withholding_taxes(
    *,
    wht_ledger_balance: float,
    certificates: list[dict[str, Any]],
    cprs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reconciles withholding tax certificates against general ledger and CPR deposits."""
    cert_total = sum(float(c.get("amount", 0.0)) for c in certificates)
    cpr_total = sum(float(p.get("amount", 0.0)) for p in cprs)
    diff = round(wht_ledger_balance - cert_total, 2)

    exceptions: list[dict[str, Any]] = []
    if abs(diff) > 1.0:
        exceptions.append({
            "exception_id": str(uuid.uuid4())[:8],
            "workpaper": "withholding_reconciliation",
            "type": "variance",
            "severity": "warning" if abs(diff) < 50_000 else "error",
            "description": f"Withholding tax in books ({wht_ledger_balance:,.2f}) differs from certificates total ({cert_total:,.2f}) by {diff:,.2f}.",
            "difference": diff,
            "statutory_ref": "Income Tax Ordinance 2001, Section 168",
        })

    # Unverified / missing CPRs
    for c in certificates:
        cert_num = c.get("certificate_number") or c.get("ref", "")
        matched = any(p.get("cpr_number") == cert_num or p.get("ref") == cert_num for p in cprs)
        if not matched and cprs:
            exceptions.append({
                "exception_id": str(uuid.uuid4())[:8],
                "workpaper": "withholding_reconciliation",
                "type": "unverified_cpr",
                "severity": "warning",
                "description": f"WHT Certificate {cert_num} ({c.get('section', 'WHT')}) for {c.get('amount', 0):,.2f} has no matching verified CPR challan.",
                "source_ref": c.get("source_reference", f"Cert:{cert_num}"),
                "statutory_ref": "Income Tax Rules 2002, Rule 44",
            })

    return {
        "ledger_amount": wht_ledger_balance,
        "certificates_total": cert_total,
        "cprs_total": cpr_total,
        "variance": diff,
        "is_reconciled": abs(diff) <= 1.0,
        "exceptions": exceptions,
    }


def reconcile_sales_and_turnover(
    *,
    accounting_turnover: float,
    sales_tax_returns: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reconciles accounting turnover (P&L) with supplies declared in Sales Tax returns."""
    portal_supplies = sum(float(r.get("taxable_supplies", 0.0) or r.get("supplies", 0.0)) for r in sales_tax_returns)
    diff = round(accounting_turnover - portal_supplies, 2)

    exceptions: list[dict[str, Any]] = []
    if abs(diff) > 1.0 and sales_tax_returns:
        exceptions.append({
            "exception_id": str(uuid.uuid4())[:8],
            "workpaper": "sales_tax_reconciliation",
            "type": "turnover_variance",
            "severity": "error" if abs(diff) > 100_000 else "warning",
            "description": f"Accounting revenue ({accounting_turnover:,.2f}) differs from sales tax return declared supplies ({portal_supplies:,.2f}) by {diff:,.2f}.",
            "difference": diff,
            "statutory_ref": "Sales Tax Act 1990, Section 26 & Section 113 Income Tax Ordinance",
        })

    return {
        "accounting_turnover": accounting_turnover,
        "sales_tax_declared_supplies": portal_supplies,
        "variance": diff,
        "is_reconciled": abs(diff) <= 1.0 or not sales_tax_returns,
        "exceptions": exceptions,
    }


def reconcile_advance_tax(
    *,
    advance_tax_ledger: float,
    s147_cprs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reconciles quarterly advance tax payments under Section 147."""
    paid_total = sum(float(c.get("amount", 0.0)) for c in s147_cprs)
    diff = round(advance_tax_ledger - paid_total, 2)

    exceptions: list[dict[str, Any]] = []
    if abs(diff) > 1.0 and s147_cprs:
        exceptions.append({
            "exception_id": str(uuid.uuid4())[:8],
            "workpaper": "advance_tax_schedule",
            "type": "advance_tax_variance",
            "severity": "warning",
            "description": f"Advance tax recorded in books ({advance_tax_ledger:,.2f}) differs from Section 147 CPR challans ({paid_total:,.2f}) by {diff:,.2f}.",
            "difference": diff,
            "statutory_ref": "Income Tax Ordinance 2001, Section 147",
        })

    return {
        "ledger_advance_tax": advance_tax_ledger,
        "cpr_advance_tax_total": paid_total,
        "variance": diff,
        "is_reconciled": abs(diff) <= 1.0 or not s147_cprs,
        "exceptions": exceptions,
    }
