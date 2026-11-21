"""Tests for Central Shared Data Layer publishing, retrieval, and version invalidation."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal
from app.models.reporting import FinancialReport
from app.models.shared_data import ApprovedModuleOutput
from app.services.shared_data import (
    get_latest_approved_accounting_output,
    list_approved_outputs,
    publish_approved_accounting_output,
    publish_approved_tax_output,
)


@pytest.fixture
def mock_principal() -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        firm_id=uuid.uuid4(),
        email="ca@firm.com",
        full_name="CA Reviewer",
        role_key="ca_reviewer",
        permissions=frozenset({"shared:publish", "shared:read", "client:read"}),
        session_id=uuid.uuid4(),
    )


@pytest.mark.asyncio
async def test_publish_accounting_output_and_versioning(mock_principal: Principal) -> None:
    client_id = uuid.uuid4()
    period_id = uuid.uuid4()

    mock_report = FinancialReport(
        id=uuid.uuid4(),
        firm_id=mock_principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        report_type="profit_loss",
        data={"net_profit": 500000, "total_revenue": 2000000, "total_expenses": 1500000},
        validation_results={"is_valid": True},
        status="signed_off",
    )

    mock_session = AsyncMock(spec=AsyncSession)

    # First run: no prior outputs
    mock_scalars = MagicMock()
    mock_scalars.all.side_effect = [
        [mock_report],  # reports
        [],             # adjustments
        [],             # mappings
        [],             # prior outputs (empty => version 1)
        [],             # dependent tax outputs
    ]
    mock_session.scalars.return_value = mock_scalars

    with patch("app.services.shared_data.get_accessible_client", return_value=None), \
         patch("app.services.shared_data.record_audit", return_value=None):
        out1 = await publish_approved_accounting_output(
            mock_session,
            mock_principal,
            client_id=client_id,
            period_id=period_id,
            notes="Initial sign-off",
        )

        assert out1.version == 1
        assert out1.module == "accounting"
        assert out1.status == "approved"
        assert out1.summary["net_profit"] == 500000
        assert out1.is_outdated is False


@pytest.mark.asyncio
async def test_cross_module_dependency_invalidation(mock_principal: Principal) -> None:
    """When a new accounting version is published, dependent taxation outputs are flagged outdated."""
    client_id = uuid.uuid4()
    period_id = uuid.uuid4()

    mock_report = FinancialReport(
        id=uuid.uuid4(),
        firm_id=mock_principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        report_type="profit_loss",
        data={"net_profit": 600000},
        validation_results={"is_valid": True},
        status="signed_off",
    )

    prior_accounting = ApprovedModuleOutput(
        id=uuid.uuid4(),
        firm_id=mock_principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        module="accounting",
        version=1,
        status="approved",
        data={},
        summary={},
        source_version_refs={},
        validation_results={},
        is_outdated=False,
    )

    dependent_tax = ApprovedModuleOutput(
        id=uuid.uuid4(),
        firm_id=mock_principal.firm_id,
        client_id=client_id,
        period_id=period_id,
        module="taxation",
        version=1,
        status="approved",
        data={"taxable_income": 500000},
        summary={},
        source_version_refs={"accounting_output_version": 1},
        validation_results={},
        is_outdated=False,
    )

    mock_session = AsyncMock(spec=AsyncSession)
    mock_scalars = MagicMock()
    mock_scalars.all.side_effect = [
        [mock_report],         # reports
        [],                    # adjustments
        [],                    # mappings
        [prior_accounting],    # prior accounting outputs (has ver 1 => next is 2)
        [dependent_tax],       # dependent taxation outputs referencing ver 1
    ]
    mock_session.scalars.return_value = mock_scalars

    with patch("app.services.shared_data.get_accessible_client", return_value=None), \
         patch("app.services.shared_data.record_audit", return_value=None):
        out2 = await publish_approved_accounting_output(
            mock_session,
            mock_principal,
            client_id=client_id,
            period_id=period_id,
            notes="Revised statements",
        )

        assert out2.version == 2
        # Prior accounting output marked superseded
        assert prior_accounting.status == "superseded"
        # Dependent taxation output flagged as outdated
        assert dependent_tax.is_outdated is True
        assert "updated to version 2" in dependent_tax.stale_reason
