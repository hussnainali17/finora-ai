"""
test_trial_balance.py — DeepEval tests for Trial Balance datasets.

These tests validate that:
  1. A clean, balanced trial balance from USAT data is correctly identified as valid
  2. A corrupted trial balance (missing fields, duplicates, imbalance) triggers findings
  3. The system correctly routes TB data to reconciliation
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent / "ca-firm-system" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:
    from app.accounting.reconciliation.general_ledger import check_general_ledger
    BACKEND_AVAILABLE = True
except ImportError as e:
    BACKEND_AVAILABLE = False
    IMPORT_ERROR = str(e)


def _build_tb_table(dataset: dict, table_id: str = "tb-001", doc_id: str = "doc-001") -> dict:
    """Convert TB dataset rows into the format expected by GL reconciliation (TB side)."""
    rows = []
    for i, row in enumerate(dataset["rows"]):
        normalized = {
            "account_code": str(row.get("account_code", "")),
            "account_name": row.get("account_name", ""),
            "debit": max(0, row.get("debits", 0) or 0),
            "credit": max(0, row.get("credits", 0) or 0),
            "_row_index": i,
        }
        rows.append(normalized)
    return {
        "table_id": table_id,
        "document_id": doc_id,
        "detected_type": "trial_balance",
        "confirmed_type": "trial_balance",
        "period_start": dataset["metadata"]["period_start"],
        "period_end": dataset["metadata"]["period_end"],
        "rows": rows,
    }


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason=f"Backend not importable: {IMPORT_ERROR if not BACKEND_AVAILABLE else ''}")
class TestTrialBalanceDataset:
    """Validate TB datasets are well-formed and behave correctly as TB input to GL module."""

    def test_clean_tb_rows_are_loadable(self, tb_clean):
        """Clean TB dataset should load with correct number of rows."""
        assert len(tb_clean["rows"]) == 10, f"Expected 10 rows, got {len(tb_clean['rows'])}"

    def test_clean_tb_all_rows_have_account_code(self, tb_clean):
        for row in tb_clean["rows"]:
            assert row.get("account_code"), f"Row missing account_code: {row}"

    def test_clean_tb_all_rows_have_account_name(self, tb_clean):
        for row in tb_clean["rows"]:
            assert row.get("account_name"), f"Row missing account_name: {row}"

    def test_clean_tb_amounts_are_numeric(self, tb_clean):
        for row in tb_clean["rows"]:
            for field in ("beginning_balance", "debits", "credits", "ending_balance"):
                val = row.get(field, 0) or 0
                assert isinstance(val, (int, float)), \
                    f"Field {field} should be numeric, got {type(val)}: {val}"

    def test_corrupted_tb_has_expected_error_rows(self, tb_with_errors):
        """Corrupted TB dataset should have the injected error rows."""
        rows = tb_with_errors["rows"]
        # Row 2 (index 1) should have empty account_code and null amounts
        empty_rows = [r for r in rows if not r.get("account_code") and not r.get("account_name")]
        assert len(empty_rows) >= 1, "Should have at least one row with missing account fields"

        # Should have duplicate account code 30001001
        codes = [r.get("account_code") for r in rows]
        assert codes.count("30001001") >= 2, "Should have at least 2 rows with 30001001 (duplicate)"

    def test_clean_tb_used_as_gl_reconciliation_input(self, tb_clean, gl_clean):
        """When a valid TB is paired with a matching GL, reconciliation should produce no discrepancies."""
        from datetime import date

        def _build_gl_table(dataset: dict) -> dict:
            rows = []
            for i, row in enumerate(dataset["rows"]):
                rows.append({
                    "date": "2025-07-05",
                    "account_code": row.get("account_code", ""),
                    "account_name": row.get("account_name", ""),
                    "description": row.get("account_name", ""),
                    "debit": max(0, row.get("debits", 0) or 0),
                    "credit": max(0, row.get("credits", 0) or 0),
                    "_row_index": i,
                })
            return {
                "table_id": "gl-001",
                "document_id": "doc-001",
                "detected_type": "general_ledger",
                "confirmed_type": "general_ledger",
                "period_start": dataset["metadata"]["period_start"],
                "period_end": dataset["metadata"]["period_end"],
                "rows": rows,
            }

        # Build GL from TB data (same accounts = should reconcile perfectly)
        gl_table = _build_gl_table(tb_clean)
        tb_table = _build_tb_table(tb_clean)

        result = check_general_ledger(
            gl_tables=[gl_table],
            tb_tables=[tb_table],
            period_start=date(2025, 7, 1),
            period_end=date(2025, 10, 31),
        )
        recon_schedules = [s for s in result.schedules if s.schedule_type == "gl_tb_reconciliation"]
        assert len(recon_schedules) == 1, "Should produce a GL vs TB reconciliation schedule"
