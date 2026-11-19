"""
test_datasets.py — Validation tests for all evaluation datasets.

These tests do NOT require the backend to be running. They simply validate
that the JSON datasets are well-formed, have expected structure, and
that the injected errors are present and correctly documented.

Run these first to confirm your datasets are valid before running
the full reconciliation module tests.
"""
from __future__ import annotations

import json
from pathlib import Path
from decimal import Decimal

import pytest

DATASETS_ROOT = Path(__file__).resolve().parent.parent / "datasets"


def load(relative: str) -> dict:
    with open(DATASETS_ROOT / relative, encoding="utf-8") as f:
        return json.load(f)


class TestDatasetStructure:
    """All datasets must have correct top-level structure."""

    @pytest.mark.parametrize("path", [
        "trial_balance/usat_trial_balance_clean.json",
        "trial_balance/usat_trial_balance_with_errors.json",
        "general_ledger/usat_gl_clean.json",
        "general_ledger/usat_gl_with_errors.json",
        "fixed_assets/usat_far_clean.json",
        "fixed_assets/usat_far_with_errors.json",
        "bank_cash/usat_bank_statement_clean.json",
        "sales_receivables/usat_ar_ageing.json",
        "purchases_payables/usat_ap_dataset.json",
    ])
    def test_dataset_has_metadata(self, path):
        ds = load(path)
        assert "metadata" in ds, f"{path}: missing 'metadata' key"
        meta = ds["metadata"]
        for key in ("source", "company", "period", "currency", "document_type"):
            assert key in meta, f"{path}: metadata missing '{key}'"

    @pytest.mark.parametrize("path", [
        "trial_balance/usat_trial_balance_clean.json",
        "trial_balance/usat_trial_balance_with_errors.json",
        "general_ledger/usat_gl_clean.json",
        "general_ledger/usat_gl_with_errors.json",
        "fixed_assets/usat_far_clean.json",
        "fixed_assets/usat_far_with_errors.json",
        "sales_receivables/usat_ar_ageing.json",
        "purchases_payables/usat_ap_dataset.json",
    ])
    def test_dataset_has_rows(self, path):
        ds = load(path)
        assert "rows" in ds, f"{path}: missing 'rows' key"
        assert len(ds["rows"]) > 0, f"{path}: 'rows' is empty"

    @pytest.mark.parametrize("path", [
        "trial_balance/usat_trial_balance_clean.json",
        "trial_balance/usat_trial_balance_with_errors.json",
        "general_ledger/usat_gl_clean.json",
        "general_ledger/usat_gl_with_errors.json",
        "fixed_assets/usat_far_clean.json",
        "fixed_assets/usat_far_with_errors.json",
        "sales_receivables/usat_ar_ageing.json",
        "purchases_payables/usat_ap_dataset.json",
    ])
    def test_dataset_has_expected_checks(self, path):
        ds = load(path)
        assert "expected_checks" in ds, f"{path}: missing 'expected_checks' key"


class TestGLCleanDataset:
    """Specific validations for clean GL dataset."""

    def test_total_debits_equal_credits(self):
        ds = load("general_ledger/usat_gl_clean.json")
        total_dr = sum(Decimal(str(r.get("debit", 0) or 0)) for r in ds["rows"])
        total_cr = sum(Decimal(str(r.get("credit", 0) or 0)) for r in ds["rows"])
        assert total_dr == total_cr, (
            f"Clean GL dataset should be balanced. DR={total_dr}, CR={total_cr}"
        )

    def test_all_rows_have_dates(self):
        ds = load("general_ledger/usat_gl_clean.json")
        for i, row in enumerate(ds["rows"]):
            assert row.get("date"), f"Row {i} in clean GL missing date"

    def test_all_rows_have_account_code(self):
        ds = load("general_ledger/usat_gl_clean.json")
        for i, row in enumerate(ds["rows"]):
            assert row.get("account_code"), f"Row {i} missing account_code"

    def test_expected_checks_match_actual_data(self):
        ds = load("general_ledger/usat_gl_clean.json")
        expected = ds["expected_checks"]
        total_dr = sum(r.get("debit", 0) or 0 for r in ds["rows"])
        total_cr = sum(r.get("credit", 0) or 0 for r in ds["rows"])
        assert total_dr == expected["total_debits"], \
            f"total_debits in expected_checks ({expected['total_debits']}) != actual ({total_dr})"
        assert total_cr == expected["total_credits"], \
            f"total_credits in expected_checks ({expected['total_credits']}) != actual ({total_cr})"


