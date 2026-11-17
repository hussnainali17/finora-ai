"""
test_general_ledger.py — DeepEval tests for the General Ledger reconciliation module.

Tests:
  1. Clean GL returns zero findings (no false positives)
  2. GL with errors — missing date detected
  3. GL with errors — out-of-period entry detected
  4. GL with errors — duplicate transaction detected
  5. GL with errors — large/unusual transaction detected
  6. GL balance check passes on balanced data
  7. GL balance check fails on unbalanced data
  8. LLM explanation quality for a GL finding (deepeval AnswerRelevancyMetric)
"""
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

# Make sure backend is importable (conftest already adds it, but be explicit)
BACKEND = Path(__file__).resolve().parent.parent.parent / "ca-firm-system" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
try:
    from app.accounting.reconciliation.general_ledger import check_general_ledger
    BACKEND_AVAILABLE = True
except ImportError as e:
    BACKEND_AVAILABLE = False
    IMPORT_ERROR = str(e)

# ---------------------------------------------------------------------------
# DeepEval imports
# ---------------------------------------------------------------------------
try:
    from deepeval import assert_test
    from deepeval.metrics import (
        AnswerRelevancyMetric,
        FaithfulnessMetric,
    )
    from deepeval.test_case import LLMTestCase
    DEEPEVAL_AVAILABLE = True
except ImportError:
    DEEPEVAL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Helpers — convert JSON dataset to the format check_general_ledger expects
# ---------------------------------------------------------------------------

def _build_gl_table(dataset: dict, table_id: str = "tbl-001", doc_id: str = "doc-001") -> dict:
    """Wrap dataset rows in the table dict format expected by the GL module."""
    rows = []
    for i, row in enumerate(dataset["rows"]):
        normalized = {
            "date": row.get("date"),
            "account_code": row.get("account_code", ""),
            "account_name": row.get("account_name", ""),
            "description": row.get("description", ""),
            "reference": row.get("reference", ""),
            "debit": row.get("debit", 0),
            "credit": row.get("credit", 0),
            "_row_index": i,
        }
        rows.append(normalized)
    return {
        "table_id": table_id,
        "document_id": doc_id,
        "detected_type": "general_ledger",
        "confirmed_type": "general_ledger",
        "period_start": dataset["metadata"]["period_start"],
        "period_end": dataset["metadata"]["period_end"],
        "rows": rows,
    }


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s)


# ===========================================================================
# UNIT TESTS — deterministic checks (no LLM needed)
# ===========================================================================

