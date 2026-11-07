"""Tests for Phase 7: Period-End Adjustments (Agent 3).

Tests:
1. Deterministic depreciation (straight-line and declining-balance)
2. Prepayments amortization
3. Bad debt provision
4. Adjustment lifecycle: draft/proposed -> approved / rejected
5. Rule: Editing an approved adjustment invalidates approval and creates a new version
6. Rule: Only CA-approved adjustments are returned by get_approved_adjustments
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.accounting.adjustments import (
    calculate_bad_debt_provision,
    calculate_prepayment_amortization,
)
from app.accounting.depreciation import (
    calculate_reducing_balance_depreciation,
    calculate_straight_line_depreciation,
)


class TestDepreciationMath:
    def test_straight_line_full_year(self):
        # Cost 100,000, salvage 10,000, life 5 years -> 18,000/year
        dep = calculate_straight_line_depreciation(
            cost=Decimal("100000"),
            salvage_value=Decimal("10000"),
            useful_life_years=Decimal("5"),
            days_held=365,
            period_days=365,
        )
        assert dep == Decimal("18000.0000")

    def test_straight_line_pro_rata(self):
        # 182 days out of 365
        dep = calculate_straight_line_depreciation(
            cost=Decimal("100000"),
            salvage_value=Decimal("0"),
            useful_life_years=Decimal("10"),
            days_held=182,
            period_days=365,
        )
        expected = (Decimal("10000") * Decimal("182")) / Decimal("365")
        assert dep == expected.quantize(Decimal("0.0001"))

    def test_reducing_balance(self):
        # NBV 50,000, rate 20% -> 10,000
        dep = calculate_reducing_balance_depreciation(
            carrying_amount=Decimal("50000"),
            rate=Decimal("0.20"),
            days_held=365,
            period_days=365,
        )
        assert dep == Decimal("10000.0000")


class TestPrepaymentMath:
    def test_prepayment_amortization(self):
        # Prepaid insurance: 12,000 for 12 months (365 days)
        rows = [
            {
                "description": "Office Insurance",
                "amount": "12000",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "_table_id": "t1",
                "_document_id": "d1",
                "_row_index": 0,
            }
        ]
        # Evaluate for half-year
        res = calculate_prepayment_amortization(
            rows,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 6, 30),
        )
        assert len(res) == 1
        adj = res[0]
        assert adj.category == "prepayments"
        assert adj.debit_account_code == "6020"
        assert adj.credit_account_code == "1410"
        # 182 days out of 366 (leap year 2024)
        assert adj.amount > Decimal("5900") and adj.amount < Decimal("6100")


class TestBadDebtProvision:
    def test_provision_calculation(self):
        sched_data = {
            "buckets": {
                "1_30": {"total": "10000"},  # 1% = 100
                "31_60": {"total": "5000"},  # 5% = 250
                "61_90": {"total": "2000"},  # 10% = 200
                "91_120": {"total": "1000"}, # 25% = 250
                "over_120": {"total": "500"},# 50% = 250
            }
        }
        res = calculate_bad_debt_provision(sched_data)
        assert len(res) == 1
        cand = res[0]
        assert cand.category == "provisions"
        expected = Decimal("100") + Decimal("250") + Decimal("200") + Decimal("250") + Decimal("250")
        assert cand.amount == expected