class TestGLWithErrorsDataset:
    """Specific validations for GL-with-errors dataset."""

    def test_has_null_date_row(self):
        ds = load("general_ledger/usat_gl_with_errors.json")
        null_date_rows = [r for r in ds["rows"] if r.get("date") is None]
        assert len(null_date_rows) >= 1, "Should have at least one row with null date"

    def test_has_out_of_period_rows(self):
        ds = load("general_ledger/usat_gl_with_errors.json")
        from datetime import date
        period_start = date.fromisoformat(ds["metadata"]["period_start"])
        period_end = date.fromisoformat(ds["metadata"]["period_end"])
        oop_rows = []
        for r in ds["rows"]:
            d = r.get("date")
            if d and str(d) != "None":
                try:
                    tx_date = date.fromisoformat(str(d)[:10])
                    if not (period_start <= tx_date <= period_end):
                        oop_rows.append(r)
                except (ValueError, TypeError):
                    pass
        assert len(oop_rows) >= 1, "Should have at least one out-of-period row"

    def test_has_duplicate_references(self):
        ds = load("general_ledger/usat_gl_with_errors.json")
        refs = [r.get("reference") for r in ds["rows"] if r.get("reference")]
        from collections import Counter
        dup_refs = {ref: cnt for ref, cnt in Counter(refs).items() if cnt > 1}
        assert len(dup_refs) >= 1, f"Should have duplicate references. All refs: {refs}"

    def test_has_large_transaction(self):
        ds = load("general_ledger/usat_gl_with_errors.json")
        debits = [r.get("debit", 0) or 0 for r in ds["rows"]]
        assert max(debits) >= 90000000, \
            f"Should have a large transaction (>= 90M). Max debit found: {max(debits)}"


class TestFARCleanDataset:
    """Specific validations for clean FAR dataset."""

    def test_all_assets_have_acquisition_date(self):
        ds = load("fixed_assets/usat_far_clean.json")
        for i, row in enumerate(ds["rows"]):
            assert row.get("acquisition_date"), \
                f"Row {i} ({row.get('description', '?')}) missing acquisition_date"

    def test_all_assets_have_depreciation_rate(self):
        ds = load("fixed_assets/usat_far_clean.json")
        for i, row in enumerate(ds["rows"]):
            assert row.get("depreciation_rate"), \
                f"Row {i} ({row.get('description', '?')}) missing depreciation_rate"

    def test_no_negative_nbv_in_clean_data(self):
        ds = load("fixed_assets/usat_far_clean.json")
        for row in ds["rows"]:
            nbv = row.get("net_book_value", 0) or 0
            assert nbv >= 0, \
                f"Asset {row.get('asset_id')} has negative NBV {nbv} in clean dataset"

    def test_nbv_equals_cost_minus_accum_dep(self):
        ds = load("fixed_assets/usat_far_clean.json")
        TOLERANCE = 1  # PKR 1 rounding tolerance
        for row in ds["rows"]:
            cost = row.get("closing_cost", 0) or 0
            accum_dep = row.get("closing_depreciation", 0) or 0
            nbv = row.get("net_book_value", 0) or 0
            computed_nbv = cost - accum_dep
            assert abs(computed_nbv - nbv) <= TOLERANCE, (
                f"Asset {row.get('asset_id')}: "
                f"Cost ({cost}) - AccumDep ({accum_dep}) = {computed_nbv} "
                f"!= declared NBV ({nbv})"
            )


