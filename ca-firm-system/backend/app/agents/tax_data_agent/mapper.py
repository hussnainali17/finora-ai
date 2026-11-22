"""Book-to-tax workpaper category mapping engine.

Maps client-provided trial balance / general ledger line items and account categories
into Pakistan statutory tax categories:
- Sales & Operating Revenue (Turnover for Section 113)
- Cost of Sales / Direct Expenses
- Payroll & Staff Salaries (Section 149 scrutiny)
- Fixed Assets & Additions (Section 22 / Third Schedule)
- Accounting Depreciation & Amortization (Inadmissible s. 22)
- Selling & Administrative Expenses
- Penalties, Fines & Statutory Breaches (Inadmissible s. 21(g))
- Finance & Mark-up Costs
- Other Income / Capital Receipts
"""

from __future__ import annotations

from typing import Any

# Standard Pakistan Tax Workpaper Heads
TAX_HEAD_REVENUE = "turnover_sales"
TAX_HEAD_COST_OF_SALES = "cost_of_sales"
TAX_HEAD_PAYROLL = "payroll_salaries"
TAX_HEAD_FIXED_ASSETS = "fixed_assets_additions"
TAX_HEAD_DEPRECIATION = "accounting_depreciation"
TAX_HEAD_ADMIN_SELLING = "admin_selling_expenses"
TAX_HEAD_PENALTIES = "inadmissible_penalties"
TAX_HEAD_FINANCE_COST = "finance_costs"
TAX_HEAD_OTHER_INCOME = "other_income"
TAX_HEAD_CASH_EXPENSES = "inadmissible_cash_expenses"


def map_account_to_tax_head(account_name: str, category: str = "", code: str = "") -> str:
    """Classifies an accounting account into a tax workpaper head."""
    text = f"{account_name} {category} {code}".lower()

    if any(kw in text for kw in ("penalty", "penalties", "fine", "fines", "violation")):
        return TAX_HEAD_PENALTIES
    if any(kw in text for kw in ("depreciation", "amortisation", "amortization")):
        return TAX_HEAD_DEPRECIATION
    if any(kw in text for kw in ("salary", "salaries", "payroll", "wage", "wages", "staff cost", "remuneration")):
        return TAX_HEAD_PAYROLL
    if any(kw in text for kw in ("sales", "revenue", "turnover", "fee", "income from operation", "gross receipts")):
        return TAX_HEAD_REVENUE
    if any(kw in text for kw in ("cost of sales", "cost of goods", "purchases", "direct cost", "raw material", "cogs")):
        return TAX_HEAD_COST_OF_SALES
    if any(kw in text for kw in ("plant", "machinery", "equipment", "vehicle", "furniture", "building", "fixed asset")):
        return TAX_HEAD_FIXED_ASSETS
    if any(kw in text for kw in ("interest", "finance", "mark-up", "markup", "bank charges")):
        return TAX_HEAD_FINANCE_COST
    if any(kw in text for kw in ("dividend", "gain on sale", "other income", "profit on debt", "scrap sales")):
        return TAX_HEAD_OTHER_INCOME

    return TAX_HEAD_ADMIN_SELLING


def build_tax_workpaper_mapping(
    accounts_data: list[dict[str, Any]],
    source_origin: str = "approved_accounting",
) -> dict[str, Any]:
    """Builds the comprehensive book-to-tax category workpaper."""
    categorized: dict[str, list[dict[str, Any]]] = {
        TAX_HEAD_REVENUE: [],
        TAX_HEAD_COST_OF_SALES: [],
        TAX_HEAD_PAYROLL: [],
        TAX_HEAD_FIXED_ASSETS: [],
        TAX_HEAD_DEPRECIATION: [],
        TAX_HEAD_ADMIN_SELLING: [],
        TAX_HEAD_PENALTIES: [],
        TAX_HEAD_FINANCE_COST: [],
        TAX_HEAD_OTHER_INCOME: [],
    }

    totals: dict[str, float] = {k: 0.0 for k in categorized}

    for acc in accounts_data:
        acc_name = acc.get("account_name", "") or acc.get("description", "")
        acc_code = acc.get("account_code", "") or acc.get("code", "")
        category = acc.get("category", "") or acc.get("statement_type", "")
        balance = float(acc.get("balance", 0.0) or acc.get("net_amount", 0.0) or acc.get("amount", 0.0))

        head = map_account_to_tax_head(acc_name, category, acc_code)
        categorized[head].append({
            "account_code": acc_code,
            "account_name": acc_name,
            "category": category,
            "amount": balance,
            "source_reference": acc.get("source_reference", f"Acc:{acc_code or acc_name}"),
        })
        totals[head] += balance

    return {
        "source_origin": source_origin,
        "mapped_categories": categorized,
        "category_totals": totals,
    }