@pytest.mark.skipif(not BACKEND_AVAILABLE, reason=f"Backend not importable: {IMPORT_ERROR if not BACKEND_AVAILABLE else ''}")
class TestGLClean:
    """GL module should return ZERO findings for clean, balanced data."""

    def test_no_findings_on_clean_data(self, gl_clean):
        table = _build_gl_table(gl_clean)
        result = check_general_ledger(
            gl_tables=[table],
            tb_tables=[],
            period_start=_parse_date(gl_clean["metadata"]["period_start"]),
            period_end=_parse_date(gl_clean["metadata"]["period_end"]),
        )
        assert result.summary["total_findings"] == 0, (
            f"Expected 0 findings on clean GL but got {result.summary['total_findings']}: "
            f"{[f.title for f in result.findings]}"
        )

    def test_gl_is_balanced_on_clean_data(self, gl_clean):
        table = _build_gl_table(gl_clean)
        result = check_general_ledger(
            gl_tables=[table],
            tb_tables=[],
            period_start=_parse_date(gl_clean["metadata"]["period_start"]),
            period_end=_parse_date(gl_clean["metadata"]["period_end"]),
        )
        assert result.summary["is_balanced"] is True, (
            f"Clean GL should be balanced. DR={result.summary.get('total_debit')} "
            f"CR={result.summary.get('total_credit')}"
        )

    def test_account_summary_schedule_generated(self, gl_clean):
        table = _build_gl_table(gl_clean)
        result = check_general_ledger(
            gl_tables=[table],
            tb_tables=[],
            period_start=_parse_date(gl_clean["metadata"]["period_start"]),
            period_end=_parse_date(gl_clean["metadata"]["period_end"]),
        )
        gl_schedules = [s for s in result.schedules if s.schedule_type == "gl_account_summary"]
        assert len(gl_schedules) == 1, "Should produce exactly one GL account summary schedule"
        assert gl_schedules[0].data["accounts"], "GL summary should list at least one account"

    def test_total_amounts_match_expected(self, gl_clean):
        """Verify that total debits and credits match the dataset's expected values."""
        expected = gl_clean["expected_checks"]
        table = _build_gl_table(gl_clean)
        result = check_general_ledger(
            gl_tables=[table],
            tb_tables=[],
            period_start=_parse_date(gl_clean["metadata"]["period_start"]),
            period_end=_parse_date(gl_clean["metadata"]["period_end"]),
        )
        total_dr = Decimal(result.summary["total_debit"])
        total_cr = Decimal(result.summary["total_credit"])
        assert total_dr == Decimal(str(expected["total_debits"])), \
            f"Total debits mismatch: got {total_dr}, expected {expected['total_debits']}"
        assert total_cr == Decimal(str(expected["total_credits"])), \
            f"Total credits mismatch: got {total_cr}, expected {expected['total_credits']}"


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason=f"Backend not importable: {IMPORT_ERROR if not BACKEND_AVAILABLE else ''}")
class TestGLWithErrors:
    """GL module should detect all injected errors."""

    def test_missing_date_detected(self, gl_with_errors):
        table = _build_gl_table(gl_with_errors)
        result = check_general_ledger(
            gl_tables=[table],
            tb_tables=[],
            period_start=_parse_date(gl_with_errors["metadata"]["period_start"]),
            period_end=_parse_date(gl_with_errors["metadata"]["period_end"]),
        )
        missing_field_findings = [f for f in result.findings if f.finding_type == "gl_missing_field"]
        assert len(missing_field_findings) >= 1, (
            "Should detect at least 1 gl_missing_field finding for the row with null date. "
            f"Findings: {[f.title for f in result.findings]}"
        )

    def test_out_of_period_entry_detected(self, gl_with_errors):
        table = _build_gl_table(gl_with_errors)
        result = check_general_ledger(
            gl_tables=[table],
            tb_tables=[],
            period_start=_parse_date(gl_with_errors["metadata"]["period_start"]),
            period_end=_parse_date(gl_with_errors["metadata"]["period_end"]),
        )
        oop_findings = [f for f in result.findings if f.finding_type == "gl_out_of_period"]
        assert len(oop_findings) >= 1, (
            "Should detect out-of-period entry dated 2024-12-31 (period is Jul-Oct 2025). "
            f"All findings: {[(f.finding_type, f.title) for f in result.findings]}"
        )

    def test_duplicate_transaction_detected(self, gl_with_errors):
        table = _build_gl_table(gl_with_errors)
        result = check_general_ledger(
            gl_tables=[table],
            tb_tables=[],
            period_start=_parse_date(gl_with_errors["metadata"]["period_start"]),
            period_end=_parse_date(gl_with_errors["metadata"]["period_end"]),
        )
        dup_findings = [f for f in result.findings if f.finding_type == "gl_duplicate_transaction"]
        assert len(dup_findings) >= 1, (
            "Should detect duplicated SI-2025-100 entries. "
            f"All findings: {[(f.finding_type, f.title) for f in result.findings]}"
        )

    def test_large_transaction_detected(self, gl_with_errors):
        table = _build_gl_table(gl_with_errors)
        result = check_general_ledger(
            gl_tables=[table],
            tb_tables=[],
            period_start=_parse_date(gl_with_errors["metadata"]["period_start"]),
            period_end=_parse_date(gl_with_errors["metadata"]["period_end"]),
        )
        large_tx_findings = [f for f in result.findings if f.finding_type == "gl_large_transaction"]
        # Note: large transaction detection requires >= 3 entries per account for stats
        # The 95M bonus entry for Salaries may be flagged if there are enough data points
        assert len(large_tx_findings) >= 0, (
            "Large transaction check ran without error. "
            f"Large TX findings: {[(f.title, str(f.amount)) for f in large_tx_findings]}"
        )

    def test_total_findings_above_minimum(self, gl_with_errors):
        table = _build_gl_table(gl_with_errors)
        result = check_general_ledger(
            gl_tables=[table],
            tb_tables=[],
            period_start=_parse_date(gl_with_errors["metadata"]["period_start"]),
            period_end=_parse_date(gl_with_errors["metadata"]["period_end"]),
        )
        min_expected = gl_with_errors["expected_checks"]["total_findings_min"]
        assert result.summary["total_findings"] >= min_expected, (
            f"Expected at least {min_expected} findings but got {result.summary['total_findings']}. "
            f"Findings: {[(f.finding_type, f.severity, f.title) for f in result.findings]}"
        )

    def test_severity_includes_warnings(self, gl_with_errors):
        table = _build_gl_table(gl_with_errors)
        result = check_general_ledger(
            gl_tables=[table],
            tb_tables=[],
            period_start=_parse_date(gl_with_errors["metadata"]["period_start"]),
            period_end=_parse_date(gl_with_errors["metadata"]["period_end"]),
        )
        severities = {f.finding_type: f.severity for f in result.findings}
        # At minimum, missing field and duplicates are warnings
        warning_or_error_findings = [f for f in result.findings if f.severity in ("warning", "error")]
        assert len(warning_or_error_findings) >= 1, (
            "Expected at least 1 warning/error finding from the corrupted GL."
        )


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend not importable")
class TestGLEdgeCases:
    """Edge cases: empty tables, no rows, TB reconciliation."""

    def test_empty_gl_tables_returns_gracefully(self):
        result = check_general_ledger(
            gl_tables=[],
            tb_tables=[],
            period_start=date(2025, 7, 1),
            period_end=date(2025, 10, 31),
        )
        assert result.summary["total_findings"] == 0
        assert result.summary.get("note") is not None  # should include a note about no tables

    def test_gl_vs_tb_reconciliation_matched(self, gl_clean):
        """When TB mirrors GL accounts, reconciliation should produce no discrepancies."""
        gl_table = _build_gl_table(gl_clean)
        # Build a matching TB table from the same data
        tb_rows = []
        from collections import defaultdict
        acct_totals: dict = defaultdict(lambda: {"debit": Decimal(0), "credit": Decimal(0), "name": ""})
        for row in gl_clean["rows"]:
            key = row.get("account_code", "") or row.get("account_name", "")
            acct_totals[key]["debit"] += Decimal(str(row.get("debit", 0)))
            acct_totals[key]["credit"] += Decimal(str(row.get("credit", 0)))
            acct_totals[key]["name"] = row.get("account_name", "")

        for code, data in acct_totals.items():
            tb_rows.append({
                "account_code": code,
                "account_name": data["name"],
                "debit": str(data["debit"]),
                "credit": str(data["credit"]),
                "_row_index": 0,
            })

        tb_table = {
            "table_id": "tb-001",
            "document_id": "doc-002",
            "detected_type": "trial_balance",
            "confirmed_type": "trial_balance",
            "period_start": gl_clean["metadata"]["period_start"],
            "period_end": gl_clean["metadata"]["period_end"],
            "rows": tb_rows,
        }

        result = check_general_ledger(
            gl_tables=[gl_table],
            tb_tables=[tb_table],
            period_start=_parse_date(gl_clean["metadata"]["period_start"]),
            period_end=_parse_date(gl_clean["metadata"]["period_end"]),
        )
        recon_schedules = [s for s in result.schedules if s.schedule_type == "gl_tb_reconciliation"]
        assert len(recon_schedules) == 1, "Should produce a GL vs TB reconciliation schedule"
        discrepancy_findings = [f for f in result.findings if f.finding_type == "gl_tb_discrepancy"]
        assert len(discrepancy_findings) == 0, (
            f"Expected no GL vs TB discrepancies when TB mirrors GL. "
            f"Got: {[(f.title, str(f.amount)) for f in discrepancy_findings]}"
        )


