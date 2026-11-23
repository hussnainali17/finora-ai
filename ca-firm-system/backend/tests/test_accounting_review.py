"""Tests for Phase 6: Accounting Review & Reconciliation (Agent 2).

Tests cover:
- Deterministic reconciliation logic (Decimal arithmetic)
- AR ageing buckets
- Bank reconciliation matching
- Duplicate invoice detection
- Payroll deduction check
- Fixed assets missing depreciation rate
- Inventory movement imbalance
- API authorization (review:read required)
- Firm isolation (firm A cannot see firm B's review runs)
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.accounting.reconciliation import (
    check_bank_cash,
    check_fixed_assets,
    check_inventory,
    check_payroll,
    check_purchases_payables,
    check_sales_receivables,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TODAY = date(2024, 12, 31)
PERIOD_START = date(2024, 1, 1)
PERIOD_END = date(2024, 12, 31)


def _make_ar_row(
    *,
    reference: str = "INV-001",
    customer: str = "Customer A",
    amount: str = "1000.00",
    due_date: date | None = None,
    row_index: int = 0,
    table_id: str = "t1",
    document_id: str = "d1",
) -> dict:
    row = {
        "reference": reference,
        "customer": customer,
        "amount": amount,
        "_row_index": row_index,
        "_table_id": table_id,
        "_document_id": document_id,
    }
    if due_date is not None:
        row["due_date"] = due_date.isoformat()
    return row


def _make_table(rows: list, table_id: str = "t1", document_id: str = "d1") -> dict:
    return {"table_id": table_id, "document_id": document_id, "rows": rows}


# ---------------------------------------------------------------------------
# Sales & Receivables
# ---------------------------------------------------------------------------


class TestSalesReceivables:
    def test_no_findings_for_clean_data(self):
        rows = [
            _make_ar_row(reference="INV-001", customer="A", amount="500.00",
                         due_date=PERIOD_END, row_index=0),
            _make_ar_row(reference="INV-002", customer="B", amount="300.00",
                         due_date=PERIOD_END, row_index=1),
        ]
        result = check_sales_receivables(
            [_make_table(rows)], PERIOD_START, PERIOD_END
        )
        # No duplicate, no missing ref, not aged -> only aged_receivable if >90d overdue
        aged = [f for f in result.findings if f.finding_type == "aged_receivable"]
        assert len(aged) == 0

    def test_missing_invoice_number_flagged(self):
        rows = [_make_ar_row(reference="", customer="A", amount="100.00", row_index=0)]
        result = check_sales_receivables([_make_table(rows)], PERIOD_START, PERIOD_END)
        types = {f.finding_type for f in result.findings}
        assert "missing_invoice_number" in types

    def test_duplicate_invoice_number_flagged(self):
        rows = [
            _make_ar_row(reference="INV-DUP", customer="A", amount="100.00", row_index=0),
            _make_ar_row(reference="INV-DUP", customer="B", amount="200.00", row_index=1),
        ]
        result = check_sales_receivables([_make_table(rows)], PERIOD_START, PERIOD_END)
        types = {f.finding_type for f in result.findings}
        assert "duplicate_invoice_number" in types

    def test_aged_receivable_over_90_days(self):
        due = PERIOD_END - timedelta(days=130)
        rows = [_make_ar_row(reference="INV-OLD", customer="A", amount="5000.00",
                             due_date=due, row_index=0)]
        result = check_sales_receivables([_make_table(rows)], PERIOD_START, PERIOD_END)
        aged = [f for f in result.findings if f.finding_type == "aged_receivable"]
        assert len(aged) == 1
        assert aged[0].severity == "error"  # over 120 days

    def test_ar_ageing_uses_decimal(self):
        due = PERIOD_END - timedelta(days=45)
        rows = [
            _make_ar_row(reference="INV-A", customer="A", amount="1234.5678",
                         due_date=due, row_index=0),
        ]
        result = check_sales_receivables([_make_table(rows)], PERIOD_START, PERIOD_END)
        assert len(result.schedules) == 1
        schedule = result.schedules[0]
        assert schedule.schedule_type == "ar_ageing"
        # Grand total should be a valid Decimal string
        grand = Decimal(schedule.data["grand_total"])
        assert grand == Decimal("1234.5678")

    def test_empty_tables_returns_empty_schedule(self):
        result = check_sales_receivables([], PERIOD_START, PERIOD_END)
        assert result.findings == []
        assert result.schedules[0].schedule_type == "ar_ageing"


# ---------------------------------------------------------------------------
# Purchases & Payables
# ---------------------------------------------------------------------------


class TestPurchasesPayables:
    def test_missing_supplier_flagged(self):
        from app.accounting.reconciliation.purchases_payables import check_purchases_payables

        rows = [{"amount": "500.00", "reference": "PO-001", "_row_index": 0,
                 "_table_id": "t1", "_document_id": "d1"}]
        result = check_purchases_payables([_make_table(rows)], PERIOD_START, PERIOD_END)
        types = {f.finding_type for f in result.findings}
        assert "missing_supplier_reference" in types

    def test_duplicate_payment_flagged(self):
        from app.accounting.reconciliation.purchases_payables import check_purchases_payables

        rows = [
            {"amount": "1000.00", "reference": "PO-DUP", "supplier": "Vendor A",
             "_row_index": 0, "_table_id": "t1", "_document_id": "d1"},
            {"amount": "1000.00", "reference": "PO-DUP", "supplier": "Vendor A",
             "_row_index": 1, "_table_id": "t1", "_document_id": "d1"},
        ]
        result = check_purchases_payables([_make_table(rows)], PERIOD_START, PERIOD_END)
        types = {f.finding_type for f in result.findings}
        assert "duplicate_purchase_reference" in types


# ---------------------------------------------------------------------------
# Bank & Cash
# ---------------------------------------------------------------------------


class TestBankCash:
    def test_unmatched_bank_entry_flagged(self):
        bank_rows = [
            {"date": "2024-06-15", "amount": "5000.00", "reference": "CHQ-001",
             "description": "Cheque payment", "_row_index": 0,
             "_table_id": "bank", "_document_id": "d1"},
        ]
        # Empty cash book — nothing to match against
        result = check_bank_cash(
            [_make_table(bank_rows, table_id="bank")],
            [],
            PERIOD_START,
            PERIOD_END,
        )
        # With no cash book rows, all bank entries are unmatched
        types = {f.finding_type for f in result.findings}
        assert "unmatched_bank_entry" in types or "no_cash_book_data" in types

    def test_matched_entries_produce_no_finding(self):
        bank_rows = [
            {"date": "2024-06-15", "amount": "1000.00", "reference": "REF-A",
             "description": "Payment", "_row_index": 0,
             "_table_id": "bank", "_document_id": "d1"},
        ]
        book_rows = [
            {"date": "2024-06-15", "amount": "1000.00", "reference": "REF-A",
             "description": "Payment", "_row_index": 0,
             "_table_id": "book", "_document_id": "d2"},
        ]
        result = check_bank_cash(
            [_make_table(bank_rows, table_id="bank")],
            [_make_table(book_rows, table_id="book")],
            PERIOD_START,
            PERIOD_END,
        )
        unmatched = [f for f in result.findings if f.finding_type == "unmatched_bank_entry"]
        assert len(unmatched) == 0


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


class TestInventory:
    def test_imbalance_detected(self):
        opening = [{"item_code": "ITEM-A", "quantity": "100", "amount": "1000.00",
                    "_row_index": 0, "_table_id": "open", "_document_id": "d1"}]
        movement = [{"item_code": "ITEM-A", "quantity": "50", "amount": "500.00",
                     "type": "purchase", "_row_index": 0,
                     "_table_id": "mov", "_document_id": "d2"}]
        closing = [{"item_code": "ITEM-A", "quantity": "200",  # wrong: 100+50=150, not 200
                    "amount": "2000.00",
                    "_row_index": 0, "_table_id": "close", "_document_id": "d3"}]
        result = check_inventory(
            [_make_table(opening, table_id="open")],
            [_make_table(movement, table_id="mov")],
            [_make_table(closing, table_id="close")],
            PERIOD_START, PERIOD_END,
        )
        types = {f.finding_type for f in result.findings}
        assert "inventory_imbalance" in types or "quantity_imbalance" in types

    def test_negative_quantity_flagged(self):
        opening = [{"item_code": "ITEM-B", "quantity": "-10", "amount": "0",
                    "_row_index": 0, "_table_id": "open", "_document_id": "d1"}]
        result = check_inventory(
            [_make_table(opening, table_id="open")], [], [], PERIOD_START, PERIOD_END
        )
        types = {f.finding_type for f in result.findings}
        assert "negative_quantity" in types


# ---------------------------------------------------------------------------
# Fixed Assets
# ---------------------------------------------------------------------------


class TestFixedAssets:
    def test_missing_depreciation_rate_flagged(self):
        rows = [
            {"asset_code": "FA-001", "description": "Office Equipment",
             "cost": "50000.00", "acquisition_date": "2023-01-01",
             # No depreciation_rate column
             "_row_index": 0, "_table_id": "fa", "_document_id": "d1"},
        ]
        result = check_fixed_assets([_make_table(rows, table_id="fa")], PERIOD_START, PERIOD_END)
        types = {f.finding_type for f in result.findings}
        assert "missing_depreciation_rate" in types

    def test_missing_acquisition_date_flagged(self):
        rows = [
            {"asset_code": "FA-002", "description": "Vehicle",
             "cost": "1000000.00", "depreciation_rate": "0.20",
             "_row_index": 0, "_table_id": "fa", "_document_id": "d1"},
        ]
        result = check_fixed_assets([_make_table(rows, table_id="fa")], PERIOD_START, PERIOD_END)
        types = {f.finding_type for f in result.findings}
        assert "missing_acquisition_date" in types

    def test_fully_depreciated_asset_still_active_flagged(self):
        rows = [
            {"asset_code": "FA-003", "description": "Old Computer",
             "cost": "100000.00", "net_book_value": "0.00",
             "depreciation_rate": "0.33", "acquisition_date": "2015-01-01",
             "status": "active",
             "_row_index": 0, "_table_id": "fa", "_document_id": "d1"},
        ]
        result = check_fixed_assets([_make_table(rows, table_id="fa")], PERIOD_START, PERIOD_END)
        types = {f.finding_type for f in result.findings}
        assert "fully_depreciated_active_asset" in types


# ---------------------------------------------------------------------------
# Payroll
# ---------------------------------------------------------------------------


class TestPayroll:
    def test_deduction_mismatch_flagged(self):
        rows = [
            {"employee_id": "E001", "gross_pay": "100000.00",
             "deductions": "10000.00", "net_pay": "80000.00",  # 100000 - 10000 != 80000
             "_row_index": 0, "_table_id": "payroll", "_document_id": "d1"},
        ]
        result = check_payroll([_make_table(rows, table_id="payroll")], PERIOD_START, PERIOD_END)
        types = {f.finding_type for f in result.findings}
        assert "payroll_deduction_mismatch" in types

    def test_negative_net_pay_flagged(self):
        rows = [
            {"employee_id": "E002", "gross_pay": "50000.00",
             "deductions": "60000.00", "net_pay": "-10000.00",
             "_row_index": 0, "_table_id": "payroll", "_document_id": "d1"},
        ]
        result = check_payroll([_make_table(rows, table_id="payroll")], PERIOD_START, PERIOD_END)
        types = {f.finding_type for f in result.findings}
        assert "negative_net_pay" in types

    def test_missing_employee_id_flagged(self):
        rows = [
            {"gross_pay": "50000.00", "deductions": "5000.00", "net_pay": "45000.00",
             "_row_index": 0, "_table_id": "payroll", "_document_id": "d1"},
        ]
        result = check_payroll([_make_table(rows, table_id="payroll")], PERIOD_START, PERIOD_END)
        types = {f.finding_type for f in result.findings}
        assert "missing_employee_id" in types

    def test_clean_payroll_no_findings(self):
        rows = [
            {"employee_id": "E001", "gross_pay": "100000.00",
             "deductions": "20000.00", "net_pay": "80000.00",
             "_row_index": 0, "_table_id": "payroll", "_document_id": "d1"},
        ]
        result = check_payroll([_make_table(rows, table_id="payroll")], PERIOD_START, PERIOD_END)
        mismatch = [f for f in result.findings if f.finding_type == "payroll_deduction_mismatch"]
        assert len(mismatch) == 0


# ---------------------------------------------------------------------------
# Decimal arithmetic correctness
# ---------------------------------------------------------------------------


class TestDecimalArithmetic:
    def test_ar_amounts_are_decimal_not_float(self):
        """Verify amounts in findings are Decimal, not float."""
        due = PERIOD_END - timedelta(days=200)
        rows = [_make_ar_row(reference="INV-X", customer="X",
                             amount="99999.9999", due_date=due, row_index=0)]
        result = check_sales_receivables([_make_table(rows)], PERIOD_START, PERIOD_END)
        aged = [f for f in result.findings if f.finding_type == "aged_receivable"]
        assert len(aged) == 1
        # Amount must be Decimal
        assert isinstance(aged[0].amount, Decimal)
        assert aged[0].amount == Decimal("99999.9999")

    def test_schedule_total_exact(self):
        """Verify that the grand total in the ageing schedule is exact Decimal arithmetic."""
        rows = [
            _make_ar_row(reference=f"INV-{i}", customer="C", amount="333.3333",
                         due_date=PERIOD_END, row_index=i)
            for i in range(3)
        ]
        result = check_sales_receivables([_make_table(rows)], PERIOD_START, PERIOD_END)
        grand = Decimal(result.schedules[0].data["grand_total"])
        expected = Decimal("333.3333") * 3
        assert grand == expected


# ---------------------------------------------------------------------------
# API authorization tests (require a running test database — marked as integration)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestReviewAPIAuth:
    def test_unauthenticated_returns_401(self, client):
        resp = client.get(
            f"/api/v1/clients/{uuid.uuid4()}/periods/{uuid.uuid4()}/review/"
        )
        assert resp.status_code == 401

    def test_missing_permission_returns_403(self):
        """accountant does NOT have review:manage, only review:read and review:resolve."""
        pytest.skip("Requires PostgreSQL test database and user with restricted permissions")

    def test_firm_isolation(self):
        """Firm A user must NOT see Firm B's review run."""
        pytest.skip("Requires PostgreSQL test database with multi-tenant data")
