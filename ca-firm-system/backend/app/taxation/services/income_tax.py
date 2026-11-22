"""Deterministic Pakistan Income Tax Calculation Service.

Enforces:
- All monetary arithmetic uses Python Decimal, ROUND_HALF_UP rounding.
- Never relies on LLM arithmetic for authoritative amounts.
- Complete step-by-step calculation trace with statutory citations.
- Minimum Tax (Section 113), Alternate Corporate Tax (Section 113C),
  and Super Tax (Section 4C) comparisons.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.taxation.rules.rates import (
    CORPORATE_TAX_RATE_TY2025,
    MINIMUM_TAX_RATE_DEFAULT,
    ACT_TAX_RATE,
    resolve_rule_set,
    resolve_super_tax_rate,
)

TWO_PLACES = Decimal("0.01")


def _d(val: Any) -> Decimal:
    """Converts int/float/str to Decimal safely."""
    if val is None or val == "":
        return Decimal("0.00")
    return Decimal(str(val))


def _round(val: Decimal) -> Decimal:
    return val.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def compute_pakistan_income_tax(
    *,
    accounting_profit_before_tax: Decimal | float | int,
    turnover: Decimal | float | int,
    tax_year: int = 2025,
    legal_form: str = "private_company",
    inadmissible_additions: list[dict[str, Any]] | None = None,
    admissible_deductions: list[dict[str, Any]] | None = None,
    tax_credits: list[dict[str, Any]] | None = None,
    withholding_taxes_paid: list[dict[str, Any]] | None = None,
    advance_tax_paid: Decimal | float | int = Decimal("0"),
) -> dict[str, Any]:
    """Computes Pakistan income tax liability deterministically."""
    trace: list[dict[str, Any]] = []

    rules = resolve_rule_set(tax_year)
    rule_version = rules["version"]

    pbt = _round(_d(accounting_profit_before_tax))
    gross_turnover = _round(_d(turnover))
    adv_tax = _round(_d(advance_tax_paid))

    trace.append({
        "step": 1,
        "title": "Accounting Profit Before Tax",
        "value": float(pbt),
        "citation": "Audited Financial Statements / P&L (IAS 1)",
        "explanation": "Starting point for book-to-tax reconciliation.",
    })

    # Step 2: Inadmissible Additions
    additions_list = inadmissible_additions or []
    total_additions = Decimal("0.00")
    detailed_additions: list[dict[str, Any]] = []

    for item in additions_list:
        amt = _round(_d(item.get("amount", 0)))
        desc = item.get("description", "Inadmissible Item")
        cit = item.get("citation", "Section 21")
        total_additions += amt
        detailed_additions.append({
            "description": desc,
            "amount": float(amt),
            "citation": cit,
        })

    trace.append({
        "step": 2,
        "title": "Add: Inadmissible Expenses / Non-Deductible Add-backs",
        "value": float(total_additions),
        "items": detailed_additions,
        "citation": "Income Tax Ordinance 2001, Section 21 & Section 34(5)",
        "explanation": "Accounting depreciation, penalties, cash payments exceeding limit, and unpaid liabilities.",
    })

    # Step 3: Admissible Deductions
    deductions_list = admissible_deductions or []
    total_deductions = Decimal("0.00")
    detailed_deductions: list[dict[str, Any]] = []

    for item in deductions_list:
        amt = _round(_d(item.get("amount", 0)))
        desc = item.get("description", "Admissible Deduction")
        cit = item.get("citation", "Section 22")
        total_deductions += amt
        detailed_deductions.append({
            "description": desc,
            "amount": float(amt),
            "citation": cit,
        })

    trace.append({
        "step": 3,
        "title": "Less: Admissible Deductions & Tax Depreciation",
        "value": float(total_deductions),
        "items": detailed_deductions,
        "citation": "Income Tax Ordinance 2001, Section 22 & Third Schedule",
        "explanation": "Statutory tax depreciation allowance and admissible expenses.",
    })

    # Step 4: Taxable Income
    taxable_income = _round(pbt + total_additions - total_deductions)
    if taxable_income < Decimal("0.00"):
        taxable_income = Decimal("0.00")  # Assessed loss

    trace.append({
        "step": 4,
        "title": "Taxable Income (Normal Tax Regime)",
        "value": float(taxable_income),
        "formula": "PBT + Inadmissible Additions - Admissible Deductions",
        "citation": "Income Tax Ordinance 2001, Section 9 & Section 18",
        "explanation": "Net income chargeable to tax under the head Income from Business.",
    })

    # Step 5: Normal Tax Calculation
    corp_rate = rules["corporate_rate"]
    normal_tax = _round(taxable_income * corp_rate)

    trace.append({
        "step": 5,
        "title": "Normal Tax Liability",
        "value": float(normal_tax),
        "rate": f"{float(corp_rate) * 100:.1f}%",
        "formula": f"Taxable Income ({float(taxable_income):,.2f}) x {float(corp_rate) * 100:.1f}%",
        "citation": "First Schedule, Division II (Corporate Tax Rate 29%)",
        "explanation": "Tax computed under standard rates.",
    })

    # Step 6: Super Tax under Section 4C
    super_tax_rate, super_citation = resolve_super_tax_rate(taxable_income, tax_year)
    super_tax = _round(taxable_income * super_tax_rate)

    trace.append({
        "step": 6,
        "title": "Super Tax under Section 4C",
        "value": float(super_tax),
        "rate": f"{float(super_tax_rate) * 100:.1f}%",
        "citation": super_citation,
        "explanation": "Super tax on high-earning individuals, AOPs, and companies.",
    })

    combined_normal_and_super = _round(normal_tax + super_tax)

    # Step 7: Minimum Tax under Section 113
    min_tax_rate = rules["minimum_tax_rate"]
    minimum_tax_113 = _round(gross_turnover * min_tax_rate)

    trace.append({
        "step": 7,
        "title": "Minimum Tax on Turnover (Section 113)",
        "value": float(minimum_tax_113),
        "rate": f"{float(min_tax_rate) * 100:.2f}%",
        "turnover": float(gross_turnover),
        "citation": "Income Tax Ordinance 2001, Section 113 (1.25% of gross turnover)",
        "explanation": "Minimum threshold based on declared sales/turnover.",
    })

    # Step 8: Alternate Corporate Tax (ACT) under Section 113C
    act_rate = rules["act_rate"]
    accounting_profit_for_act = pbt if pbt > Decimal("0") else Decimal("0")
    alternate_corporate_tax_113c = _round(accounting_profit_for_act * act_rate)

    trace.append({
        "step": 8,
        "title": "Alternate Corporate Tax (Section 113C)",
        "value": float(alternate_corporate_tax_113c),
        "rate": f"{float(act_rate) * 100:.1f}%",
        "accounting_profit": float(accounting_profit_for_act),
        "citation": "Income Tax Ordinance 2001, Section 113C (17% of accounting profit)",
        "explanation": "ACT comparison for resident corporate taxpayers.",
    })

    # Step 9: Highest Liability Determination
    regime_applied = "normal_and_super"
    gross_tax_liability = combined_normal_and_super

    if minimum_tax_113 > gross_tax_liability and minimum_tax_113 >= alternate_corporate_tax_113c:
        gross_tax_liability = minimum_tax_113
        regime_applied = "minimum_tax_113"
    elif alternate_corporate_tax_113c > gross_tax_liability and alternate_corporate_tax_113c > minimum_tax_113:
        gross_tax_liability = alternate_corporate_tax_113c
        regime_applied = "alternate_corporate_tax_113c"

    trace.append({
        "step": 9,
        "title": "Gross Tax Liability (Benchmark Comparison)",
        "value": float(gross_tax_liability),
        "regime_applied": regime_applied,
        "formula": "max(Normal + Super Tax, Minimum Tax s.113, ACT s.113C)",
        "citation": "Sections 4C, 113, 113C Benchmarking Rule",
        "explanation": f"Highest benchmark applies: {regime_applied.replace('_', ' ').title()}.",
    })

    # Step 10: Tax Credits
    credits_list = tax_credits or []
    total_credits = Decimal("0.00")
    for cr in credits_list:
        total_credits += _round(_d(cr.get("amount", 0)))

    # Step 11: Withholding Tax Credits & Advance Tax
    wht_list = withholding_taxes_paid or []
    total_wht = Decimal("0.00")
    for w in wht_list:
        total_wht += _round(_d(w.get("amount", 0)))

    total_tax_paid = _round(total_wht + adv_tax)

    # Net Tax Payable / Refundable
    net_tax_payable = _round(gross_tax_liability - total_credits - total_tax_paid)

    trace.append({
        "step": 10,
        "title": "Net Tax Payable / (Refundable)",
        "value": float(net_tax_payable),
        "gross_liability": float(gross_tax_liability),
        "tax_credits": float(total_credits),
        "withholding_taxes": float(total_wht),
        "advance_tax": float(adv_tax),
        "formula": "Gross Tax Liability - Tax Credits - (Withholding Taxes + Advance Tax Paid)",
        "citation": "Income Tax Ordinance 2001, Sections 137, 147, 168",
        "explanation": "Final balance payable or refundable on filing of tax return.",
    })

    return {
        "rule_set_version": rule_version,
        "tax_year": tax_year,
        "legal_form": legal_form,
        "accounting_profit_before_tax": float(pbt),
        "turnover": float(gross_turnover),
        "inadmissible_additions": detailed_additions,
        "total_additions": float(total_additions),
        "admissible_deductions": detailed_deductions,
        "total_deductions": float(total_deductions),
        "taxable_income": float(taxable_income),
        "normal_tax": float(normal_tax),
        "super_tax_4c": float(super_tax),
        "minimum_tax_113": float(minimum_tax_113),
        "alternate_corporate_tax_113c": float(alternate_corporate_tax_113c),
        "regime_applied": regime_applied,
        "gross_tax_liability": float(gross_tax_liability),
        "tax_credits": float(total_credits),
        "withholding_taxes_paid": float(total_wht),
        "advance_tax_paid": float(adv_tax),
        "total_advance_and_wht_paid": float(total_tax_paid),
        "net_tax_payable": float(net_tax_payable),
        "calculation_trace": trace,
    }
