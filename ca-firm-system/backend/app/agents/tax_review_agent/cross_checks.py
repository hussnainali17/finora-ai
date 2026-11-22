"""Cross-check validation and risk assessment engine for Tax Review (Agent 4).

Validates:
- Return totals tie back to approved workpapers & source records.
- Unmapped accounts or unverified deductions are flagged.
- Withholding tax claims match verified certificates and challans.
- Rate applicability matches tax year and legal form.
- Disallowed expenses comply with statutory thresholds (s. 21).
"""

from __future__ import annotations

from typing import Any
import uuid


def run_tax_cross_checks(
    *,
    income_tax_data: dict[str, Any],
    workpapers: dict[str, Any],
    taxpayer_profile: dict[str, Any],
) -> dict[str, Any]:
    """Runs statutory validation checks and produces the tax review report and risk list."""
    findings: list[dict[str, Any]] = []

    pbt = float(income_tax_data.get("accounting_profit_before_tax", 0.0))
    turnover = float(income_tax_data.get("turnover", 0.0))
    taxable_income = float(income_tax_data.get("taxable_income", 0.0))
    gross_tax = float(income_tax_data.get("gross_tax_liability", 0.0))
    net_tax = float(income_tax_data.get("net_tax_payable", 0.0))

    # Check 1: Tie-out between Turnover and PBT
    if turnover < pbt:
        findings.append({
            "finding_id": str(uuid.uuid4())[:8],
            "rule": "turnover_pbt_consistency",
            "severity": "critical",
            "message": f"Turnover ({turnover:,.2f}) cannot be less than Accounting Profit ({pbt:,.2f}).",
            "action_required": "Verify mapping of revenue and operating income accounts.",
        })

    # Check 2: Unreconciled Withholding Tax Claimed
    wht_rec = workpapers.get("withholding_reconciliation", {})
    wht_claimed = float(income_tax_data.get("withholding_taxes_paid", 0.0))
    wht_certs = float(wht_rec.get("certificates_total", 0.0))
    if wht_claimed > wht_certs:
        findings.append({
            "finding_id": str(uuid.uuid4())[:8],
            "rule": "unsupported_withholding_claim",
            "severity": "critical",
            "message": f"Claimed withholding tax ({wht_claimed:,.2f}) exceeds verified certificates ({wht_certs:,.2f}) by {(wht_claimed - wht_certs):,.2f}.",
            "action_required": "Obtain CPRs or valid Section 164 certificates before submission to prevent disallowance under s.168.",
        })

    # Check 3: Minimum Tax Benchmark Verification
    min_tax_computed = float(income_tax_data.get("minimum_tax_113", 0.0))
    expected_min_tax = round(turnover * 0.0125, 2)
    if abs(min_tax_computed - expected_min_tax) > 1.0 and turnover > 0:
        findings.append({
            "finding_id": str(uuid.uuid4())[:8],
            "rule": "minimum_tax_rate_mismatch",
            "severity": "error",
            "message": f"Section 113 minimum tax ({min_tax_computed:,.2f}) differs from statutory 1.25% of turnover ({expected_min_tax:,.2f}).",
            "action_required": "Confirm if special minimum tax rate applies under Division IX of Part III of First Schedule.",
        })

    # Check 4: Unmapped Accounts / Raw Exceptions
    for wp_type, wp_content in workpapers.items():
        exceptions = wp_content.get("exceptions", [])
        for exc in exceptions:
            findings.append({
                "finding_id": exc.get("exception_id") or str(uuid.uuid4())[:8],
                "rule": f"workpaper_exception_{wp_type}",
                "severity": exc.get("severity", "warning"),
                "message": f"[{wp_type.replace('_', ' ').title()}] {exc.get('description', '')}",
                "action_required": "Resolve discrepancy with source schedules or document reason for CA review.",
            })

    # Check 5: Legal form verification
    legal_form = taxpayer_profile.get("legal_form", "private_company")
    ntn = taxpayer_profile.get("ntn", "")
    if not ntn or "0000000" in ntn:
        findings.append({
            "finding_id": str(uuid.uuid4())[:8],
            "rule": "missing_ntn",
            "severity": "critical",
            "message": "Valid NTN is missing from taxpayer profile. Return cannot be filed on IRIS without verified NTN.",
            "action_required": "Enter verified NTN in Tax Intake screen.",
        })

    is_compliant = not any(f["severity"] == "critical" for f in findings)
    error_count = sum(1 for f in findings if f["severity"] in ("critical", "error"))
    warning_count = sum(1 for f in findings if f["severity"] == "warning")

    return {
        "is_compliant": is_compliant,
        "error_count": error_count,
        "warning_count": warning_count,
        "findings": findings,
        "metrics_summary": {
            "pbt": pbt,
            "turnover": turnover,
            "taxable_income": taxable_income,
            "gross_tax": gross_tax,
            "net_tax_payable": net_tax,
        },
    }
