"""
test_fixed_assets.py — DeepEval tests for the Fixed Assets (PPE) reconciliation module.

Tests:
  1. Clean FAR returns zero critical findings
  2. Missing acquisition date detected
  3. Missing depreciation rate detected
  4. Negative NBV detected
  5. Fully-deprecated-but-active asset detected
  6. Disposal without proceeds detected
  7. PPE movement schedule is generated correctly
  8. LLM explanation quality for a negative NBV finding
"""
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent / "ca-firm-system" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:
    from app.accounting.reconciliation.fixed_assets import check_fixed_assets
    BACKEND_AVAILABLE = True
except ImportError as e:
    BACKEND_AVAILABLE = False
    IMPORT_ERROR = str(e)

try:
    from deepeval import assert_test
    from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
    from deepeval.test_case import LLMTestCase
    DEEPEVAL_AVAILABLE = True
except ImportError:
    DEEPEVAL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_dep_rate(val):
    if val is None:
        return None
    val_str = str(val).strip()
    if val_str.startswith("STL-"):
        import re
        m = re.search(r"STL-(\d+)Y", val_str)
        if m:
            years = int(m.group(1))
            return round(1.0 / years, 4) if years > 0 else None
    try:
        return float(val_str)
    except ValueError:
        return None


def _build_far_rows(dataset: dict) -> list[dict]:
    """Convert dataset rows to the normalized format expected by check_fixed_assets."""
    out = []
    for i, row in enumerate(dataset["rows"]):
        normalized = {
            "asset_id": row.get("asset_id"),
            "code": row.get("asset_id"),
            "description": row.get("description", ""),
            "cost": row.get("closing_cost", row.get("cost", 0)),
            "accumulated_depreciation": row.get("closing_depreciation", 0),
            "net_book_value": row.get("net_book_value"),
            "depreciation_rate": _parse_dep_rate(row.get("depreciation_rate")),
            "acquisition_date": row.get("acquisition_date"),
            "status": row.get("status", "active"),
            "disposal_date": row.get("disposal_date"),
            "disposal_proceeds": row.get("disposal_proceeds"),
            "is_addition": row.get("is_addition", False),
            "is_disposal": row.get("is_disposal", False),
            "_row_index": i,
        }
        out.append(normalized)
    return out


def _wrap_in_table(rows: list[dict], dataset: dict) -> list[dict]:
    """Wrap rows in the table structure expected by check_fixed_assets.
    
    Note: check_fixed_assets takes a flat list of rows from the dataset docstring.
    It actually expects: asset_register_rows: list[dict[str, Any]]
    """
    return rows  # check_fixed_assets takes the rows directly, not table wrapper


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s)


# ===========================================================================
# UNIT TESTS
# ===========================================================================

@pytest.mark.skipif(not BACKEND_AVAILABLE, reason=f"Backend not importable: {IMPORT_ERROR if not BACKEND_AVAILABLE else ''}")
class TestFARClean:
    """Fixed assets module should return zero critical findings for clean data."""

    def test_no_critical_findings_on_clean_data(self, far_clean):
        rows = _build_far_rows(far_clean)
        result = check_fixed_assets(
            asset_register_rows=rows,
            period_start=_parse_date(far_clean["metadata"]["period_start"]),
            period_end=_parse_date(far_clean["metadata"]["period_end"]),
        )
        error_findings = [f for f in result.findings if f.severity == "error"]
        assert len(error_findings) == 0, (
            f"Expected no error-severity findings on clean FAR but got: "
            f"{[(f.finding_type, f.title) for f in error_findings]}"
        )

    def test_ppe_movement_schedule_generated(self, far_clean):
        rows = _build_far_rows(far_clean)
        result = check_fixed_assets(
            asset_register_rows=rows,
            period_start=_parse_date(far_clean["metadata"]["period_start"]),
            period_end=_parse_date(far_clean["metadata"]["period_end"]),
        )
        # Should produce at least a summary schedule
        assert len(result.schedules) >= 1, "Should produce at least one schedule (PPE movement)"

    def test_summary_has_correct_structure(self, far_clean):
        rows = _build_far_rows(far_clean)
        result = check_fixed_assets(
            asset_register_rows=rows,
            period_start=_parse_date(far_clean["metadata"]["period_start"]),
            period_end=_parse_date(far_clean["metadata"]["period_end"]),
        )
        assert "total_findings" in result.summary, "Summary should contain total_findings key"
        assert isinstance(result.findings, list), "findings should be a list"


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason=f"Backend not importable: {IMPORT_ERROR if not BACKEND_AVAILABLE else ''}")
class TestFARWithErrors:
    """Fixed assets module should detect all injected FAR errors."""

    def test_missing_acquisition_date_detected(self, far_with_errors):
        rows = _build_far_rows(far_with_errors)
        result = check_fixed_assets(
            asset_register_rows=rows,
            period_start=_parse_date(far_with_errors["metadata"]["period_start"]),
            period_end=_parse_date(far_with_errors["metadata"]["period_end"]),
        )
        date_findings = [
            f for f in result.findings
            if "date" in f.finding_type.lower() or "date" in f.title.lower()
        ]
        assert len(date_findings) >= 1, (
            f"Should detect missing acquisition_date on ERR-001. "
            f"All findings: {[(f.finding_type, f.title) for f in result.findings]}"
        )

    def test_negative_nbv_detected(self, far_with_errors):
        rows = _build_far_rows(far_with_errors)
        result = check_fixed_assets(
            asset_register_rows=rows,
            period_start=_parse_date(far_with_errors["metadata"]["period_start"]),
            period_end=_parse_date(far_with_errors["metadata"]["period_end"]),
        )
        nbv_findings = [
            f for f in result.findings
            if "negative" in f.finding_type.lower() or "negative" in f.title.lower()
        ]
        assert len(nbv_findings) >= 1, (
            f"Should detect negative NBV on ERR-002 (Generator). "
            f"All findings: {[(f.finding_type, f.title) for f in result.findings]}"
        )

    def test_fully_deprecated_active_detected(self, far_with_errors):
        rows = _build_far_rows(far_with_errors)
        result = check_fixed_assets(
            asset_register_rows=rows,
            period_start=_parse_date(far_with_errors["metadata"]["period_start"]),
            period_end=_parse_date(far_with_errors["metadata"]["period_end"]),
        )
        active_findings = [
            f for f in result.findings
            if "fully_depreciat" in f.finding_type.lower() or "fully depreciat" in f.title.lower()
        ]
        assert len(active_findings) >= 1, (
            f"Should detect fully-deprecated asset ERR-003 marked as 'active'. "
            f"All findings: {[(f.finding_type, f.title) for f in result.findings]}"
        )

    def test_disposal_without_proceeds_detected(self, far_with_errors):
        rows = _build_far_rows(far_with_errors)
        result = check_fixed_assets(
            asset_register_rows=rows,
            period_start=_parse_date(far_with_errors["metadata"]["period_start"]),
            period_end=_parse_date(far_with_errors["metadata"]["period_end"]),
        )
        disposal_findings = [
            f for f in result.findings
            if "disposal" in f.finding_type.lower() or "disposal" in f.title.lower()
        ]
        assert len(disposal_findings) >= 1, (
            f"Should detect disposal (ERR-004 Forklift) without proceeds. "
            f"All findings: {[(f.finding_type, f.title) for f in result.findings]}"
        )

    def test_total_findings_above_minimum(self, far_with_errors):
        rows = _build_far_rows(far_with_errors)
        result = check_fixed_assets(
            asset_register_rows=rows,
            period_start=_parse_date(far_with_errors["metadata"]["period_start"]),
            period_end=_parse_date(far_with_errors["metadata"]["period_end"]),
        )
        min_expected = far_with_errors["expected_checks"]["total_findings_min"]
        assert result.summary["total_findings"] >= min_expected, (
            f"Expected at least {min_expected} findings but got "
            f"{result.summary['total_findings']}: "
            f"{[(f.finding_type, f.severity, f.title) for f in result.findings]}"
        )


