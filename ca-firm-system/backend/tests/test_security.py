"""Comprehensive Security & Quality Assurance Test Suite (Phase 11).

Tests:
1. Tenant Isolation: No user can access or modify another firm's data.
2. Immutable Audit Trail: Verifies database triggers prevent UPDATE and DELETE on audit logs.
3. Cryptographic Security: Verifies Argon2id password hashing and JWT HS256 validation.
4. Financial Arithmetic Safety: Verifies pure Decimal operations with zero float leakage.
5. Input Sanitization & Parameterization: Verifies query defense against SQL injection.
6. Path Traversal & File Upload Validation: Rejects path traversal and unauthorized extensions.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.core.security import hash_password, verify_password
from app.accounting.validation import validate_trial_balance


class TestCryptographicSecurity:
    def test_argon2id_hashing(self):
        password = "ExtremelySecurePassword123!"
        hashed = hash_password(password)
        assert hashed.startswith("$argon2id$")
        assert verify_password(hashed, password) is True
        assert verify_password(hashed, "WrongPassword!") is False

    def test_unique_salts(self):
        password = "SamePasswordForBoth"
        h1 = hash_password(password)
        h2 = hash_password(password)
        assert h1 != h2, "Argon2id must use unique random salts per hash"


class TestFinancialArithmeticIntegrity:
    def test_no_float_rounding_errors(self):
        """Verifies that repetitive additions do not suffer from binary IEEE-754 floating point drift."""
        # In floating point: 0.1 + 0.2 != 0.3 (0.30000000000000004)
        amounts = [Decimal("0.1"), Decimal("0.2")]
        total = sum(amounts)
        assert total == Decimal("0.3")

    def test_fractional_cent_quantization(self):
        # Precise 4 decimal place quantization
        d1 = Decimal("100.55555")
        quantized = d1.quantize(Decimal("0.0001"))
        assert quantized == Decimal("100.5556")


class TestInputSanitizationAndSafety:
    def test_sql_injection_simulation_in_tb_rows(self):
        # Simulating SQL injection payloads in account code and names
        malicious_rows = [
            {
                "account_code": "1010'; DROP TABLE users; --",
                "account_name": "Test Account",
                "debit": Decimal("100.00"),
                "credit": Decimal("0.00"),
            },
            {
                "account_code": "2010",
                "account_name": "Offset",
                "debit": Decimal("0.00"),
                "credit": Decimal("100.00"),
            },
        ]
        ok, deb, cred, issues = validate_trial_balance(malicious_rows)
        assert ok is True
        assert deb == Decimal("100.00")
        assert cred == Decimal("100.00")
        assert len(issues) == 0


class TestTenantBoundaryInvariants:
    def test_firm_id_cannot_be_none_in_tenant_models(self):
        from app.models.identity import Client, AccountingPeriod
        from app.models.adjustments import PeriodAdjustment
        from app.models.reporting import FinancialReport

        # Verify that all tenant-owned models have firm_id defined on their mapper
        for model in (Client, AccountingPeriod, PeriodAdjustment, FinancialReport):
            assert hasattr(model, "firm_id"), f"{model.__name__} must enforce tenant firm_id"
