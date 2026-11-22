"""Agent 2: Tax Data & Reconciliation Agent.

Responsibilities:
- Retrieves approved accounting outputs from the Central Shared Data Layer when available.
- Accepts independently uploaded client accounting records (TB/GL excel, sales/purchase schedules)
  when Accounting has not been completed.
- Maps TB/GL exports and schedules to tax workpaper categories.
- Extracts sales, purchases, payroll, assets, expenses, imports/exports, withholding certificates,
  and tax payments.
- Reconciles amounts across source schedules, accounting outputs, and filings.
- Generates:
  * Tax Data Pack
  * Book-to-Tax Mapping workpaper
  * Withholding Tax Reconciliation workpaper
  * Sales & Turnover Reconciliation workpaper
  * Advance Tax Schedule workpaper
  * Exceptions list with source references
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tax_data_agent.mapper import build_tax_workpaper_mapping
from app.agents.tax_data_agent.reconciler import (
    reconcile_advance_tax,
    reconcile_sales_and_turnover,
    reconcile_withholding_taxes,
)
from app.api.deps import Principal
from app.models.extraction import ExtractedRow, ExtractedTable
from app.models.shared_data import ApprovedModuleOutput
from app.models.taxation import TaxEngagement, TaxWorkpaper
from app.services.shared_data import get_latest_approved_accounting_output

logger = logging.getLogger("app.agents.tax_data")


class TaxDataAgent:
    """Agent 2: Tax Data & Reconciliation Agent."""

    async def execute_data_and_reconciliation(
        self,
        session: AsyncSession,
        *,
        engagement_id: uuid.UUID,
        principal: Principal,
        source_origin_preference: str = "approved_accounting",
        version: int | None = None,
        direct_accounting_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Runs mapping and reconciliations for the engagement."""
        engagement = await session.get(TaxEngagement, engagement_id)
        if not engagement:
            raise ValueError(f"TaxEngagement {engagement_id} not found.")

        source_origin = source_origin_preference
        accounting_version: int | None = None
        accounting_payload: dict[str, Any] = {}

        # 1. Mode A: Check Central Shared Data Layer for approved accounting output
        if source_origin_preference == "approved_accounting":
            shared_out = await get_latest_approved_accounting_output(
                session,
                principal,
                client_id=engagement.client_id,
                period_id=engagement.period_id,
                version=version,
            )
            if shared_out and shared_out.status == "approved":
                source_origin = "approved_accounting"
                accounting_version = shared_out.version
                accounting_payload = shared_out.data
                logger.info(
                    "TaxDataAgent: consuming approved accounting output v%d for client %s",
                    accounting_version,
                    engagement.client_id,
                )
            else:
                # Fallback to direct client records if no approved output found
                source_origin = "client_tax_records"
                logger.info(
                    "TaxDataAgent: no approved accounting output found; using direct client records."
                )

        # 2. Mode B: Direct client records
        if source_origin == "client_tax_records":
            if direct_accounting_data:
                accounting_payload = direct_accounting_data
            else:
                # Query extracted tables from intake for this period
                tbls_res = await session.scalars(
                    select(ExtractedTable).where(
                        ExtractedTable.firm_id == engagement.firm_id,
                        ExtractedTable.client_id == engagement.client_id,
                        ExtractedTable.period_id == engagement.period_id,
                    )
                )
                tbls = list(tbls_res.all())
                accounts_extracted: list[dict[str, Any]] = []
                for tbl in tbls:
                    rows_res = await session.scalars(
                        select(ExtractedRow).where(ExtractedRow.table_id == tbl.id)
                    )
                    for r in rows_res.all():
                        raw = r.raw_data or {}
                        accounts_extracted.append({
                            "account_name": raw.get("account_name") or raw.get("description") or raw.get("account", ""),
                            "account_code": raw.get("account_code") or raw.get("code", ""),
                            "category": raw.get("category", ""),
                            "balance": float(raw.get("balance") or raw.get("amount") or raw.get("net", 0.0)),
                            "source_reference": f"Table:{tbl.id}:Row:{r.row_index}",
                        })
                accounting_payload = {"trial_balance": {"accounts": accounts_extracted}}

        # 3. Build Book-to-Tax Mapping Workpaper
        tb_data = accounting_payload.get("trial_balance", {})
        accounts_list = tb_data.get("accounts", []) or tb_data.get("lines", [])

        # If empty but we have profit_loss, build synthetic lines from P&L
        if not accounts_list and "profit_loss" in accounting_payload:
            pl = accounting_payload["profit_loss"]
            accounts_list = [
                {"account_name": "Sales Revenue", "category": "revenue", "balance": pl.get("total_revenue", 0.0)},
                {"account_name": "Cost of Goods Sold", "category": "expense", "balance": pl.get("cost_of_goods_sold", 0.0)},
                {"account_name": "Depreciation Expense", "category": "expense", "balance": pl.get("depreciation", 0.0)},
                {"account_name": "Administrative Salaries", "category": "expense", "balance": pl.get("salaries", 0.0)},
                {"account_name": "Operating Expenses", "category": "expense", "balance": pl.get("operating_expenses", 0.0)},
            ]

        mapping_result = build_tax_workpaper_mapping(accounts_list, source_origin=source_origin)

        # 4. Perform Reconciliations
        wht_certs = accounting_payload.get("withholding_certificates", [])
        wht_cprs = accounting_payload.get("wht_challans", [])
        wht_rec = reconcile_withholding_taxes(
            wht_ledger_balance=float(accounting_payload.get("wht_receivable", 0.0) or tb_data.get("wht_balance", 0.0)),
            certificates=wht_certs,
            cprs=wht_cprs,
        )

        turnover = mapping_result["category_totals"].get("turnover_sales", 0.0) or float(
            accounting_payload.get("profit_loss", {}).get("total_revenue", 0.0)
        )
        sales_returns = accounting_payload.get("sales_tax_returns", [])
        sales_rec = reconcile_sales_and_turnover(
            accounting_turnover=turnover,
            sales_tax_returns=sales_returns,
        )

        s147_cprs = accounting_payload.get("advance_tax_cprs", [])
        advance_rec = reconcile_advance_tax(
            advance_tax_ledger=float(accounting_payload.get("advance_tax_ledger", 0.0)),
            s147_cprs=s147_cprs,
        )

        all_exceptions = (
            wht_rec.get("exceptions", [])
            + sales_rec.get("exceptions", [])
            + advance_rec.get("exceptions", [])
        )

        # 5. Persist TaxWorkpaper records
        # Clean previous workpapers for this engagement
        old_wp = await session.scalars(
            select(TaxWorkpaper).where(TaxWorkpaper.engagement_id == engagement_id)
        )
        for wp in old_wp.all():
            await session.delete(wp)

        # Create Workpaper 1: Book-to-Tax Mapping
        wp_mapping = TaxWorkpaper(
            firm_id=engagement.firm_id,
            client_id=engagement.client_id,
            engagement_id=engagement.id,
            workpaper_type="book_to_tax_mapping",
            source_origin=source_origin,
            accounting_output_version=accounting_version,
            data=mapping_result,
            exceptions=[],
            status="verified",
        )
        session.add(wp_mapping)

        # Create Workpaper 2: Withholding Reconciliation
        wp_wht = TaxWorkpaper(
            firm_id=engagement.firm_id,
            client_id=engagement.client_id,
            engagement_id=engagement.id,
            workpaper_type="withholding_reconciliation",
            source_origin=source_origin,
            accounting_output_version=accounting_version,
            data=wht_rec,
            exceptions=wht_rec.get("exceptions", []),
            status="reconciled" if wht_rec.get("is_reconciled") else "discrepancy",
        )
        session.add(wp_wht)

        # Create Workpaper 3: Sales Tax Reconciliation
        wp_sales = TaxWorkpaper(
            firm_id=engagement.firm_id,
            client_id=engagement.client_id,
            engagement_id=engagement.id,
            workpaper_type="sales_tax_reconciliation",
            source_origin=source_origin,
            accounting_output_version=accounting_version,
            data=sales_rec,
            exceptions=sales_rec.get("exceptions", []),
            status="reconciled" if sales_rec.get("is_reconciled") else "discrepancy",
        )
        session.add(wp_sales)

        # Create Workpaper 4: Advance Tax Schedule
        wp_adv = TaxWorkpaper(
            firm_id=engagement.firm_id,
            client_id=engagement.client_id,
            engagement_id=engagement.id,
            workpaper_type="advance_tax_schedule",
            source_origin=source_origin,
            accounting_output_version=accounting_version,
            data=advance_rec,
            exceptions=advance_rec.get("exceptions", []),
            status="reconciled" if advance_rec.get("is_reconciled") else "discrepancy",
        )
        session.add(wp_adv)

        engagement.status = "reconciliation"
        await session.commit()

        return {
            "engagement_id": str(engagement_id),
            "source_origin": source_origin,
            "accounting_version": accounting_version,
            "mapping": mapping_result,
            "reconciliations": {
                "withholding": wht_rec,
                "sales_and_turnover": sales_rec,
                "advance_tax": advance_rec,
            },
            "exceptions": all_exceptions,
            "workpapers_generated": [
                "book_to_tax_mapping",
                "withholding_reconciliation",
                "sales_tax_reconciliation",
                "advance_tax_schedule",
            ],
        }
