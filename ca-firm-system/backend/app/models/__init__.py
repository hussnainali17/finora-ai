"""ORM models. Importing this package registers every table on ``Base.metadata``.

There is intentionally no ledger, journal or bookkeeping model anywhere in this product.
"""

from app.models.accounting_intake import AccountingIntakeRecord
from app.models.accounting_review import (
    ReconciliationSchedule,
    ReviewFinding,
    ReviewRun,
)
from app.models.adjustments import PeriodAdjustment
from app.models.audit import AuditEvent
from app.models.documents import Document, DocumentModuleReference, OutboxEvent
from app.models.extraction import (
    DataQualityFinding,
    ExtractedColumn,
    ExtractedRow,
    ExtractedTable,
    ExtractionRun,
)
from app.models.identity import (
    AccountingPeriod,
    Client,
    Firm,
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    User,
    UserClientAccess,
)
from app.models.llm import (
    LlmAgentConfig,
    LlmCallLog,
    LlmFirmPolicy,
    LlmModelSetting,
    LlmTaskOverride,
)
from app.models.ca_review import (
    CACorrectionProposal,
    CAConversation,
    CAMessage,
)
from app.models.reporting import AccountMapping, FinancialReport
from app.models.shared_data import ApprovedModuleOutput
from app.models.taxation import (
    MultiModuleWorkflowRun,
    TaxCalculationRun,
    TaxEngagement,
    TaxpayerProfile,
    TaxReturnDraft,
    TaxWorkflowRun,
    TaxWorkpaper,
)
from app.models.workflows import WorkflowRun

__all__ = [
    "AccountingIntakeRecord",
    "AccountMapping",
    "AccountingPeriod",
    "ApprovedModuleOutput",
    "AuditEvent",
    "CACorrectionProposal",
    "CAConversation",
    "CAMessage",
    "Client",
    "DataQualityFinding",
    "Document",
    "DocumentModuleReference",
    "ExtractedColumn",
    "ExtractedRow",
    "ExtractedTable",
    "ExtractionRun",
    "FinancialReport",
    "Firm",
    "LlmAgentConfig",
    "LlmCallLog",
    "LlmFirmPolicy",
    "LlmModelSetting",
    "LlmTaskOverride",
    "MultiModuleWorkflowRun",
    "OutboxEvent",
    "PeriodAdjustment",
    "Permission",
    "ReconciliationSchedule",
    "RefreshToken",
    "ReviewFinding",
    "ReviewRun",
    "Role",
    "RolePermission",
    "TaxCalculationRun",
    "TaxEngagement",
    "TaxpayerProfile",
    "TaxReturnDraft",
    "TaxWorkflowRun",
    "TaxWorkpaper",
    "User",
    "UserClientAccess",
    "WorkflowRun",
]
