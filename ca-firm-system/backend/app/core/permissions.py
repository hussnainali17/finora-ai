"""Single source of truth for permissions and system roles.

The initial Alembic migration seeds a frozen copy of this catalog; a test asserts the database
and this module never drift apart. Changing a role's permissions later requires a new migration.
"""

from typing import Final

# permission key -> description
PERMISSIONS: Final[dict[str, str]] = {
    "user:read": "View users in the firm",
    "user:manage": "Create users, change roles, activate/deactivate users",
    "client:read": "View clients the user can access",
    "client:create": "Create clients",
    "client:update": "Edit or archive clients the user can access",
    "client:access_all": "Implicitly access every client in the firm",
    "client:access_manage": "Assign or remove users on a client",
    "period:read": "View accounting periods",
    "period:create": "Create accounting periods",
    "period:update": "Edit open accounting periods",
    "period:close": "Close and reopen accounting periods",
    "audit:read": "View the audit trail (limited to accessible clients unless client:access_all)",
    "document:read": "List and download documents of accessible clients",
    "document:upload": "Upload documents to open accounting periods of accessible clients",
    "document:delete": "Remove (soft-delete) documents; the original object is retained",
    "extraction:read": "View extracted data, column mappings and data-quality findings",
    "extraction:review": "Correct column mappings / table types and resolve data-quality findings",
    "extraction:run": "Re-run extraction for a document",
    "llm:read": "View approved AI models, agent defaults and the firm model policy",
    "llm:manage": "Enable/disable models, set agent defaults/fallbacks and policy, view usage",
    "llm:select": "Choose an approved model for a specific task when firm policy allows",
    "review:read": "View accounting review results, findings and reconciliation schedules",
    "review:manage": "Trigger accounting review runs and configure review settings",
    "review:resolve": "Update finding status (explained/resolved/escalated) and add reviewer notes",
    # Phase 7 — Period-End Adjustments
    "adjustment:read": "View proposed, approved, and rejected period-end adjustments",
    "adjustment:propose": "Create and edit draft or proposed period-end adjustments",
    "adjustment:approve": "Approve or reject period-end adjustments (CA reviewer authority)",
    # Phase 8 — Financial Reporting & Validation
    "report:read": "View financial reports, Adjusted Trial Balance, and validation outputs",
    "report:generate": "Generate Adjusted Trial Balance and financial statements",
    "report:sign_off": "Provide formal CA sign-off on final published reports",
    # Phase 9 — LangGraph Workflows
    "workflow:read": "View end-to-end workflow execution state and history",
    "workflow:execute": "Trigger, pause, or resume end-to-end agent workflows",
}

FIRM_ADMIN = "firm_admin"
CA_REVIEWER = "ca_reviewer"
ACCOUNTANT = "accountant"
CLIENT_USER = "client_user"

# role key -> (display name, description, permission keys)
ROLES: Final[dict[str, tuple[str, str, frozenset[str]]]] = {
    FIRM_ADMIN: (
        "Firm Admin",
        "Manages the firm, users and client assignments. Can access every client in the firm.",
        frozenset(PERMISSIONS),
    ),
    CA_REVIEWER: (
        "CA / Reviewer",
        "Reviews and approves work for assigned clients; closes periods; reads the audit trail.",
        frozenset(
            {
                "client:read",
                "client:create",
                "client:update",
                "period:read",
                "period:create",
                "period:update",
                "period:close",
                "audit:read",
                "document:read",
                "document:upload",
                "document:delete",
                "extraction:read",
                "extraction:review",
                "extraction:run",
                "llm:read",
                "llm:select",
                "review:read",
                "review:manage",
                "review:resolve",
                "adjustment:read",
                "adjustment:propose",
                "adjustment:approve",
                "report:read",
                "report:generate",
                "report:sign_off",
                "workflow:read",
                "workflow:execute",
            }
        ),
    ),
    ACCOUNTANT: (
        "Accountant / Staff",
        "Prepares work for assigned clients. Cannot close periods.",
        frozenset(
            {
                "client:read",
                "period:read",
                "period:create",
                "period:update",
                "document:read",
                "document:upload",
                "extraction:read",
                "extraction:review",
                "extraction:run",
                "llm:read",
                "review:read",
                "review:resolve",
                "adjustment:read",
                "adjustment:propose",
                "report:read",
                "report:generate",
                "workflow:read",
                "workflow:execute",
            }
        ),
    ),
    CLIENT_USER: (
        "Read-only Client User",
        "Client-portal user: read-only access to assigned clients only.",
        frozenset(
            {
                "client:read",
                "period:read",
                "document:read",
                "extraction:read",
                "review:read",
                "adjustment:read",
                "report:read",
                "workflow:read",
            }
        ),
    ),
}

ASSIGNABLE_ROLE_KEYS: Final[frozenset[str]] = frozenset(ROLES)