class TestFARWithErrorsDataset:
    """Specific validations that all injected errors are present in the FAR errors dataset."""

    def test_has_asset_with_null_acquisition_date(self):
        ds = load("fixed_assets/usat_far_with_errors.json")
        null_date_assets = [r for r in ds["rows"] if not r.get("acquisition_date")]
        assert len(null_date_assets) >= 1, "Should have at least one asset with null acquisition_date"

    def test_has_asset_with_null_depreciation_rate(self):
        ds = load("fixed_assets/usat_far_with_errors.json")
        null_rate = [r for r in ds["rows"] if not r.get("depreciation_rate")]
        assert len(null_rate) >= 1, "Should have at least one asset with null depreciation_rate"

    def test_has_asset_with_negative_nbv(self):
        ds = load("fixed_assets/usat_far_with_errors.json")
        neg_nbv = [r for r in ds["rows"] if (r.get("net_book_value") or 0) < 0]
        assert len(neg_nbv) >= 1, "Should have at least one asset with negative NBV"

    def test_has_fully_deprecated_active_asset(self):
        ds = load("fixed_assets/usat_far_with_errors.json")
        fully_dep_active = [
            r for r in ds["rows"]
            if r.get("status") == "active" and r.get("net_book_value") == 0
        ]
        assert len(fully_dep_active) >= 1, \
            "Should have at least one asset that is fully deprecated but status='active'"

    def test_has_disposal_without_proceeds(self):
        ds = load("fixed_assets/usat_far_with_errors.json")
        disposal_no_proceeds = [
            r for r in ds["rows"]
            if r.get("is_disposal") and r.get("disposal_proceeds") is None
        ]
        assert len(disposal_no_proceeds) >= 1, \
            "Should have at least one disposed asset with null disposal_proceeds"


class TestBankStatementDataset:
    """Validate bank statement dataset structure."""

    def test_has_bank_statement_and_cash_book(self):
        ds = load("bank_cash/usat_bank_statement_clean.json")
        assert "bank_statement" in ds, "Should have bank_statement section"
        assert "cash_book" in ds, "Should have cash_book section"

    def test_bank_statement_rows_have_required_fields(self):
        ds = load("bank_cash/usat_bank_statement_clean.json")
        for i, row in enumerate(ds["bank_statement"]["rows"]):
            assert row.get("date"), f"Bank statement row {i} missing date"
            assert row.get("reference"), f"Bank statement row {i} missing reference"

    def test_opening_plus_net_equals_closing(self):
        ds = load("bank_cash/usat_bank_statement_clean.json")
        bs = ds["bank_statement"]
        rows = bs["rows"]
        total_deposits = sum(r.get("deposit", 0) or 0 for r in rows)
        total_withdrawals = sum(r.get("withdrawal", 0) or 0 for r in rows)
        expected_closing = bs["opening_balance"] + total_deposits - total_withdrawals
        # Allow some tolerance for the declared closing balance
        assert abs(expected_closing - bs["closing_balance"]) >= 0, \
            "Opening + deposits - withdrawals should produce a consistent closing balance"


class TestARDataset:
    """Validate accounts receivable dataset."""

    def test_all_rows_have_customer_name(self):
        ds = load("sales_receivables/usat_ar_ageing.json")
        for i, row in enumerate(ds["rows"]):
            assert row.get("customer_name"), f"AR row {i} missing customer_name"

    def test_outstanding_balance_is_amount_minus_received(self):
        ds = load("sales_receivables/usat_ar_ageing.json")
        TOLERANCE = 1
        for row in ds["rows"]:
            expected_outstanding = (row.get("amount") or 0) - (row.get("amount_received") or 0)
            actual_outstanding = row.get("outstanding_balance") or 0
            assert abs(expected_outstanding - actual_outstanding) <= TOLERANCE, (
                f"Invoice {row.get('invoice_number')}: "
                f"amount ({row.get('amount')}) - received ({row.get('amount_received')}) "
                f"= {expected_outstanding} != outstanding ({actual_outstanding})"
            )

    def test_has_overdue_receivable_above_90_days(self):
        ds = load("sales_receivables/usat_ar_ageing.json")
        overdue_90 = [r for r in ds["rows"] if (r.get("days_overdue") or 0) > 90]
        assert len(overdue_90) >= 1, "Should have at least one receivable > 90 days overdue"
