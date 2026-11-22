"""Agent 4: Tax Review & Filing Pack Agent.

Responsibilities:
- Runs cross-checks, detects missing schedules, inconsistent values, duplicate claims,
  and unsupported deductions/credits.
- Generates a CA review pack and filing-ready draft (FBR IRIS Form IT-1).
- Enforces CA human-in-the-loop approval gate: actual filing and final declarations
  require authorized CA sign-off.
- Tracks approval and filing evidence (CPRs, acknowledgment numbers).
- Publishes approved taxation outputs to the Central Shared Data Layer.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tax_review_agent.cross_checks import run_tax_cross_checks
from app.agents.tax_review_agent.iris_mapper import map_to_fbr_iris_fields
from app.api.deps import Principal, require_permission
from app.models.taxation import (
    TaxCalculationRun,
    TaxEngagement,
    TaxpayerProfile,
    TaxReturnDraft,
    TaxWorkpaper,
)
from app.services.shared_data import publish_approved_tax_output

logger = logging.getLogger("app.agents.tax_review")


class TaxReviewAgent:
    """Agent 4: Tax Review & Filing Pack Agent."""

    async def generate_review_and_draft(
        self,
        session: AsyncSession,
        *,
        engagement_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Runs validation checks and generates filing-ready draft return pack."""
        engagement = await session.get(TaxEngagement, engagement_id)
        if not engagement:
            raise ValueError(f"TaxEngagement {engagement_id} not found.")

        # 1. Fetch TaxCalculationRun
        calc_res = await session.scalars(
            select(TaxCalculationRun)
            .where(TaxCalculationRun.engagement_id == engagement_id)
            .order_by(desc(TaxCalculationRun.created_at))
        )
        calc_run = calc_res.first()
        if not calc_run:
            raise ValueError("No tax calculation run found. Run Agent 3 before review.")

        # 2. Fetch TaxpayerProfile
        prof_res = await session.scalars(
            select(TaxpayerProfile).where(TaxpayerProfile.engagement_id == engagement_id)
        )
        profile = prof_res.first()
        profile_data = {
            "legal_form": profile.legal_form if profile else "private_company",
            "ntn": profile.ntn if profile else "",
            "strn": profile.strn if profile else "",
            "principal_activity": profile.principal_activity if profile else "",
        }

        # 3. Fetch Workpapers
        wp_res = await session.scalars(
            select(TaxWorkpaper).where(TaxWorkpaper.engagement_id == engagement_id)
        )
        workpapers = {wp.workpaper_type: wp.data for wp in wp_res.all()}

        # 4. Assemble flattened income tax data for validation
        income_tax_data = {
            "accounting_profit_before_tax": calc_run.accounting_profit.get("pbt", 0.0),
            "turnover": calc_run.accounting_profit.get("turnover", 0.0),
            "total_additions": sum(item.get("amount", 0.0) for item in calc_run.tax_adjustments.get("additions", [])),
            "total_deductions": sum(item.get("amount", 0.0) for item in calc_run.tax_adjustments.get("deductions", [])),
            "inadmissible_additions": calc_run.tax_adjustments.get("additions", []),
            "admissible_deductions": calc_run.tax_adjustments.get("deductions", []),
            "taxable_income": calc_run.taxable_income.get("taxable_income", 0.0),
            "normal_tax": calc_run.normal_tax.get("normal_tax", 0.0),
            "super_tax_4c": calc_run.super_tax_4c.get("super_tax_4c", 0.0),
            "minimum_tax_113": calc_run.minimum_tax_113.get("minimum_tax_113", 0.0),
            "alternate_corporate_tax_113c": calc_run.alternate_corporate_tax_113c.get("act_113c", 0.0),
            "gross_tax_liability": calc_run.net_tax_payable.get("gross_liability", 0.0),
            "tax_credits": sum(c.get("amount", 0.0) for c in calc_run.tax_credits.get("credits", [])),
            "withholding_taxes_paid": sum(w.get("amount", 0.0) for w in calc_run.withholding_taxes.get("withholding_taxes", [])),
            "advance_tax_paid": float(calc_run.withholding_taxes.get("advance_tax", 0.0)),
            "net_tax_payable": calc_run.net_tax_payable.get("net_payable", 0.0),
            "rule_set_version": calc_run.rule_set_version,
        }

        # 5. Run Cross-Checks
        review_report = run_tax_cross_checks(
            income_tax_data=income_tax_data,
            workpapers=workpapers,
            taxpayer_profile=profile_data,
        )

        # 6. Generate FBR IRIS field mappings
        iris_pack = map_to_fbr_iris_fields(
            income_tax=income_tax_data,
            sales_tax=calc_run.sales_tax_computation,
            taxpayer_profile=profile_data,
            tax_year=engagement.tax_year,
        )

        # 7. Persist TaxReturnDraft
        draft_res = await session.scalars(
            select(TaxReturnDraft)
            .where(TaxReturnDraft.engagement_id == engagement_id)
            .order_by(desc(TaxReturnDraft.version))
        )
        existing_draft = draft_res.first()
        next_ver = (existing_draft.version + 1) if existing_draft else 1

        draft = TaxReturnDraft(
            firm_id=engagement.firm_id,
            client_id=engagement.client_id,
            engagement_id=engagement.id,
            version=next_ver,
            return_type="it_1",
            return_fields=iris_pack["fields"],
            review_report=review_report,
            risk_findings=review_report["findings"],
            status="draft",
            filing_evidence={},
        )
        session.add(draft)
        engagement.status = "review_pending"
        await session.commit()
        await session.refresh(draft)

        logger.info(
            "TaxReviewAgent generated draft return v%d for engagement %s (compliant: %s, findings: %d)",
            next_ver,
            engagement_id,
            review_report["is_compliant"],
            len(review_report["findings"]),
        )

        return {
            "draft_id": str(draft.id),
            "engagement_id": str(engagement.id),
            "version": next_ver,
            "status": "draft",
            "review_report": review_report,
            "iris_mapping": iris_pack,
        }

    async def sign_off_tax_pack(
        self,
        session: AsyncSession,
        principal: Principal,
        *,
        draft_id: uuid.UUID,
        notes: str | None = None,
    ) -> TaxReturnDraft:
        """Formal CA reviewer sign-off on the tax pack and publication to Central Shared Data Layer."""
        require_permission(principal, "tax:approve")

        draft = await session.get(TaxReturnDraft, draft_id)
        if not draft:
            raise ValueError(f"TaxReturnDraft {draft_id} not found.")

        engagement = await session.get(TaxEngagement, draft.engagement_id)
        if not engagement:
            raise ValueError("Associated TaxEngagement not found.")

        draft.status = "ca_approved"
        draft.signed_off_by = principal.user_id
        draft.signed_off_at = datetime.now(UTC)
        draft.sign_off_notes = notes or "CA Approved Tax Return Draft"
        engagement.status = "approved"

        # Check source accounting version used by Agent 2
        wp_res = await session.scalars(
            select(TaxWorkpaper)
            .where(TaxWorkpaper.engagement_id == draft.engagement_id)
            .limit(1)
        )
        sample_wp = wp_res.first()
        acc_ver = sample_wp.accounting_output_version if sample_wp else None

        # Publish to Central Shared Data Layer
        summary = {
            "tax_year": engagement.tax_year,
            "net_tax_payable": draft.return_fields.get("7017", 0.0),
            "gross_tax_liability": draft.return_fields.get("7013", 0.0),
            "taxable_income": draft.return_fields.get("7008", 0.0),
            "turnover": draft.return_fields.get("7001", 0.0),
        }

        await publish_approved_tax_output(
            session,
            principal,
            client_id=engagement.client_id,
            period_id=engagement.period_id,
            data={
                "return_fields": draft.return_fields,
                "review_report": draft.review_report,
                "risk_findings": draft.risk_findings,
            },
            summary=summary,
            source_version_refs={"accounting_output_version": acc_ver} if acc_ver else {},
            validation_results={
                "is_compliant": draft.review_report.get("is_compliant", True),
                "error_count": draft.review_report.get("error_count", 0),
            },
            notes=notes or "Published upon CA tax pack sign-off",
        )

        await session.commit()
        await session.refresh(draft)

        logger.info(
            "Tax return draft %s approved by CA %s and published to Central Shared Data Layer.",
            draft_id,
            principal.user_id,
        )
        return draft

    async def record_filing_evidence(
        self,
        session: AsyncSession,
        principal: Principal,
        *,
        draft_id: uuid.UUID,
        cpr_numbers: list[str],
        acknowledgment_number: str,
        filing_date: str,
        bank_name: str | None = None,
        amount_paid: str | None = None,
        notes: str | None = None,
    ) -> TaxReturnDraft:
        """Records official filing evidence upon submission to FBR IRIS."""
        require_permission(principal, "tax:manage")

        draft = await session.get(TaxReturnDraft, draft_id)
        if not draft:
            raise ValueError(f"TaxReturnDraft {draft_id} not found.")

        engagement = await session.get(TaxEngagement, draft.engagement_id)
        if not engagement:
            raise ValueError("Associated TaxEngagement not found.")

        evidence = {
            "cpr_numbers": cpr_numbers,
            "acknowledgment_number": acknowledgment_number,
            "filing_date": filing_date,
            "bank_name": bank_name,
            "amount_paid": amount_paid,
            "recorded_by": str(principal.user_id),
            "recorded_at": datetime.now(UTC).isoformat(),
            "notes": notes,
        }

        draft.filing_evidence = evidence
        draft.status = "filed"
        engagement.status = "filed"

        await session.commit()
        await session.refresh(draft)
        logger.info("Filing evidence recorded for draft %s (Ack: %s)", draft_id, acknowledgment_number)
        return draft