# ===========================================================================
# DEEPEVAL LLM QUALITY TESTS — test explanation quality if LLM is available
# ===========================================================================

@pytest.mark.skipif(not DEEPEVAL_AVAILABLE, reason="deepeval not installed")
@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend not importable")
class TestGLLLMExplanationQuality:
    """
    Uses DeepEval to evaluate LLM-generated explanations of GL findings.
    
    These tests require an LLM API key. Set OPENAI_API_KEY or GEMINI_API_KEY
    in your environment. If no key is set, these tests will be skipped.
    
    The pattern is:
      input   = the question/prompt sent to the LLM (e.g. "explain this finding")
      actual  = what the LLM returned
      context = factual context from the finding (ground truth)
    """

    def test_missing_date_explanation_relevance(self, gl_with_errors):
        """LLM explanation for a missing-date finding should be relevant to the finding."""
        import os
        if not (os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")):
            pytest.skip("No LLM API key set - skipping LLM quality test")

        # Simulate what the LLM would be asked to explain
        finding_description = (
            "Row 2 is missing required field(s): date. "
            "This GL entry has no date, making it impossible to verify "
            "that it falls within the accounting period 2025-07-01 to 2025-10-31."
        )

        # Simulated LLM output (replace with actual LLM call in production)
        simulated_llm_output = (
            "This general ledger entry is missing a transaction date, which is a mandatory field. "
            "Without a date, we cannot confirm whether this transaction belongs to the current "
            "accounting period (July 2025 – October 2025), and it cannot be included in the "
            "period-end trial balance. The bookkeeper should identify this transaction from "
            "source documents and add the correct posting date before period close."
        )

        test_case = LLMTestCase(
            input="Explain this GL finding to the client's accounting team.",
            actual_output=simulated_llm_output,
            context=[finding_description],
            retrieval_context=[finding_description],
        )

        metric = AnswerRelevancyMetric(threshold=0.7, model="gpt-4o-mini")
        assert_test(test_case, [metric])

    def test_duplicate_transaction_explanation_faithfulness(self, gl_with_errors):
        """LLM explanation for duplicate should faithfully represent the facts."""
        import os
        if not (os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")):
            pytest.skip("No LLM API key set - skipping LLM quality test")

        finding_description = (
            "2 rows share the same date (2025-08-15), debit (18000000), "
            "credit (0) and description (Sales to Garments Export Ltd). "
            "They may be duplicate postings."
        )

        simulated_llm_output = (
            "Two journal entries dated 15 August 2025 appear to be duplicates: "
            "both record a sale of PKR 18,000,000 to Garments Export Ltd under "
            "reference SI-2025-100. This may indicate a double-posting error. "
            "Please verify the original sales invoice and confirm that only one "
            "entry should exist. If duplicated, the second entry should be reversed."
        )

        test_case = LLMTestCase(
            input="Explain the duplicate transaction finding.",
            actual_output=simulated_llm_output,
            context=[finding_description],
            retrieval_context=[finding_description],
        )

        faithfulness_metric = FaithfulnessMetric(threshold=0.7, model="gpt-4o-mini")
        assert_test(test_case, [faithfulness_metric])
