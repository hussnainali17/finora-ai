"""Central Document Intelligence Generic Classifier and Category Verifier.

Verifies the user-selected document category against the extracted content and text.
Enforces the core rule:
- The user selection is preserved as the primary classification.
- If a mismatch is detected, the document is flagged for review without silently altering the user category.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.document_intelligence.categories import (
    ACCOUNTING_CATEGORY_KEYS,
    AUDIT_CATEGORY_KEYS,
    TAXATION_CATEGORY_KEYS,
)

logger = logging.getLogger("app.document_intelligence.classifier")

# -----------------------------------------------------------------------------
# Keyword patterns for category detection
# -----------------------------------------------------------------------------

CATEGORY_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    # Accounting categories
    "trial_balance": [
        re.compile(r"\btrial\s+balance\b", re.IGNORECASE),
        re.compile(r"\bdebit\s+credit\s+balance\b", re.IGNORECASE),
        re.compile(r"\btb\s+report\b", re.IGNORECASE),
        re.compile(r"\bunadjusted\s+trial\s+balance\b", re.IGNORECASE),
    ],
    "general_ledger": [
        re.compile(r"\bgeneral\s+ledger\b", re.IGNORECASE),
        re.compile(r"\bgl\s+account\b", re.IGNORECASE),
        re.compile(r"\bledger\s+summary\b", re.IGNORECASE),
        re.compile(r"\bnominal\s+ledger\b", re.IGNORECASE),
    ],
    "bank_statement": [
        re.compile(r"\bbank\s+statement\b", re.IGNORECASE),
        re.compile(r"\baccount\s+statement\b", re.IGNORECASE),
        re.compile(r"\bopening\s+balance\b.*\bclosing\s+balance\b", re.IGNORECASE | re.DOTALL),
        re.compile(r"\bwithdrawals?\b.*\bdeposits?\b", re.IGNORECASE | re.DOTALL),
        re.compile(r"\bcheque\s+no\b|\bcheck\s+no\b", re.IGNORECASE),
    ],
    "invoice": [
        re.compile(r"\btax\s+invoice\b|\bsales\s+invoice\b|\bcommercial\s+invoice\b", re.IGNORECASE),
        re.compile(r"\binvoice\s+(no|number|#)\b", re.IGNORECASE),
        re.compile(r"\bbill\s+to\b|\bship\s+to\b", re.IGNORECASE),
        re.compile(r"\bdue\s+date\b.*\binvoice\s+date\b", re.IGNORECASE | re.DOTALL),
    ],
    "receipt": [
        re.compile(r"\breceipt\b|\bofficial\s+receipt\b|\bcash\s+receipt\b", re.IGNORECASE),
        re.compile(r"\bpayment\s+received\b|\breceived\s+from\b", re.IGNORECASE),
    ],
    "contract": [
        re.compile(r"\bagreement\b|\bcontract\b|\bmemorandum\s+of\s+understanding\b|\bmou\b", re.IGNORECASE),
        re.compile(r"\bterms\s+and\s+conditions\b", re.IGNORECASE),
        re.compile(r"\bparty\s+of\s+the\s+first\s+part\b", re.IGNORECASE),
    ],
    "fixed_asset_schedule": [
        re.compile(r"\bfixed\s+assets?\b|\basset\s+schedule\b|\bppe\s+schedule\b", re.IGNORECASE),
        re.compile(r"\baccumulated\s+depreciation\b|\bwritten\s+down\s+value\b|\bwdv\b", re.IGNORECASE),
        re.compile(r"\bnet\s+book\s+value\b|\bnbv\b", re.IGNORECASE),
    ],
    "inventory_report": [
        re.compile(r"\binventory\s+report\b|\bstock\s+report\b|\bstock\s+ledger\b", re.IGNORECASE),
        re.compile(r"\bstock\s+on\s+hand\b|\bquantity\s+on\s+hand\b|\bclosing\s+stock\b", re.IGNORECASE),
        re.compile(r"\bitem\s+code\b.*\bqty\b.*\bunit\s+cost\b", re.IGNORECASE | re.DOTALL),
    ],
    "payroll_schedule": [
        re.compile(r"\bpayroll\b|\bsalary\s+sheet\b|\bwages\s+sheet\b|\bsalary\s+register\b", re.IGNORECASE),
        re.compile(r"\bgross\s+pay\b.*\bdeductions?\b.*\bnet\s+pay\b", re.IGNORECASE | re.DOTALL),
        re.compile(r"\bbasic\s+salary\b|\bhouse\s+rent\s+allowance\b", re.IGNORECASE),
    ],

    # Taxation categories
    "tax_return": [
        re.compile(r"\bincome\s+tax\s+return\b|\biris\b|\bit-1\b|\bit-2\b", re.IGNORECASE),
        re.compile(r"\btax\s+year\s+20\d\d\b", re.IGNORECASE),
        re.compile(r"\bsection\s+114\b|\bunder\s+section\s+114\b", re.IGNORECASE),
        re.compile(r"\btaxable\s+income\b.*\btax\s+payable\b", re.IGNORECASE | re.DOTALL),
    ],
    "withholding_certificate": [
        re.compile(r"\bwithholding\s+tax\s+certificate\b|\bwht\s+certificate\b", re.IGNORECASE),
        re.compile(r"\bsection\s+153\b|\bsection\s+155\b|\bsection\s+236\b", re.IGNORECASE),
        re.compile(r"\bcpr\s+no\b|\bcpr\b|\bcomputerized\s+payment\s+receipt\b", re.IGNORECASE),
        re.compile(r"\btax\s+deducted\s+at\s+source\b", re.IGNORECASE),
    ],
    "sales_tax_return": [
        re.compile(r"\bsales\s+tax\s+return\b|\bannexure\s+[a-z]\b", re.IGNORECASE),
        re.compile(r"\bstrn\b.*\binput\s+tax\b.*\boutput\s+tax\b", re.IGNORECASE | re.DOTALL),
        re.compile(r"\bfbr\s+sales\s+tax\b|\bsales\s+tax\s+act\s+1990\b", re.IGNORECASE),
    ],
    "tax_payment_challan": [
        re.compile(r"\bchallan\b|\bcpr\b|\btax\s+payment\s+receipt\b", re.IGNORECASE),
        re.compile(r"\bhead\s+of\s+account\b|\bbank\s+scroll\b", re.IGNORECASE),
        re.compile(r"\bpayment\s+section\b|\badvance\s+tax\s+u/s\s+147\b", re.IGNORECASE),
    ],
    "tax_notice": [
        re.compile(r"\bnotice\s+under\s+section\b|\bshow\s+cause\s+notice\b|\bscn\b", re.IGNORECASE),
        re.compile(r"\bsection\s+122\b|\bsection\s+177\b|\bsection\s+214c\b|\bsection\s+111\b", re.IGNORECASE),
        re.compile(r"\border\s+under\s+section\b", re.IGNORECASE),
    ],
    "tax_exemption_certificate": [
        re.compile(r"\bexemption\s+certificate\b|\bsection\s+159\b", re.IGNORECASE),
        re.compile(r"\breduced\s+rate\s+certificate\b", re.IGNORECASE),
    ],

    # Audit categories
    "audit_engagement_letter": [
        re.compile(r"\bengagement\s+letter\b|\bterms\s+of\s+audit\b", re.IGNORECASE),
        re.compile(r"\bisa\s+210\b", re.IGNORECASE),
    ],
    "management_representation": [
        re.compile(r"\bmanagement\s+representation\b|\brepresentation\s+letter\b", re.IGNORECASE),
        re.compile(r"\bisa\s+580\b", re.IGNORECASE),
    ],
    "audit_confirmation": [
        re.compile(r"\bbank\s+confirmation\b|\bdebtor\s+confirmation\b|\bexternal\s+confirmation\b", re.IGNORECASE),
        re.compile(r"\bisa\s+505\b", re.IGNORECASE),
    ],
    "sampling_evidence": [
        re.compile(r"\baudit\s+sample\b|\bsampling\s+sheet\b|\btest\s+of\s+controls\b", re.IGNORECASE),
    ],
}


@dataclass
class ClassificationVerification:
    user_category: str
    detected_category: str
    confidence: float
    is_mismatch: bool
    explanation: str
    module: str
    warnings: list[str] = field(default_factory=list)


def verify_category(
    *,
    user_category: str,
    module: str,
    filename: str,
    text_content: str,
    table_headers: list[str] | None = None,
) -> ClassificationVerification:
    """Verifies the CA's selected category against document contents.

    Returns ClassificationVerification. If a mismatch is detected:
    - is_mismatch is True
    - user_category is kept intact
    - explanation describes the inconsistency for CA review.
    """
    user_cat = user_category.lower().strip()
    mod = module.lower().strip()
    combined_text = f"{filename}\n{' '.join(table_headers or [])}\n{text_content[:15000]}".lower()

    # Score each category
    scores: dict[str, float] = {}
    for cat, patterns in CATEGORY_PATTERNS.items():
        score = 0.0
        for pat in patterns:
            matches = len(pat.findall(combined_text))
            if matches > 0:
                score += min(matches * 0.35, 1.0)
        # Give a small boost if category name itself is in filename
        clean_cat = cat.replace("_", " ")
        if clean_cat in filename.lower():
            score += 0.4
        scores[cat] = score

    # Find highest scoring category
    best_cat, best_score = max(scores.items(), key=lambda x: x[1]) if scores else ("other", 0.0)
    confidence = min(round(best_score / 1.5, 2), 0.99) if best_score > 0 else 0.2

    # Check if user category has good support in the text
    user_cat_score = scores.get(user_cat, 0.0)

    # Determine if there is a true mismatch:
    # 1. User selected category had virtually 0 match, but another category had strong match (>= 0.7)
    # 2. Or user selected a category belonging to another module (e.g., Accounting invoice vs Tax CPR)
    is_mismatch = False
    explanation = f"Document verified as matching user selection '{user_category}'."
    warnings: list[str] = []

    # If user selected 'other', it's never a mismatch unless high confidence specific match found
    if user_cat in ("other", "tax_other", "audit_other"):
        if confidence >= 0.75 and best_score >= 1.0:
            is_mismatch = False  # Not an error, just an informative detection
            explanation = f"Generic category selected. Content suggests specific type '{best_cat}'."
    elif best_score >= 0.8 and user_cat_score < 0.2 and best_cat != user_cat:
        # Clear mismatch detected
        is_mismatch = True
        explanation = (
            f"Category Mismatch: User selected '{user_cat}', but document content strongly "
            f"indicates '{best_cat}' (confidence: {int(confidence * 100)}%)."
        )
        warnings.append(
            f"Selected category '{user_cat}' does not match detected document content ('{best_cat}'). "
            "Please review and verify."
        )
    elif user_cat in TAXATION_CATEGORY_KEYS and mod == "accounting":
        is_mismatch = True
        explanation = f"Cross-module mismatch: Category '{user_cat}' is a Taxation category, but module is Accounting."
        warnings.append(explanation)
    elif user_cat in ACCOUNTING_CATEGORY_KEYS and mod == "taxation":
        # Note: TB or invoices can be referenced by Taxation, but if uploaded under Tax module,
        # note it for review.
        if user_cat not in ("trial_balance", "general_ledger", "invoice"):
            is_mismatch = True
            explanation = f"Category '{user_cat}' is typically an Accounting category."
            warnings.append(explanation)

    logger.debug(
        "category verification: user=%s detected=%s confidence=%.2f mismatch=%s",
        user_cat,
        best_cat,
        confidence,
        is_mismatch,
    )

    return ClassificationVerification(
        user_category=user_category,
        detected_category=best_cat if best_score > 0 else user_category,
        confidence=confidence if best_score > 0 else 0.5,
        is_mismatch=is_mismatch,
        explanation=explanation,
        module=mod,
        warnings=warnings,
    )
