"""Pakistan statutory tax obligations determination engine.

Resolves statutory obligations under:
- Income Tax Ordinance, 2001 (Federal Income Tax, Super Tax s.4C, Minimum Tax s.113, ACT s.113C)
- Withholding Income Tax regime (Part V of Chapter X, Sections 149-169)
- Sales Tax Act, 1990 (Federal sales tax on goods)
- Provincial / ICT Sales Tax on Services (PRA 2012, SRB 2011, KPRA 2013, BRA 2015, ICT 2001)
- Advance Tax (Section 147)
"""

from __future__ import annotations

from typing import Any


def determine_applicable_obligations(
    *,
    legal_form: str,
    business_sector: str,
    principal_activity: str,
    jurisdictions: list[str],
    has_strn: bool,
    turnover_estimate: float = 0.0,
) -> list[str]:
    """Determines applicable Pakistan tax obligations based on taxpayer profile.

    Do not assume every client is subject to every tax.
    """
    obligations: list[str] = []

    # 1. Federal Income Tax
    obligations.append("Federal Income Tax (Income Tax Ordinance, 2001)")

    # Corporate vs Individual/AOP specific
    if legal_form in ("private_company", "public_unlisted", "public_listed", "banking_company"):
        obligations.append("Corporate Income Tax Return (Form IT-1 / FBR IRIS)")
        obligations.append("Quarterly Advance Income Tax (Section 147)")
        obligations.append("Alternate Corporate Tax assessment (Section 113C)")
        obligations.append("Super Tax on High Earning Persons (Section 4C)")
    elif legal_form == "aop":
        obligations.append("AOP Income Tax Return (FBR IRIS)")
        if turnover_estimate >= 100_000_000:
            obligations.append("Quarterly Advance Income Tax (Section 147)")
    else:  # individual
        obligations.append("Individual Business / Salaried Tax Return (FBR IRIS)")

    # Minimum Tax under Section 113
    if legal_form != "individual" or turnover_estimate >= 100_000_000:
        obligations.append("Minimum Tax on Turnover (Section 113)")

    # 2. Withholding Income Tax Agent Obligations (prescribed persons)
    is_prescribed_person = legal_form in (
        "private_company",
        "public_unlisted",
        "public_listed",
        "banking_company",
    ) or (turnover_estimate >= 100_000_000)

    if is_prescribed_person:
        obligations.append("Withholding Tax Agent (Prescribed Person - Section 153/165)")
        obligations.append("Periodic Withholding Tax Statements (Section 165 / IRIS)")
        obligations.append("Salary Withholding Tax deduction & deposit (Section 149)")

    # 3. Federal Sales Tax on Goods & FED
    activity_lower = (principal_activity + " " + business_sector).lower()
    is_goods_supplier = any(
        kw in activity_lower
        for kw in ("trading", "commercial", "manufacturing", "import", "wholesale", "distributor", "goods")
    )

    if has_strn or is_goods_supplier:
        obligations.append("Federal Sales Tax on Goods (Sales Tax Act, 1990)")
        obligations.append("Monthly Sales Tax Return (Annexure C, A, I - FBR e-portal)")

    # 4. Provincial / ICT Sales Tax on Services
    service_keywords = ("service", "consulting", "software", "it", "hospitality", "transport", "construction", "agency")
    is_service_provider = any(kw in activity_lower for kw in service_keywords)

    for jur in jurisdictions:
        jur_lower = jur.lower()
        if jur_lower == "pra" or (jur_lower == "punjab" and is_service_provider):
            obligations.append("Punjab Sales Tax on Services (Punjab Revenue Authority - PRA 2012)")
        elif jur_lower == "srb" or (jur_lower == "sindh" and is_service_provider):
            obligations.append("Sindh Sales Tax on Services (Sindh Revenue Board - SRB 2011)")
        elif jur_lower == "kpra" or (jur_lower in ("kpk", "kp") and is_service_provider):
            obligations.append("KP Sales Tax on Services (Khyber Pakhtunkhwa Revenue Authority - KPRA 2013)")
        elif jur_lower == "bra" or (jur_lower == "balochistan" and is_service_provider):
            obligations.append("Balochistan Sales Tax on Services (Balochistan Revenue Authority - BRA 2015)")
        elif jur_lower in ("ict", "islamabad") and is_service_provider:
            obligations.append("ICT Sales Tax on Services (Federal Board of Revenue - ICT Ordinance 2001)")

    return sorted(list(set(obligations)))
