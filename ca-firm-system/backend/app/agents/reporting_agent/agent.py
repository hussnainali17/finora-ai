"""Agent 4: Financial Reporting & Validation Agent.

CRITICAL PRODUCT RULES:
1. Never alter the original client-provided Trial Balance.
2. Apply ONLY approved adjustments. Draft, proposed, or rejected adjustments
   must NEVER appear in the Adjusted Trial Balance or financial statements.
3. If the Trial Balance is out of balance, flag the issue. Never fabricate a balancing entry.
4. All arithmetic uses deterministic Python services with Decimal.
5. The LLM is used strictly for drafting narrative summaries, never for math.
"""

from __future__ import annotations

import io
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.validation import (
    _to_dec,
    validate_financial_statements,
    validate_trial_balance,
)
from app.models import ExtractedRow, ExtractedTable
from app.models.adjustments import PeriodAdjustment
from app.models.reporting import AccountMapping, FinancialReport

logger = logging.getLogger("app.agents.reporting")


class ReportingAgent:
    """Financial Reporting & Validation Agent (Agent 4)."""

    async def generate_reporting_pack(
        self,
        session: AsyncSession,
        client_id: uuid.UUID,
        period_id: uuid.UUID,
        firm_id: uuid.UUID,
        currency: str = "PKR",
    ) -> dict[str, Any]:
        """Runs the deterministic financial reporting pipeline:

        Original TB -> + Approved Adjustments -> Adjusted TB -> Statements -> Validation -> Excel.
        """
        logger.info(
            "reporting agent starting",
            extra={"client_id": str(client_id), "period_id": str(period_id)},
        )

        # 1. Fetch original Trial Balance extracted tables
        tb_tables_res = await session.execute(
            select(ExtractedTable).where(
                ExtractedTable.firm_id == firm_id,
                ExtractedTable.client_id == client_id,
                ExtractedTable.period_id == period_id,
                ExtractedTable.detected_type.in_(["trial_balance", "tb"]),
            )
        )
        tb_tables = list(tb_tables_res.scalars().all())

        original_tb_rows: list[dict[str, Any]] = []
        for t in tb_tables:
            rows_res = await session.execute(
                select(ExtractedRow).where(ExtractedRow.table_id == t.id)
            )
            for r in rows_res.scalars().all():
                norm = r.normalized or {}
                account_code = str(norm.get("account_code") or norm.get("code") or norm.get("reference") or "").strip()
                account_name = str(norm.get("account_name") or norm.get("description") or norm.get("name") or "Account").strip()
                debit = _to_dec(norm.get("debit") or (norm.get("amount") if norm.get("is_debit") else 0))
                credit = _to_dec(norm.get("credit") or (norm.get("amount") if not norm.get("is_debit") and norm.get("amount") else 0))

                if account_code or account_name:
                    original_tb_rows.append(
                        {
                            "account_code": account_code or f"ACC-{r.row_index}",
                            "account_name": account_name,
                            "debit": debit,
                            "credit": credit,
                            "_row_index": r.row_index,
                        }
                    )

        # Validate original TB without changing it
        tb_balanced, orig_debit_sum, orig_credit_sum, orig_tb_issues = validate_trial_balance(original_tb_rows)

        # 2. Fetch ONLY APPROVED adjustments
        adj_res = await session.execute(
            select(PeriodAdjustment).where(
                PeriodAdjustment.firm_id == firm_id,
                PeriodAdjustment.client_id == client_id,
                PeriodAdjustment.period_id == period_id,
                PeriodAdjustment.status == "approved",
            )
        )
        approved_adjustments = list(adj_res.scalars().all())

        # 3. Calculate Adjusted Trial Balance
        # Aggregate account balances
        accounts_map: dict[str, dict[str, Any]] = {}

        for r in original_tb_rows:
            code = r["account_code"]
            if code not in accounts_map:
                accounts_map[code] = {
                    "account_code": code,
                    "account_name": r["account_name"],
                    "orig_debit": r["debit"],
                    "orig_credit": r["credit"],
                    "adj_debit": Decimal("0"),
                    "adj_credit": Decimal("0"),
                    "final_debit": Decimal("0"),
                    "final_credit": Decimal("0"),
                }
            else:
                accounts_map[code]["orig_debit"] += r["debit"]
                accounts_map[code]["orig_credit"] += r["credit"]

        # Apply approved adjustments only
        for adj in approved_adjustments:
            d_code = adj.debit_account_code
            c_code = adj.credit_account_code
            if d_code not in accounts_map:
                accounts_map[d_code] = {
                    "account_code": d_code,
                    "account_name": adj.debit_account_name,
                    "orig_debit": Decimal("0"),
                    "orig_credit": Decimal("0"),
                    "adj_debit": Decimal("0"),
                    "adj_credit": Decimal("0"),
                    "final_debit": Decimal("0"),
                    "final_credit": Decimal("0"),
                }
            if c_code not in accounts_map:
                accounts_map[c_code] = {
                    "account_code": c_code,
                    "account_name": adj.credit_account_name,
                    "orig_debit": Decimal("0"),
                    "orig_credit": Decimal("0"),
                    "adj_debit": Decimal("0"),
                    "adj_credit": Decimal("0"),
                    "final_debit": Decimal("0"),
                    "final_credit": Decimal("0"),
                }

            accounts_map[d_code]["adj_debit"] += adj.amount
            accounts_map[c_code]["adj_credit"] += adj.amount

        # Compute net final debits / credits per account
        adjusted_tb_rows: list[dict[str, Any]] = []
        tot_adj_debit = Decimal("0")
        tot_adj_credit = Decimal("0")

        for acc in accounts_map.values():
            net_debit = acc["orig_debit"] + acc["adj_debit"]
            net_credit = acc["orig_credit"] + acc["adj_credit"]
            if net_debit >= net_credit:
                acc["final_debit"] = net_debit - net_credit
                acc["final_credit"] = Decimal("0")
            else:
                acc["final_debit"] = Decimal("0")
                acc["final_credit"] = net_credit - net_debit

            tot_adj_debit += acc["final_debit"]
            tot_adj_credit += acc["final_credit"]

            adjusted_tb_rows.append(
                {
                    "account_code": acc["account_code"],
                    "account_name": acc["account_name"],
                    "original_debit": str(acc["orig_debit"]),
                    "original_credit": str(acc["orig_credit"]),
                    "adjustment_debit": str(acc["adj_debit"]),
                    "adjustment_credit": str(acc["adj_credit"]),
                    "final_debit": str(acc["final_debit"]),
                    "final_credit": str(acc["final_credit"]),
                }
            )

        # 4. Financial Statements Generation (P&L and Balance Sheet)
        pl_data, bs_data, cf_data = self._generate_statements(accounts_map, currency)

        # 5. Validation Gate
        validation_report = validate_financial_statements(
            tb_rows=[{"debit": a["final_debit"], "credit": a["final_credit"]} for a in accounts_map.values()],
            bs_data=bs_data,
            pl_data=pl_data,
            cash_flow_data=cf_data,
        )

        # 6. Build Excel representation
        excel_bytes = self._build_excel_pack(
            client_id=client_id,
            period_id=period_id,
            currency=currency,
            adjusted_tb_rows=adjusted_tb_rows,
            pl_data=pl_data,
            bs_data=bs_data,
            validation=validation_report.to_dict(),
        )

        # 7. Persist FinancialReport records in PostgreSQL
        report_pkg = {
            "currency": currency,
            "original_tb_summary": {
                "balanced": tb_balanced,
                "total_debit": str(orig_debit_sum),
                "total_credit": str(orig_credit_sum),
            },
            "adjusted_tb": {
                "total_debit": str(tot_adj_debit),
                "total_credit": str(tot_adj_credit),
                "balanced": abs(tot_adj_debit - tot_adj_credit) < Decimal("0.01"),
                "rows": adjusted_tb_rows,
            },
            "profit_and_loss": pl_data,
            "balance_sheet": bs_data,
            "cash_flow": cf_data,
        }

        # Save Adjusted TB Report
        tb_report = FinancialReport(
            firm_id=firm_id,
            client_id=client_id,
            period_id=period_id,
            report_type="adjusted_trial_balance",
            status="draft",
            version=1,
            data=report_pkg["adjusted_tb"],
            validation_results=validation_report.to_dict(),
        )
        session.add(tb_report)

        # Save Full Pack Report
        pack_report = FinancialReport(
            firm_id=firm_id,
            client_id=client_id,
            period_id=period_id,
            report_type="full_pack",
            status="draft",
            version=1,
            data=report_pkg,
            validation_results=validation_report.to_dict(),
        )
        session.add(pack_report)

        await session.commit()
        await session.refresh(pack_report)

        logger.info(
            "reporting pack generated",
            extra={"report_id": str(pack_report.id), "valid": validation_report.is_valid},
        )
        return {
            "report_id": str(pack_report.id),
            "validation": validation_report.to_dict(),
            "data": report_pkg,
        }

    def _generate_statements(
        self,
        accounts_map: dict[str, dict[str, Any]],
        currency: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Maps account codes by standard accounting prefixes:

        1xxx: Assets
        2xxx: Liabilities
        3xxx: Equity
        4xxx: Revenue
        5xxx: Cost of Goods Sold
        6xxx/7xxx: Operating Expenses
        """
        revenue = Decimal("0")
        cogs = Decimal("0")
        opex = Decimal("0")
        revenue_lines = []
        cogs_lines = []
        opex_lines = []

        current_assets = Decimal("0")
        non_current_assets = Decimal("0")
        current_liab = Decimal("0")
        non_current_liab = Decimal("0")
        equity = Decimal("0")
        cash_and_cash_equiv = Decimal("0")

        ca_lines = []
        nca_lines = []
        cl_lines = []
        ncl_lines = []
        equity_lines = []

        for acc in accounts_map.values():
            code = acc["account_code"]
            name = acc["account_name"]
            net_bal = acc["final_debit"] - acc["final_credit"]  # positive if debit, negative if credit

            # Profit & Loss
            if code.startswith("4") or any(k in name.lower() for k in ("revenue", "sales", "income")):
                # Revenue is naturally credit balance
                amt = acc["final_credit"] if acc["final_credit"] > 0 else -net_bal
                revenue += amt
                revenue_lines.append({"code": code, "name": name, "amount": str(amt)})
            elif code.startswith("5") or any(k in name.lower() for k in ("cogs", "cost of sales", "direct cost")):
                amt = acc["final_debit"] if acc["final_debit"] > 0 else net_bal
                cogs += amt
                cogs_lines.append({"code": code, "name": name, "amount": str(amt)})
            elif code.startswith(("6", "7")) or any(k in name.lower() for k in ("expense", "salary", "depreciation", "rent")):
                amt = acc["final_debit"] if acc["final_debit"] > 0 else net_bal
                opex += amt
                opex_lines.append({"code": code, "name": name, "amount": str(amt)})

            # Balance sheet
            elif code.startswith("1") or any(k in name.lower() for k in ("asset", "bank", "cash", "receivable", "inventory", "equipment")):
                amt = acc["final_debit"] if acc["final_debit"] > 0 else net_bal
                if any(k in name.lower() for k in ("cash", "bank")):
                    cash_and_cash_equiv += amt
                if any(k in name.lower() for k in ("equipment", "property", "vehicle", "fixed", "accumulated")):
                    non_current_assets += amt
                    nca_lines.append({"code": code, "name": name, "amount": str(amt)})
                else:
                    current_assets += amt
                    ca_lines.append({"code": code, "name": name, "amount": str(amt)})
            elif code.startswith("2") or any(k in name.lower() for k in ("payable", "liability", "accrued")):
                amt = acc["final_credit"] if acc["final_credit"] > 0 else -net_bal
                if any(k in name.lower() for k in ("long term", "loan", "mortgage")):
                    non_current_liab += amt
                    ncl_lines.append({"code": code, "name": name, "amount": str(amt)})
                else:
                    current_liab += amt
                    cl_lines.append({"code": code, "name": name, "amount": str(amt)})
            elif code.startswith("3") or any(k in name.lower() for k in ("capital", "equity", "retained")):
                amt = acc["final_credit"] if acc["final_credit"] > 0 else -net_bal
                equity += amt
                equity_lines.append({"code": code, "name": name, "amount": str(amt)})

        # P&L Totals
        gross_profit = revenue - cogs
        net_profit = gross_profit - opex

        pl_data = {
            "currency": currency,
            "revenue": str(revenue),
            "revenue_lines": revenue_lines,
            "cost_of_goods_sold": str(cogs),
            "cogs_lines": cogs_lines,
            "gross_profit": str(gross_profit),
            "operating_expenses": str(opex),
            "opex_lines": opex_lines,
            "net_profit": str(net_profit),
        }

        # Balance Sheet Totals
        total_assets = current_assets + non_current_assets
        # Include current period net profit in total equity
        total_equity = equity + net_profit
        total_liabilities = current_liab + non_current_liab

        bs_data = {
            "currency": currency,
            "current_assets": str(current_assets),
            "current_asset_lines": ca_lines,
            "non_current_assets": str(non_current_assets),
            "non_current_asset_lines": nca_lines,
            "total_assets": str(total_assets),
            "cash_and_cash_equivalents": str(cash_and_cash_equiv),
            "current_liabilities": str(current_liab),
            "current_liability_lines": cl_lines,
            "non_current_liabilities": str(non_current_liab),
            "non_current_liability_lines": ncl_lines,
            "total_liabilities": str(total_liabilities),
            "retained_earnings": str(equity),
            "current_year_earnings": str(net_profit),
            "total_equity": str(total_equity),
            "total_liabilities_and_equity": str(total_liabilities + total_equity),
        }

        # Simple direct Cash Flow representation
        cf_data = {
            "currency": currency,
            "cash_and_equivalents_start": "0.00",
            "net_cash_from_operating_activities": str(net_profit),
            "net_cash_from_investing_activities": "0.00",
            "net_cash_from_financing_activities": "0.00",
            "net_change_in_cash": str(net_profit),
            "cash_and_equivalents_end": str(cash_and_cash_equiv),
        }

        return pl_data, bs_data, cf_data

    def _build_excel_pack(
        self,
        client_id: uuid.UUID,
        period_id: uuid.UUID,
        currency: str,
        adjusted_tb_rows: list[dict[str, Any]],
        pl_data: dict[str, Any],
        bs_data: dict[str, Any],
        validation: dict[str, Any],
    ) -> bytes:
        """Constructs an Excel workbook with OpenPyXL containing:

        1. Adjusted Trial Balance
        2. Statement of Profit or Loss
        3. Statement of Financial Position
        4. Validation Report
        """
        wb = Workbook()
        ws_tb = wb.active
        ws_tb.title = "Adjusted Trial Balance"

        # Headers styling
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        center_align = Alignment(horizontal="center", vertical="center")
        right_align = Alignment(horizontal="right", vertical="center")

        ws_tb.append([
            "Account Code", "Account Name",
            f"Original Debit ({currency})", f"Original Credit ({currency})",
            f"Adj Debit ({currency})", f"Adj Credit ({currency})",
            f"Final Debit ({currency})", f"Final Credit ({currency})",
        ])
        for col_idx in range(1, 9):
            cell = ws_tb.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align

        for r in adjusted_tb_rows:
            ws_tb.append([
                r["account_code"], r["account_name"],
                float(r["original_debit"]), float(r["original_credit"]),
                float(r["adjustment_debit"]), float(r["adjustment_credit"]),
                float(r["final_debit"]), float(r["final_credit"]),
            ])

        # P&L sheet
        ws_pl = wb.create_sheet(title="Profit and Loss")
        ws_pl.append(["Statement of Profit or Loss", f"Currency: {currency}"])
        ws_pl.append(["Line Item", "Amount"])
        ws_pl.append(["Revenue", float(pl_data["revenue"])])
        ws_pl.append(["Cost of Goods Sold", float(pl_data["cost_of_goods_sold"])])
        ws_pl.append(["Gross Profit", float(pl_data["gross_profit"])])
        ws_pl.append(["Operating Expenses", float(pl_data["operating_expenses"])])
        ws_pl.append(["Net Profit", float(pl_data["net_profit"])])

        # Balance Sheet
        ws_bs = wb.create_sheet(title="Balance Sheet")
        ws_bs.append(["Statement of Financial Position", f"Currency: {currency}"])
        ws_bs.append(["Line Item", "Amount"])
        ws_bs.append(["Current Assets", float(bs_data["current_assets"])])
        ws_bs.append(["Non-Current Assets", float(bs_data["non_current_assets"])])
        ws_bs.append(["Total Assets", float(bs_data["total_assets"])])
        ws_bs.append(["Current Liabilities", float(bs_data["current_liabilities"])])
        ws_bs.append(["Non-Current Liabilities", float(bs_data["non_current_liabilities"])])
        ws_bs.append(["Total Liabilities", float(bs_data["total_liabilities"])])
        ws_bs.append(["Total Equity (incl. Current Year Profit)", float(bs_data["total_equity"])])
        ws_bs.append(["Total Liabilities and Equity", float(bs_data["total_liabilities_and_equity"])])

        # Validation sheet
        ws_val = wb.create_sheet(title="Validation Checks")
        ws_val.append(["Check Name", "Severity", "Description", "Discrepancy"])
        for issue in validation.get("issues", []):
            ws_val.append([
                issue.get("check_name"),
                issue.get("severity"),
                issue.get("description"),
                issue.get("difference"),
            ])

        stream = io.BytesIO()
        wb.save(stream)
        return stream.getvalue()
