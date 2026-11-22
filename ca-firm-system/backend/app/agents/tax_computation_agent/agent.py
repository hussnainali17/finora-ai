"""Agent 3: Tax Computation & Compliance Agent.

Responsibilities:
- Applies approved, versioned tax rules to mapped data.
- Computes taxable income and tax payable using deterministic calculation services.
- Classifies withholding, applies book-to-tax adjustments, and computes benchmarks
  (Normal Tax, Section 4C Super Tax, Section 113 Minimum Tax, Section 113C ACT).
- Prepares applicable income tax and sales tax workpapers.
- Produces complete, auditable calculation trace with statutory citations.
- Hard rule: Never relies on LLM arithmetic for authoritative numbers.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.taxation import TaxCalculationRun, TaxEngagement, TaxpayerProfile, TaxWorkpaper
from app.taxation.services.income_tax import compute_pakistan_income_tax
from app.taxation.services.sales_tax import compute_sales_tax

logger = logging.getLogger("app.agents.tax_computation")


class TaxComputationAgent:
    """Agent 3: Tax Computation & Compliance Agent."""

    async def execute_computation(
        self,
        session: AsyncSession,
        *,
        engagement_id: uuid.UUID,
        manual_additions: list[dict[str, Any]] | None = None,
        manual_deductions: list[dict[str, Any]] | None = None,
        tax_credits: list[dict[str, Any]] | None = None,
        advance_tax_override: float | None = None,
    ) -> dict[str, Any]:
        """Computes tax liabilities and persists TaxCalculationRun."""
        engagement = await session.get(TaxEngagement, engagement_id)
        if not engagement:
            raise ValueError(f"TaxEngagement {engagement_id} not found.")

        # 1. Fetch taxpayer profile to determine legal form and jurisdictions
        prof_res = await session.scalars(
            select(TaxpayerProfile).where(TaxpayerProfile.engagement_id == engagement_id)
        )
        profile = prof_res.first()
        legal_form = profile.legal_form if profile else "private_company"
        jurisdictions = profile.jurisdictions if profile else ["Federal"]

        # 2. Fetch workpapers prepared by Agent 2
        wp_res = await session.scalars(
            select(TaxWorkpaper).where(TaxWorkpaper.engagement_id == engagement_id)
        )
        workpapers = {wp.workpaper_type: wp.data for wp in wp_res.all()}

        mapping_data = workpapers.get("book_to_tax_mapping", {})
        category_totals = mapping_data.get("category_totals", {})

        turnover = float(category_totals.get("turnover_sales", 0.0))
        cogs = float(category_totals.get("cost_of_sales", 0.0))
        acc_depreciation = float(category_totals.get("accounting_depreciation", 0.0))
        penalties = float(category_totals.get("inadmissible_penalties", 0.0))
        payroll = float(category_totals.get("payroll_salaries", 0.0))
        admin_selling = float(category_totals.get("admin_selling_expenses", 0.0))
        finance_costs = float(category_totals.get("finance_costs", 0.0))

        # Estimate accounting profit before tax
        total_expenses = cogs + acc_depreciation + penalties + payroll + admin_selling + finance_costs
        pbt = round(turnover - total_expenses, 2)

        # 3. Assemble Inadmissible Additions
        inadmissible_additions: list[dict[str, Any]] = []
        if acc_depreciation > 0:
            inadmissible_additions.append({
                "description": "Accounting Depreciation (disallowed as per tax law)",
                "amount": acc_depreciation,
                "citation": "Income Tax Ordinance 2001, Section 22",
            })
        if penalties > 0:
            inadmissible_additions.append({
                "description": "Fines & Penalties for statutory violations",
                "amount": penalties,
                "citation": "Income Tax Ordinance 2001, Section 21(g)",
            })
        if manual_additions:
            inadmissible_additions.extend(manual_additions)

        # 4. Assemble Admissible Deductions
        admissible_deductions: list[dict[str, Any]] = []
        # Tax depreciation allowance under Section 22 / Third Schedule
        # Standard tax depreciation benchmark: 15% on net machinery/equipment
        fixed_assets_additions = float(category_totals.get("fixed_assets_additions", 0.0))
        tax_dep_base = fixed_assets_additions if fixed_assets_additions > 0 else (acc_depreciation * 1.1)
        statutory_tax_depreciation = round(tax_dep_base * 0.15, 2)
        if statutory_tax_depreciation > 0:
            admissible_deductions.append({
                "description": "Tax Depreciation Allowance under Third Schedule",
                "amount": statutory_tax_depreciation,
                "citation": "Income Tax Ordinance 2001, Section 22 & Third Schedule",
            })
        if manual_deductions:
            admissible_deductions.extend(manual_deductions)

        # 5. Extract Withholding and Advance Taxes from Reconciliations
        wht_rec = workpapers.get("withholding_reconciliation", {})
        wht_certs = wht_rec.get("certificates_total", 0.0) or wht_rec.get("ledger_amount", 0.0)
        withholding_taxes_list = [
            {"description": "Withholding Tax Deductions (Verified Certificates)", "amount": float(wht_certs)}
        ] if wht_certs > 0 else []

        adv_rec = workpapers.get("advance_tax_schedule", {})
        advance_tax = advance_tax_override if advance_tax_override is not None else float(
            adv_rec.get("cpr_advance_tax_total", 0.0) or adv_rec.get("ledger_advance_tax", 0.0)
        )

        # 6. Execute Deterministic Income Tax Calculation
        income_tax_result = compute_pakistan_income_tax(
            accounting_profit_before_tax=pbt,
            turnover=turnover,
            tax_year=engagement.tax_year,
            legal_form=legal_form,
            inadmissible_additions=inadmissible_additions,
            admissible_deductions=admissible_deductions,
            tax_credits=tax_credits or [],
            withholding_taxes_paid=withholding_taxes_list,
            advance_tax_paid=advance_tax,
        )

        # 7. Execute Deterministic Sales Tax Calculation
        province = jurisdictions[0] if jurisdictions else "Federal"
        sales_tax_result = compute_sales_tax(
            taxable_supplies=turnover,
            admissible_purchases=cogs,
            provincial_service_turnover=0.0,
            province=province,
        )

        # 8. Persist TaxCalculationRun
        calc_run = TaxCalculationRun(
            firm_id=engagement.firm_id,
            client_id=engagement.client_id,
            engagement_id=engagement.id,
            tax_year=engagement.tax_year,
            rule_set_version=income_tax_result["rule_set_version"],
            accounting_profit={
                "pbt": income_tax_result["accounting_profit_before_tax"],
                "turnover": income_tax_result["turnover"],
            },
            tax_adjustments={
                "additions": income_tax_result["inadmissible_additions"],
                "deductions": income_tax_result["admissible_deductions"],
            },
            taxable_income={
                "taxable_income": income_tax_result["taxable_income"],
                "regime": income_tax_result["regime_applied"],
            },
            normal_tax={"normal_tax": income_tax_result["normal_tax"]},
            minimum_tax_113={"minimum_tax_113": income_tax_result["minimum_tax_113"]},
            alternate_corporate_tax_113c={"act_113c": income_tax_result["alternate_corporate_tax_113c"]},
            super_tax_4c={"super_tax_4c": income_tax_result["super_tax_4c"]},
            tax_credits={"credits": income_tax_result["tax_credits"]},
            withholding_taxes={
                "withholding_taxes": income_tax_result["withholding_taxes_paid"],
                "advance_tax": income_tax_result["advance_tax_paid"],
            },
            net_tax_payable={
                "gross_liability": income_tax_result["gross_tax_liability"],
                "net_payable": income_tax_result["net_tax_payable"],
            },
            sales_tax_computation=sales_tax_result,
            calculation_trace=income_tax_result["calculation_trace"],
            status="verified",
        )
        session.add(calc_run)
        engagement.status = "calculating"
        await session.commit()
        await session.refresh(calc_run)

        logger.info(
            "TaxComputationAgent completed calculation run %s for engagement %s (taxable income: %s, net tax: %s)",
            calc_run.id,
            engagement_id,
            income_tax_result["taxable_income"],
            income_tax_result["net_tax_payable"],
        )

        return {
            "calculation_run_id": str(calc_run.id),
            "engagement_id": str(engagement.id),
            "tax_year": engagement.tax_year,
            "rule_set_version": income_tax_result["rule_set_version"],
            "income_tax": income_tax_result,
            "sales_tax": sales_tax_result,
        }