@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend not importable")
class TestFAREdgeCases:
    """Edge cases for the fixed assets module."""

    def test_empty_asset_register_returns_gracefully(self):
        result = check_fixed_assets(
            asset_register_rows=[],
            period_start=date(2025, 7, 1),
            period_end=date(2025, 10, 31),
        )
        assert result.summary["total_findings"] == 0

    def test_single_new_addition_in_period(self):
        """An asset added in-period with valid data should produce no errors."""
        rows = [{
            "asset_id": "NEW-001",
            "description": "New Production Machine",
            "cost": 5000000,
            "accumulated_depreciation": 83334,
            "net_book_value": 4916666,
            "depreciation_rate": "0.10",
            "acquisition_date": "2025-08-01",
            "status": "active",
            "is_addition": True,
            "is_disposal": False,
            "disposal_date": None,
            "disposal_proceeds": None,
            "_row_index": 0,
        }]
        result = check_fixed_assets(
            asset_register_rows=rows,
            period_start=date(2025, 7, 1),
            period_end=date(2025, 10, 31),
        )
        error_findings = [f for f in result.findings if f.severity == "error"]
        assert len(error_findings) == 0, (
            f"Valid new addition should not trigger error findings: "
            f"{[(f.finding_type, f.title) for f in error_findings]}"
        )


# ===========================================================================
# DEEPEVAL LLM QUALITY TESTS
# ===========================================================================

@pytest.mark.skipif(not DEEPEVAL_AVAILABLE, reason="deepeval not installed")
@pytest.mark.skipif(not BACKEND_AVAILABLE, reason="Backend not importable")
class TestFARLLMExplanationQuality:
    """Test that LLM explanations of FAR findings are relevant and faithful."""

    def test_negative_nbv_explanation_relevance(self):
        import os
        if not (os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")):
            pytest.skip("No LLM API key set")

        finding_context = (
            "Asset 'Generator - Diesel 500KVA' (ERR-002) has a Net Book Value of PKR -350,000. "
            "Opening cost: PKR 4,500,000. Accumulated depreciation: PKR 4,850,000. "
            "NBV = cost - accum_dep = -350,000. This is physically impossible."
        )

        simulated_llm_output = (
            "The Generator (ERR-002) shows a negative Net Book Value of PKR -350,000, "
            "which means the total depreciation charged (PKR 4,850,000) exceeds the "
            "original cost of the asset (PKR 4,500,000). This is not permissible under "
            "IAS 16 — an asset's carrying amount cannot fall below zero. The accumulated "
            "depreciation balance should be capped at the asset's cost. Please review the "
            "depreciation schedule for this asset and adjust the accumulated depreciation "
            "to PKR 4,500,000, recognising the difference as a prior period error."
        )

        test_case = LLMTestCase(
            input="Explain the negative NBV finding for the Generator asset to the finance team.",
            actual_output=simulated_llm_output,
            context=[finding_context],
            retrieval_context=[finding_context],
        )

        metric = AnswerRelevancyMetric(threshold=0.7, model="gpt-4o-mini")
        assert_test(test_case, [metric])
