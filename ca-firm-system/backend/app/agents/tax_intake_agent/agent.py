"""Agent 1: Tax Intake & Taxpayer Profile Agent.

Consumes centrally extracted documents from Central Document Intelligence and relevant
Accounting outputs.

Responsibilities:
1. Taxpayer profile management (legal form, NTN/STRN, obligations, branches).
2. Tax year identification.
3. Tax document association with the relevant taxpayer.
4. Tax information completeness checking.
5. Identification of missing tax information.
6. Comparison of extracted information against existing taxpayer profiles.
7. Identification of inconsistencies in tax documents (conflict flagging for CA confirmation;
   never blindly overwrites verified profile information).
8. Preparation of consolidated, structured tax inputs for downstream Tax Agents (2, 3, 4).
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tax_intake_agent.obligations import determine_applicable_obligations
from app.agents.tax_intake_agent.profile_builder import (
    analyze_profile_completeness,
    validate_ntn,
    validate_strn,
)
from app.models.documents import Document, DocumentModuleReference
from app.models.extraction import ExtractedRow, ExtractedTable, ExtractionRun
from app.models.identity import Client
from app.models.taxation import TaxEngagement, TaxpayerProfile

logger = logging.getLogger("app.agents.tax_intake")


class TaxIntakeAgent:
    """Agent 1: Tax Intake & Taxpayer Profile Agent."""

    async def execute_intake(
        self,
        session: AsyncSession,
        *,
        engagement_id: uuid.UUID,
        override_profile_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Runs the tax intake process using centrally extracted documents and persists/updates
        the TaxpayerProfile without overwriting verified attributes.
        """
        engagement = await session.get(TaxEngagement, engagement_id)
        if not engagement:
            raise ValueError(f"TaxEngagement {engagement_id} not found.")

        client = await session.get(Client, engagement.client_id)
        if not client:
            raise ValueError(f"Client {engagement.client_id} not found.")

        # 1. Fetch Centrally Ingested & Shared Documents for this client and period
        # Include documents primarily under 'taxation' OR shared with taxation via DocumentModuleReference
        ref_subq = (
            select(DocumentModuleReference.document_id)
            .where(
                DocumentModuleReference.firm_id == engagement.firm_id,
                DocumentModuleReference.client_id == engagement.client_id,
                DocumentModuleReference.period_id == engagement.period_id,
                DocumentModuleReference.module == "taxation",
                DocumentModuleReference.status == "active",
            )
            .scalar_subquery()
        )
        docs_stmt = (
            select(Document)
            .where(
                Document.firm_id == engagement.firm_id,
                Document.client_id == engagement.client_id,
                Document.period_id == engagement.period_id,
                Document.deleted_at.is_(None),
                (Document.module == "taxation")
                | (Document.id.in_(ref_subq))
                | (Document.category.in_(("tax_return", "withholding_certificate", "sales_tax_return", "tax_payment_challan"))),
            )
        )
        documents = list((await session.scalars(docs_stmt)).all())

        # If no tax-specific documents found yet, also consider accounting documents in period for general awareness
        if not documents:
            fallback_docs = await session.scalars(
                select(Document).where(
                    Document.firm_id == engagement.firm_id,
                    Document.client_id == engagement.client_id,
                    Document.period_id == engagement.period_id,
                    Document.deleted_at.is_(None),
                )
            )
            documents = list(fallback_docs.all())

        # 2. Analyze Document Types from Central Intelligence Categories
        has_prior_returns = any(
            d.category in ("tax_return", "sales_tax_return")
            or any(kw in (d.original_filename or "").lower() for kw in ("tax return", "iris", "it-1", "prior year", "return"))
            for d in documents
        )
        has_tax_payment_evidence = any(
            d.category in ("tax_payment_challan", "withholding_certificate")
            or any(kw in (d.original_filename or "").lower() for kw in ("cpr", "challan", "tax payment", "147", "payment"))
            for d in documents
        )

        # 3. Read Centrally Extracted Tables & Rows to Extract Tax Artifacts
        extracted_ntns: set[str] = set()
        cpr_records: list[dict[str, Any]] = []

        for d in documents:
            tables = (
                await session.scalars(
                    select(ExtractedTable)
                    .join(ExtractionRun, ExtractedTable.run_id == ExtractionRun.id)
                    .where(
                        ExtractedTable.document_id == d.id,
                        ExtractionRun.is_current.is_(True),
                    )
                )
            ).all()

            for tbl in tables:
                rows = (
                    await session.scalars(
                        select(ExtractedRow).where(ExtractedRow.table_id == tbl.id).limit(100)
                    )
                ).all()

                for row in rows:
                    norm = row.normalized or {}
                    # Look for NTN patterns in row cells
                    for v in norm.values():
                        if isinstance(v, str) and re.match(r"^\d{7}-?\d?$", v.strip()):
                            extracted_ntns.add(v.strip())

                    # Look for CPR withholding or payment records
                    ref = norm.get("reference") or norm.get("description")
                    amt = norm.get("amount") or norm.get("debit")
                    if ref and any(kw in str(ref).lower() for kw in ("cpr", "challan", "wht")):
                        cpr_records.append(
                            {
                                "document_id": str(d.id),
                                "cpr_reference": ref,
                                "amount": str(amt or "0.00"),
                                "table": tbl.name,
                            }
                        )

        # 4. Check Existing Profile & Prevent Blind Overwrite of Verified Attributes
        prof_res = await session.scalars(
            select(TaxpayerProfile)
            .where(TaxpayerProfile.engagement_id == engagement_id)
            .order_by(TaxpayerProfile.version.desc())
        )
        existing_profile = prof_res.first()

        conflicts: list[dict[str, Any]] = []

        # Client profile defaults
        overrides = override_profile_data or {}
        legal_form = overrides.get("legal_form") or (
            existing_profile.legal_form if existing_profile else "private_company"
        )
        base_ntn = overrides.get("ntn") or getattr(client, "tax_id", None) or (
            existing_profile.ntn if existing_profile else "0000000-0"
        )
        strn = overrides.get("strn") or (existing_profile.strn if existing_profile else None)
        principal_activity = overrides.get("principal_activity") or (
            existing_profile.principal_activity if existing_profile else "Commercial Business"
        )
        business_sector = overrides.get("business_sector") or (
            existing_profile.business_sector if existing_profile else "General Trading & Commercial"
        )
        registered_branches = overrides.get("registered_branches") or (
            existing_profile.registered_branches
            if existing_profile
            else [{"branch_name": "Head Office", "city": "Karachi", "province": "Sindh", "jurisdiction": "SRB"}]
        )
        jurisdictions = overrides.get("jurisdictions") or (
            existing_profile.jurisdictions if existing_profile else ["Federal", "SRB"]
        )

        # Conflict Detection: Compare extracted NTN vs verified profile NTN
        if existing_profile and existing_profile.ntn and extracted_ntns:
            for ext_ntn in extracted_ntns:
                # Compare digits
                clean_ext = ext_ntn.replace("-", "")
                clean_prof = existing_profile.ntn.replace("-", "")
                if clean_ext != clean_prof and clean_ext != "00000000":
                    conflicts.append(
                        {
                            "field": "ntn",
                            "profile_value": existing_profile.ntn,
                            "extracted_value": ext_ntn,
                            "reason": (
                                f"Extracted document NTN '{ext_ntn}' does not match verified taxpayer profile NTN '{existing_profile.ntn}'. "
                                "Preserving verified profile; flagged for CA review."
                            ),
                        }
                    )
            # Never blindly overwrite verified profile NTN
            ntn = existing_profile.ntn
        else:
            ntn = base_ntn

        # 5. Determine Obligations
        obligations = determine_applicable_obligations(
            legal_form=legal_form,
            business_sector=business_sector,
            principal_activity=principal_activity,
            jurisdictions=jurisdictions,
            has_strn=bool(strn),
            turnover_estimate=float(overrides.get("estimated_turnover", 0.0)),
        )

        # 6. Analyze Completeness
        missing_info = analyze_profile_completeness(
            legal_form=legal_form,
            ntn=ntn,
            strn=strn,
            business_sector=business_sector,
            principal_activity=principal_activity,
            registered_branches=registered_branches,
            jurisdictions=jurisdictions,
            has_prior_returns=has_prior_returns,
            has_tax_payment_evidence=has_tax_payment_evidence,
        )

        # Add conflict notices to missing_info
        for c in conflicts:
            missing_info.append(
                {
                    "item_id": f"conflict_{c['field']}",
                    "category": "taxpayer_profile",
                    "title": f"Profile Discrepancy: {c['field'].upper()}",
                    "severity": "critical",
                    "question": c["reason"],
                    "remedy": "CA confirmation required to resolve the discrepancy.",
                }
            )

        # 7. Update or Create TaxpayerProfile
        if existing_profile:
            existing_profile.legal_form = legal_form
            existing_profile.ntn = ntn
            existing_profile.strn = strn
            existing_profile.principal_activity = principal_activity
            existing_profile.business_sector = business_sector
            existing_profile.registered_branches = registered_branches
            existing_profile.jurisdictions = jurisdictions
            existing_profile.applicable_obligations = obligations
            existing_profile.missing_information = missing_info
            existing_profile.version += 1
            profile = existing_profile
        else:
            profile = TaxpayerProfile(
                firm_id=engagement.firm_id,
                client_id=engagement.client_id,
                engagement_id=engagement.id,
                version=1,
                legal_form=legal_form,
                ntn=ntn,
                strn=strn,
                principal_activity=principal_activity,
                business_sector=business_sector,
                registered_branches=registered_branches,
                jurisdictions=jurisdictions,
                applicable_obligations=obligations,
                is_active_taxpayer=True,
                verified_attributes={
                    "client_name": client.name,
                    "tax_year": engagement.tax_year,
                    "tax_period_label": engagement.tax_period_label,
                    "documents_indexed_count": len(documents),
                    "conflicts_count": len(conflicts),
                },
                missing_information=missing_info,
            )
            session.add(profile)

        engagement.status = "data_gathering"
        await session.commit()
        await session.refresh(profile)

        source_doc_index = [
            {
                "document_id": str(d.id),
                "filename": getattr(d, "original_filename", "") or getattr(d, "filename", "document"),
                "document_type": getattr(d, "category", "other"),
                "module": getattr(d, "module", "accounting"),
                "uploaded_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in documents
        ]

        # 8. Prepare Consolidated Structured Tax Inputs for downstream Tax Agents (2, 3, 4)
        consolidated_tax_inputs = {
            "tax_year": engagement.tax_year,
            "tax_period_label": engagement.tax_period_label,
            "taxpayer_name": client.name,
            "ntn": profile.ntn,
            "strn": profile.strn,
            "legal_form": profile.legal_form,
            "obligations": obligations,
            "source_documents_count": len(documents),
            "cpr_records_found": len(cpr_records),
            "cpr_records": cpr_records[:50],
            "conflicts": conflicts,
            "ready_for_tax_data_agent": True,
        }

        logger.info(
            "tax intake completed for engagement %s (obligations: %d, missing: %d, conflicts: %d)",
            engagement_id,
            len(obligations),
            len(missing_info),
            len(conflicts),
        )

        return {
            "profile_id": str(profile.id),
            "engagement_id": str(engagement.id),
            "taxpayer_profile": {
                "legal_form": profile.legal_form,
                "ntn": profile.ntn,
                "strn": profile.strn,
                "principal_activity": profile.principal_activity,
                "business_sector": profile.business_sector,
                "registered_branches": profile.registered_branches,
                "jurisdictions": profile.jurisdictions,
                "version": profile.version,
            },
            "obligations": obligations,
            "missing_information": missing_info,
            "source_documents_indexed": source_doc_index,
            "consolidated_tax_inputs": consolidated_tax_inputs,
            "conflicts": conflicts,
        }
