"""Versioned Pakistan Tax Rates and Statutory Rule Sets.

Primary Source Families:
- Income Tax Ordinance, 2001 (amended by Finance Act 2024 & 2025)
- Sales Tax Act, 1990
- Provincial Sales Tax on Services Acts (PRA 2012, SRB 2011, KPRA 2013, BRA 2015)
- FBR Withholding Tax Rate Cards
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

# Rule set identifiers
RULE_SET_TY2025 = "ITO2001_TY2025_FA2024"
RULE_SET_TY2024 = "ITO2001_TY2024_FA2023"

# Corporate Tax Rates
CORPORATE_TAX_RATE_TY2025 = Decimal("0.29")  # 29% normal corporate tax
CORPORATE_TAX_RATE_TY2024 = Decimal("0.29")
SMALL_COMPANY_TAX_RATE = Decimal("0.20")     # 20% small company

# Minimum Tax under Section 113
MINIMUM_TAX_RATE_DEFAULT = Decimal("0.0125")  # 1.25% of turnover

# Alternate Corporate Tax under Section 113C
ACT_TAX_RATE = Decimal("0.17")  # 17% of accounting profit

# Standard Sales Tax on Goods
SALES_TAX_RATE_GOODS = Decimal("0.18")  # 18% standard sales tax
SALES_TAX_INPUT_CAP_PERCENT = Decimal("0.90")  # Section 8B 90% input tax adjustment limit

# Provincial Services Rates
PRA_STANDARD_SERVICE_RATE = Decimal("0.16")  # Punjab 16%
SRB_STANDARD_SERVICE_RATE = Decimal("0.13")  # Sindh 13%
KPRA_STANDARD_SERVICE_RATE = Decimal("0.15")  # KP 15%
BRA_STANDARD_SERVICE_RATE = Decimal("0.15")   # Balochistan 15%
ICT_STANDARD_SERVICE_RATE = Decimal("0.15")   # Islamabad 15%

# Section 4C Super Tax Slabs (Finance Act 2024)
# Threshold (Rs) -> Rate
SUPER_TAX_SLABS_TY2025 = [
    (Decimal("150000000"), Decimal("0.00")),
    (Decimal("200000000"), Decimal("0.01")),
    (Decimal("250000000"), Decimal("0.02")),
    (Decimal("300000000"), Decimal("0.03")),
    (Decimal("350000000"), Decimal("0.04")),
    (Decimal("400000000"), Decimal("0.06")),
    (Decimal("500000000"), Decimal("0.08")),
    (Decimal("999999999999999"), Decimal("0.10")),
]

# Section 22 / Third Schedule Tax Depreciation Rates
TAX_DEPRECIATION_RATES: dict[str, Decimal] = {
    "building": Decimal("0.10"),          # Buildings 10%
    "plant_machinery": Decimal("0.15"),   # Plant and Machinery 15%
    "furniture": Decimal("0.15"),         # Furniture & fittings 15%
    "motor_vehicles": Decimal("0.15"),    # Motor vehicles 15%
    "computer_equipment": Decimal("0.30"),# Computer equipment 30%
}
INITIAL_ALLOWANCE_RATE = Decimal("0.25")  # Section 23: 25% initial allowance on eligible plant & machinery


def resolve_super_tax_rate(income: Decimal, tax_year: int = 2025) -> tuple[Decimal, str]:
    """Resolves applicable Super Tax rate under Section 4C."""
    slabs = SUPER_TAX_SLABS_TY2025
    prev_limit = Decimal("0")
    for limit, rate in slabs:
        if income <= limit:
            citation = f"Section 4C, First Schedule Division IIB (Income between {prev_limit:,.0f} and {limit:,.0f})"
            return rate, citation
        prev_limit = limit

    return Decimal("0.10"), "Section 4C (Income exceeding 500M: 10% rate)"


def resolve_rule_set(tax_year: int) -> dict[str, Any]:
    """Returns the effective-dated tax parameters for a given tax year."""
    if tax_year >= 2025:
        return {
            "version": RULE_SET_TY2025,
            "corporate_rate": CORPORATE_TAX_RATE_TY2025,
            "minimum_tax_rate": MINIMUM_TAX_RATE_DEFAULT,
            "act_rate": ACT_TAX_RATE,
            "sales_tax_rate": SALES_TAX_RATE_GOODS,
            "input_tax_cap": SALES_TAX_INPUT_CAP_PERCENT,
        }
    return {
        "version": RULE_SET_TY2024,
        "corporate_rate": CORPORATE_TAX_RATE_TY2024,
        "minimum_tax_rate": MINIMUM_TAX_RATE_DEFAULT,
        "act_rate": ACT_TAX_RATE,
        "sales_tax_rate": SALES_TAX_RATE_GOODS,
        "input_tax_cap": SALES_TAX_INPUT_CAP_PERCENT,
    }
