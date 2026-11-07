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
            }
        ),
    ),
    CLIENT_USER: (
        "Read-only Client User",
        "Client-portal user: read-only access to assigned clients only.",
        frozenset({"client:read", "period:read", "document:read"}),
    ),
}

ASSIGNABLE_ROLE_KEYS: Final[frozenset[str]] = frozenset(ROLES)
