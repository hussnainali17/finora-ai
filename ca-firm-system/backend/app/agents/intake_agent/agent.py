"""Accounting Agent 1: Accounting Intake & Preparation Agent.

Refactored from the legacy file parser/OCR agent into a dedicated domain agent.
Generic OCR, document classification, and file extraction now belong to
Central Document Intelligence.

Responsibilities:
1. Identify accounting-relevant transactions from centrally extracted documents.
2. Categorize transactions into accounting categories.
3. Map transactions to appropriate accounts using the company's chart of accounts.
4. Convert extracted information into standardized accounting records.
5. Identify potential duplicate invoices and records.
6. Check transaction data completeness.
7. Identify missing information and supporting documents.
8. Flag ambiguous transactions and accounting exceptions.
9. Prepare structured accounting inputs for Accounting Agent 2 (Reconciliation Agent).

IMPORTANT:
- Does NOT perform reconciliation (which is Agent 2's exclusive responsibility).
- Does NOT post entries or generate final financial statements (which belongs to downstream agents).
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AccountingPeriod,
    Document,
    ExtractedColumn,
    ExtractedRow,
    ExtractedTable,
    ExtractionRun,
)
from app.models.accounting_intake import AccountingIntakeRecord
from app.models.reporting import AccountMapping

logger = logging.getLogger("app.agents.accounting_intake")


class AccountingIntakePreparationAgent:
    """Accounting Agent 1: Accounting Intake & Preparation Agent."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def execute_intake_preparation(
        self,
        session: AsyncSession,
        *,
        firm_id: uuid.UUID,
        client_id: uuid.UUID,
        period_id: uuid.UUID,
        prepared_by: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Processes all centrally extracted documents for this client & period,
        preparing structured accounting inputs for Agent 2.
        """
        logger.info(
            "accounting_agent_1: starting intake & preparation for client=%s period=%s",
            client_id,
            period_id,
        )

        period = await session.get(AccountingPeriod, period_id)
        period_start = period.start_date if period else None
        period_end = period.end_date if period else None

        # Fetch all centrally extracted tables from current runs in this period
        tbl_stmt = (
            select(ExtractedTable)
            .join(ExtractionRun, ExtractedTable.run_id == ExtractionRun.id)
            .where(
                ExtractedTable.firm_id == firm_id,
                ExtractedTable.client_id == client_id,
                ExtractedTable.period_id == period_id,
                ExtractionRun.is_current.is_(True),
            )
            .order_by(ExtractedTable.ordinal)
        )
        tables = (await session.scalars(tbl_stmt)).all()

        # Load existing AccountMappings for chart of accounts mapping
        mapping_stmt = select(AccountMapping).where(
            AccountMapping.firm_id == firm_id,
            AccountMapping.client_id == client_id,
        )
        existing_mappings = {m.account_code: m for m in (await session.scalars(mapping_stmt)).all()}

        standardized_records: list[dict[str, Any]] = []
        categorized_summary: dict[str, list[dict[str, Any]]] = defaultdict(list)
        coa_mappings: dict[str, Any] = {}
        completeness_issues: list[dict[str, Any]] = []
        duplicate_candidates: list[dict[str, Any]] = []
        exceptions: list[dict[str, Any]] = []

        # Tracking for duplicate detection (e.g., invoice # or ref + amount)
        seen_refs: dict[str, list[dict[str, Any]]] = defaultdict(list)
        seen_date_amount_party: dict[tuple[str, str, str], list[str]] = defaultdict(list)

        tx_counter = 0

        for tbl in tables:
            rows = (
                await session.scalars(
                    select(ExtractedRow)
                    .where(ExtractedRow.table_id == tbl.id)
                    .order_by(ExtractedRow.row_index)
                )
            ).all()

            tbl_type = tbl.confirmed_type or tbl.detected_type or "unknown"

            for row in rows:
                norm = row.normalized or {}
                flags = row.flags or {}
                tx_id = f"TX-{tbl.id.hex[:8]}-{row.row_index}"
                tx_counter += 1

                # 1. Identify Accounting-Relevant Fields
                date_val = norm.get("date") or norm.get("value_date")
                amount_val = norm.get("amount")
                debit_val = norm.get("debit")
                credit_val = norm.get("credit")
                withdrawal_val = norm.get("withdrawal")
                deposit_val = norm.get("deposit")
                ref_val = norm.get("reference")
                party_val = norm.get("party")
                desc_val = norm.get("description") or norm.get("narration") or ""
                account_code = norm.get("account_code")
                account_name = norm.get("account_name")

                # Resolve net numeric amount
                debit = self._to_decimal(debit_val or withdrawal_val)
                credit = self._to_decimal(credit_val or deposit_val)
                amount = self._to_decimal(amount_val)

                if amount == Decimal(0):
                    if debit > Decimal(0):
                        amount = debit
                    elif credit > Decimal(0):
                        amount = credit

                # 2. Categorize Transaction
                category = self._categorize_transaction(
                    table_type=tbl_type,
                    description=desc_val,
                    party=party_val,
                    debit=debit,
                    credit=credit,
                    account_code=account_code,
                )

                # 3. Chart of Accounts Mapping
                mapped_account = self._map_to_chart_of_accounts(
                    account_code=account_code,
                    account_name=account_name,
                    category=category,
                    description=desc_val,
                    existing_mappings=existing_mappings,
                )
                if account_code:
                    coa_mappings[str(account_code)] = mapped_account

                # 4. Standardized Accounting Record
                record = {
                    "transaction_id": tx_id,
                    "source_document_id": str(tbl.document_id),
                    "source_table_id": str(tbl.id),
                    "table_name": tbl.name,
                    "table_type": tbl_type,
                    "row_index": row.row_index,
                    "date": date_val,
                    "reference": ref_val,
                    "party": party_val,
                    "description": desc_val,
                    "accounting_category": category,
                    "account_code": mapped_account["account_code"],
                    "account_name": mapped_account["account_name"],
                    "account_category": mapped_account["account_category"],
                    "debit": str(debit) if debit else "0.00",
                    "credit": str(credit) if credit else "0.00",
                    "amount": str(amount),
                    "raw_flags": flags,
                }
                standardized_records.append(record)
                categorized_summary[category].append(
                    {"transaction_id": tx_id, "amount": str(amount), "ref": ref_val}
                )

                # 5. Check Transaction Data Completeness
                if not date_val:
                    completeness_issues.append(
                        {
                            "transaction_id": tx_id,
                            "issue": "missing_transaction_date",
                            "severity": "warning",
                            "details": f"Row {row.row_index} in {tbl.name} has no valid transaction date.",
                        }
                    )
                elif period_start and period_end:
                    try:
                        parsed_d = date.fromisoformat(str(date_val))
                        if not (period_start <= parsed_d <= period_end):
                            exceptions.append(
                                {
                                    "transaction_id": tx_id,
                                    "code": "out_of_period_transaction",
                                    "severity": "warning",
                                    "message": f"Transaction date {date_val} is outside period {period_start} to {period_end}.",
                                }
                            )
                    except ValueError:
                        pass

                if amount == Decimal(0) and debit == Decimal(0) and credit == Decimal(0):
                    completeness_issues.append(
                        {
                            "transaction_id": tx_id,
                            "issue": "missing_or_zero_amount",
                            "severity": "info",
                            "details": f"Row {row.row_index} in {tbl.name} has zero or missing monetary values.",
                        }
                    )

                # Missing supporting reference
                if amount > Decimal(10000) and not ref_val and tbl_type in ("sales_ledger", "purchase_ledger", "invoices"):
                    completeness_issues.append(
                        {
                            "transaction_id": tx_id,
                            "issue": "missing_supporting_reference",
                            "severity": "warning",
                            "details": f"Transaction for {amount} in {tbl.name} lacks invoice/voucher reference.",
                        }
                    )

                # 6. Duplicate Detection
                if ref_val and len(str(ref_val).strip()) >= 3:
                    ref_key = str(ref_val).strip().lower()
                    seen_refs[ref_key].append(
                        {"transaction_id": tx_id, "amount": str(amount), "party": party_val, "table": tbl.name}
                    )

                if date_val and amount > Decimal(0) and party_val:
                    triplet_key = (str(date_val), str(amount), str(party_val).strip().lower())
                    seen_date_amount_party[triplet_key].append(tx_id)

                # 7. Flag Ambiguous Transactions & Exceptions
                if amount < Decimal(0) or debit < Decimal(0) or credit < Decimal(0):
                    exceptions.append(
                        {
                            "transaction_id": tx_id,
                            "code": "negative_transaction_amount",
                            "severity": "warning",
                            "message": f"Negative amount detected: {amount}. May indicate inverted debit/credit signs.",
                        }
                    )

                if mapped_account.get("is_unmapped"):
                    exceptions.append(
                        {
                            "transaction_id": tx_id,
                            "code": "unmapped_account_code",
                            "severity": "info",
                            "message": f"Account '{account_code or account_name or 'Unspecified'}' requires COA mapping confirmation.",
                        }
                    )

        # Consolidate duplicate candidates
        for ref_key, matches in seen_refs.items():
            if len(matches) > 1:
                duplicate_candidates.append(
                    {
                        "type": "duplicate_reference",
                        "reference": ref_key,
                        "count": len(matches),
                        "transactions": [m["transaction_id"] for m in matches],
                        "details": f"Reference '{ref_key}' appears in {len(matches)} separate records.",
                    }
                )

        for (d_val, a_val, p_val), tx_list in seen_date_amount_party.items():
            if len(tx_list) > 1:
                duplicate_candidates.append(
                    {
                        "type": "identical_date_amount_party",
                        "date": d_val,
                        "amount": a_val,
                        "party": p_val,
                        "count": len(tx_list),
                        "transactions": tx_list,
                        "details": f"Identical date ({d_val}), amount ({a_val}), and party ({p_val}) repeated {len(tx_list)} times.",
                    }
                )

        # Calculate counts
        unmapped_count = sum(1 for e in exceptions if e["code"] == "unmapped_account_code")
        status = "needs_review" if (duplicate_candidates or len(exceptions) > 5) else "prepared"

        # Summaries by category
        summary_totals = {
            cat: {
                "count": len(tx_list),
                "total_amount": str(sum(self._to_decimal(tx["amount"]) for tx in tx_list)),
            }
            for cat, tx_list in categorized_summary.items()
        }

        # Persist structured Accounting Intake Record
        intake_record = AccountingIntakeRecord(
            id=uuid.uuid4(),
            firm_id=firm_id,
            client_id=client_id,
            period_id=period_id,
            status=status,
            transactions_count=tx_counter,
            duplicates_count=len(duplicate_candidates),
            unmapped_count=unmapped_count,
            exceptions_count=len(exceptions),
            standardized_records=standardized_records[:5000],  # bounded size
            categorized_summary=summary_totals,
            chart_of_accounts_mappings=coa_mappings,
            completeness_report={
                "total_issues": len(completeness_issues),
                "issues": completeness_issues[:100],
            },
            duplicate_candidates=duplicate_candidates[:50],
            exceptions=exceptions[:100],
            notes=notes or "Prepared by Accounting Agent 1 (Accounting Intake & Preparation Agent).",
            prepared_by=prepared_by,
        )
        session.add(intake_record)
        await session.commit()
        await session.refresh(intake_record)

        logger.info(
            "accounting_agent_1: prepared %d transactions, %d duplicates, %d exceptions (record_id=%s)",
            tx_counter,
            len(duplicate_candidates),
            len(exceptions),
            intake_record.id,
        )

        return {
            "intake_record_id": str(intake_record.id),
            "status": intake_record.status,
            "transactions_count": intake_record.transactions_count,
            "duplicates_count": intake_record.duplicates_count,
            "unmapped_count": intake_record.unmapped_count,
            "exceptions_count": intake_record.exceptions_count,
            "categorized_summary": summary_totals,
            "duplicate_candidates": duplicate_candidates,
            "completeness_issues": completeness_issues,
            "exceptions": exceptions,
            "ready_for_reconciliation": True,
        }

    # -------------------------------------------------------------------------
    # Helper Heuristics
    # -------------------------------------------------------------------------

    def _to_decimal(self, val: Any) -> Decimal:
        if val is None:
            return Decimal(0)
        try:
            cleaned = str(val).replace(",", "").replace("$", "").replace("PKR", "").strip()
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return Decimal(0)

    def _categorize_transaction(
        self,
        *,
        table_type: str,
        description: str,
        party: str | None,
        debit: Decimal,
        credit: Decimal,
        account_code: str | None,
    ) -> str:
        tt = (table_type or "").lower()
        desc = (description or "").lower()

        if "bank" in tt or "cash" in tt:
            return "cash_and_bank"
        if "sales" in tt or "receivable" in tt or "invoice" in tt:
            return "revenue"
        if "purchase" in tt or "payable" in tt:
            return "cost_of_sales" if ("goods" in desc or "raw" in desc) else "operating_expense"
        if "payroll" in tt or "salary" in desc or "wage" in desc:
            return "payroll"
        if "asset" in tt or "ppe" in tt or "depreciation" in desc:
            return "fixed_assets"
        if "inventory" in tt or "stock" in tt:
            return "inventory"

        # Description heuristics
        if any(w in desc for w in ("sales", "revenue", "consulting fee", "subscription")):
            return "revenue"
        if any(w in desc for w in ("rent", "utility", "electricity", "software", "travel", "legal")):
            return "operating_expense"
        if any(w in desc for w in ("salary", "payroll", "allowance", "provident fund")):
            return "payroll"

        # Code heuristics
        if account_code:
            first_digit = str(account_code).strip()[:1]
            if first_digit == "1":
                return "assets"
            if first_digit == "2":
                return "liabilities"
            if first_digit == "3":
                return "equity"
            if first_digit == "4":
                return "revenue"
            if first_digit in ("5", "6"):
                return "operating_expense"

        return "other"

    def _map_to_chart_of_accounts(
        self,
        *,
        account_code: str | None,
        account_name: str | None,
        category: str,
        description: str,
        existing_mappings: dict[str, AccountMapping],
    ) -> dict[str, Any]:
        """Maps transaction into company chart of accounts."""
        if account_code and str(account_code) in existing_mappings:
            m = existing_mappings[str(account_code)]
            return {
                "account_code": m.standard_account_code,
                "account_name": m.standard_account_name,
                "account_category": m.statement_line,
                "is_unmapped": False,
            }

        # Default standard mapping based on category
        default_codes = {
            "revenue": ("4000", "Sales Revenue", "Revenue"),
            "cost_of_sales": ("5000", "Cost of Goods Sold", "Cost of Sales"),
            "operating_expense": ("6000", "Operating Expenses", "Operating Expenses"),
            "payroll": ("6100", "Salaries & Wages Expense", "Operating Expenses"),
            "cash_and_bank": ("1010", "Cash & Bank Balances", "Current Assets"),
            "fixed_assets": ("1500", "Property, Plant & Equipment", "Non-Current Assets"),
            "inventory": ("1200", "Merchandise Inventory", "Current Assets"),
            "assets": ("1000", "General Assets", "Current Assets"),
            "liabilities": ("2000", "General Liabilities", "Current Liabilities"),
            "equity": ("3000", "Share Capital / Equity", "Equity"),
            "other": ("9999", "Suspense / Clearing Account", "Unclassified"),
        }

        code, name, cat_name = default_codes.get(category, ("9999", "Suspense Account", "Unclassified"))

        return {
            "account_code": str(account_code) if account_code else code,
            "account_name": str(account_name) if account_name else name,
            "account_category": cat_name,
            "is_unmapped": not bool(account_code),
        }


# Backward compatibility alias
AccountingIntakeAgent = AccountingIntakePreparationAgent
