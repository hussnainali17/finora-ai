"""Deterministic Pakistan Sales Tax & Provincial Services Calculation Service.

Covers:
- Federal Sales Tax on Goods (Sales Tax Act, 1990 - 18% standard)
- Section 8B Input Tax Adjustment Restriction (90% ceiling)
- Provincial Sales Tax on Services (PRA 16%, SRB 13%, KPRA 15%, BRA 15%, ICT 15%)
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.taxation.rules.rates import (
    BRA_STANDARD_SERVICE_RATE,
    ICT_STANDARD_SERVICE_RATE,
    KPRA_STANDARD_SERVICE_RATE,
    PRA_STANDARD_SERVICE_RATE,
    SALES_TAX_INPUT_CAP_PERCENT,
    SALES_TAX_RATE_GOODS,
    SRB_STANDARD_SERVICE_RATE,
)

TWO_PLACES = Decimal("0.01")


def _d(val: Any) -> Decimal:
    if val is None or val == "":
        return Decimal("0.00")
    return Decimal(str(val))


def _round(val: Decimal) -> Decimal:
    return val.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def compute_sales_tax(
    *,
    taxable_supplies: Decimal | float | int,
    admissible_purchases: Decimal | float | int,
    provincial_service_turnover: Decimal | float | int = Decimal("0"),
    province: str = "federal",
    tax_rate_override: Decimal | float | None = None,
) -> dict[str, Any]:
    """Computes Federal & Provincial Sales Tax deterministically using Decimal."""
    supplies = _round(_d(taxable_supplies))
    purchases = _round(_d(admissible_purchases))
    services_turnover = _round(_d(provincial_service_turnover))

    # Output Tax on Goods
    rate_goods = _d(tax_rate_override) if tax_rate_override is not None else SALES_TAX_RATE_GOODS
    output_tax_goods = _round(supplies * rate_goods)

    # Input Tax on Goods
    raw_input_tax = _round(purchases * rate_goods)

    # Section 8B: 90% limitation
    input_cap = _round(output_tax_goods * SALES_TAX_INPUT_CAP_PERCENT)
    admissible_input_tax = min(raw_input_tax, input_cap)
    carried_forward_input_tax = _round(raw_input_tax - admissible_input_tax)

    # Net Federal Sales Tax
    net_federal_payable = _round(output_tax_goods - admissible_input_tax)

    # Provincial Sales Tax on Services
    prov_rate = Decimal("0.00")
    prov_authority = "Federal / None"
    prov_lower = province.lower()

    if prov_lower in ("pra", "punjab"):
        prov_rate = PRA_STANDARD_SERVICE_RATE
        prov_authority = "PRA (Punjab)"
    elif prov_lower in ("srb", "sindh"):
        prov_rate = SRB_STANDARD_SERVICE_RATE
        prov_authority = "SRB (Sindh)"
    elif prov_lower in ("kpra", "kp", "kpk"):
        prov_rate = KPRA_STANDARD_SERVICE_RATE
        prov_authority = "KPRA (Khyber Pakhtunkhwa)"
    elif prov_lower in ("bra", "balochistan"):
        prov_rate = BRA_STANDARD_SERVICE_RATE
        prov_authority = "BRA (Balochistan)"
    elif prov_lower in ("ict", "islamabad"):
        prov_rate = ICT_STANDARD_SERVICE_RATE
        prov_authority = "ICT (Islamabad)"

    provincial_output_tax = _round(services_turnover * prov_rate)

    total_sales_tax_liability = _round(net_federal_payable + provincial_output_tax)

    return {
        "taxable_supplies": float(supplies),
        "admissible_purchases": float(purchases),
        "output_tax_goods": float(output_tax_goods),
        "rate_goods": float(rate_goods),
        "raw_input_tax": float(raw_input_tax),
        "section_8b_cap": float(input_cap),
        "admissible_input_tax": float(admissible_input_tax),
        "carried_forward_input_tax": float(carried_forward_input_tax),
        "net_federal_payable": float(net_federal_payable),
        "provincial_authority": prov_authority,
        "provincial_services_turnover": float(services_turnover),
        "provincial_rate": float(prov_rate),
        "provincial_output_tax": float(provincial_output_tax),
        "total_sales_tax_payable": float(total_sales_tax_liability),
    }
