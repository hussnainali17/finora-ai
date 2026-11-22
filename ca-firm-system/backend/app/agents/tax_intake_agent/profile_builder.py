"""Taxpayer Profile verification and missing information analyzer.

Enforces:
- Hard rule: NEVER invent a registration, NTN, STRN, or taxpayer fact.
- Validates NTN and STRN formats.
- Identifies missing required tax inputs and formats questions for client / staff.
"""

from __future__ import annotations

import re
from typing import Any
import uuid


def validate_ntn(ntn: str) -> tuple[bool, str]:
    """Validates Pakistani National Tax Number (7 digits with optional check digit: 1234567-8)."""
    cleaned = ntn.replace("-", "").strip()
    if not (7 <= len(cleaned) <= 8 and cleaned.isdigit()):
        return False, f"NTN '{ntn}' is not in valid Pakistan 7-8 digit format."
    return True, cleaned


def validate_strn(strn: str | None) -> tuple[bool, str]:
    """Validates Pakistani Sales Tax Registration Number (13 digits: 12-34-5678-901-23)."""
    if not strn or not strn.strip():
        return True, ""
    cleaned = strn.replace("-", "").strip()
    if not (cleaned.isdigit() and len(cleaned) in (13, 14)):
        return False, f"STRN '{strn}' is not in valid Pakistan 13-digit format."
    return True, cleaned


def analyze_profile_completeness(
    *,
    legal_form: str,
    ntn: str,
    strn: str | None,
    business_sector: str,
    principal_activity: str,
    registered_branches: list[dict[str, Any]],
    jurisdictions: list[str],
    has_prior_returns: bool = False,
    has_tax_payment_evidence: bool = False,
) -> list[dict[str, Any]]:
    """Analyzes taxpayer facts and generates missing information questions."""
    missing: list[dict[str, Any]] = []

    # 1. NTN Check
    is_valid_ntn, ntn_err = validate_ntn(ntn)
    if not is_valid_ntn:
        missing.append({
            "query_id": str(uuid.uuid4())[:8],
            "field": "ntn",
            "question": f"Invalid NTN format ({ntn}). Please supply the official 7-digit NTN as per FBR Taxpayer Profile Inquiry.",
            "severity": "critical",
            "statutory_basis": "Income Tax Ordinance 2001, Section 181",
        })

    # 2. STRN check for commercial/trading/manufacturing
    activity_lower = (principal_activity + " " + business_sector).lower()
    requires_strn = any(
        kw in activity_lower
        for kw in ("trading", "commercial", "manufacturing", "wholesale", "import", "goods")
    )
    if requires_strn and not strn:
        missing.append({
            "query_id": str(uuid.uuid4())[:8],
            "field": "strn",
            "question": "Business activity involves supply/manufacture of goods but no STRN is registered. Please provide STRN or confirm exemption status under Sixth Schedule of Sales Tax Act 1990.",
            "severity": "warning",
            "statutory_basis": "Sales Tax Act 1990, Section 14",
        })
    elif strn:
        is_valid_strn, strn_err = validate_strn(strn)
        if not is_valid_strn:
            missing.append({
                "query_id": str(uuid.uuid4())[:8],
                "field": "strn",
                "question": f"Invalid STRN format ({strn}). Please provide the 13-digit Sales Tax Registration Number.",
                "severity": "critical",
                "statutory_basis": "Sales Tax Act 1990, Section 14",
            })

    # 3. Provincial Jurisdictions and registered branches
    if not jurisdictions:
        missing.append({
            "query_id": str(uuid.uuid4())[:8],
            "field": "jurisdictions",
            "question": "No tax jurisdiction specified. Please confirm provincial operations (Federal, PRA-Punjab, SRB-Sindh, KPRA-KPK, BRA-Balochistan).",
            "severity": "warning",
            "statutory_basis": "Provincial Sales Tax on Services Acts",
        })

    if not registered_branches:
        missing.append({
            "query_id": str(uuid.uuid4())[:8],
            "field": "registered_branches",
            "question": "Registered branches / locations list is empty. Please provide principal place of business address.",
            "severity": "info",
            "statutory_basis": "FBR Taxpayer Registration Rules",
        })

    # 4. Tax history evidence
    if not has_prior_returns:
        missing.append({
            "query_id": str(uuid.uuid4())[:8],
            "field": "prior_year_returns",
            "question": "Prior year tax return and computation workpapers not uploaded. Upload prior returns to verify unabsorbed depreciation and loss carry-forwards (Section 57).",
            "severity": "info",
            "statutory_basis": "Income Tax Ordinance 2001, Section 57",
        })

    if not has_tax_payment_evidence:
        missing.append({
            "query_id": str(uuid.uuid4())[:8],
            "field": "tax_challans",
            "question": "No tax payment challans (CPRs) uploaded for withholding or advance tax under Section 147.",
            "severity": "warning",
            "statutory_basis": "Income Tax Ordinance 2001, Section 147 & 168",
        })

    return missing
