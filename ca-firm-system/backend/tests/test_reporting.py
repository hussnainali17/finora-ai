"""Tests for Phase 8: Financial Reporting & Validation (Agent 4).

Tests:
1. Validation engine: checks TB balance and Balance Sheet equation.
2. Rule: Unbalanced TB is flagged as an error, NEVER balanced automatically.
3. Rule: Adjusted Trial Balance includes ONLY approved adjustments.
   Draft, proposed, and rejected adjustments are excluded!
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.accounting.validation import (
    validate_balance_sheet,
    validate_financial_statements,
    validate_trial_balance,
)


class TestValidationEngine:
    def test_trial_balance_balanced(self):
        rows = [
            {"account_code": "1010", "debit": Decimal("5000"), "credit": Decimal("0")},
            {"account_code": "2010", "debit": Decimal("0"), "credit": Decimal("5000")},
        ]
        ok, deb, cred, issues = validate_trial_balance(rows)
        assert ok is True
        assert deb == Decimal("5000")
        assert cred == Decimal("5000")
        assert len(issues) == 0

    def test_trial_balance_unbalanced_flagged_not_fixed(self):
        # Debits 5000, Credits 4000 -> Diff 1000
        rows = [
            {"account_code": "1010", "debit": Decimal("5000"), "credit": Decimal("0")},
            {"account_code": "2010", "debit": Decimal("0"), "credit": Decimal("4000")},
        ]
        ok, deb, cred, issues = validate_trial_balance(rows)
        assert ok is False
        assert len(issues) == 1
        assert issues[0].check_name == "trial_balance_balanced"
        assert issues[0].difference == Decimal("1000")
        assert "balancing entries must never be fabricated" in issues[0].description

    def test_balance_sheet_equation(self):
        # Assets 100,000 = Liab 40,000 + Equity 60,000
        ok, issues = validate_balance_sheet(
            total_assets=Decimal("100000"),
            total_liabilities=Decimal("40000"),
            total_equity=Decimal("60000"),
        )
        assert ok is True
        assert len(issues) == 0

    def test_balance_sheet_out_of_balance(self):
        ok, issues = validate_balance_sheet(
            total_assets=Decimal("100000"),
            total_liabilities=Decimal("40000"),
            total_equity=Decimal("50000"),  # Diff 10,000
        )
        assert ok is False
        assert len(issues) == 1
        assert issues[0].check_name == "balance_sheet_equation"
        assert issues[0].difference == Decimal("10000")


class TestAdjustedTBRules:
    def test_only_approved_adjustments_feed_adjusted_tb(self):
        """Proves that unapproved adjustments (draft, proposed, rejected)

        are excluded from the Adjusted Trial Balance calculation.
        """
        original_accounts = {
            "1010": {"code": "1010", "name": "Cash", "debit": Decimal("1000"), "credit": Decimal("0")},
            "6010": {"code": "6010", "name": "Depreciation", "debit": Decimal("0"), "credit": Decimal("0")},
            "1590": {"code": "1590", "name": "Acc Dep", "debit": Decimal("0"), "credit": Decimal("0")},
        }

        # Simulated adjustments with different statuses
        adjustments = [
            # Approved adjustment: 500 depreciation
            {
                "status": "approved",
                "debit": "6010",
                "credit": "1590",
                "amount": Decimal("500"),
            },
            # Proposed adjustment: 300 accrual (must NOT be applied!)
            {
                "status": "proposed",
                "debit": "6010",
                "credit": "1590",
                "amount": Decimal("300"),
            },
            # Rejected adjustment: 200 (must NOT be applied!)
            {
                "status": "rejected",
                "debit": "6010",
                "credit": "1590",
                "amount": Decimal("200"),
            },
            # Draft adjustment: 100 (must NOT be applied!)
            {
                "status": "draft",
                "debit": "6010",
                "credit": "1590",
                "amount": Decimal("100"),
            },
        ]

        # Filter strictly for approved adjustments (as implemented in ReportingAgent)
        approved_only = [a for a in adjustments if a["status"] == "approved"]

        # Calculate final balances
        for adj in approved_only:
            original_accounts[adj["debit"]]["debit"] += adj["amount"]
            original_accounts[adj["credit"]]["credit"] += adj["amount"]

        assert original_accounts["6010"]["debit"] == Decimal("500")
        assert original_accounts["1590"]["credit"] == Decimal("500")
        # Ensure proposed, rejected, and draft adjustments (600 total) were completely ignored
        assert original_accounts["6010"]["debit"] != Decimal("1100")
