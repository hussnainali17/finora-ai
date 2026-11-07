"""Phase 1: firms, users, roles/permissions, clients, accounting periods, access, audit.

Revision ID: 0001
Revises:
Create Date: 2026-10-31

The role/permission seed below is a FROZEN snapshot (do not import app code into migrations).
A test asserts it matches app.core.permissions. No ledger/journal tables exist or may be added.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ExcludeConstraint

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

PERMISSIONS = {
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
}
ROLES = {
    "firm_admin": (
        "Firm Admin",
        "Manages the firm, users and client assignments. Can access every client in the firm.",
        sorted(PERMISSIONS),
    ),
    "ca_reviewer": (
        "CA / Reviewer",
        "Reviews and approves work for assigned clients; closes periods; reads the audit trail.",
        [
            "client:read",
            "client:create",
            "client:update",
            "period:read",
            "period:create",
            "period:update",
            "period:close",
            "audit:read",
        ],
    ),
    "accountant": (
        "Accountant / Staff",
        "Prepares work for assigned clients. Cannot close periods.",
        ["client:read", "period:read", "period:create", "period:update"],
    ),
    "client_user": (
        "Read-only Client User",
        "Client-portal user: read-only access to assigned clients only.",
        ["client:read", "period:read"],
    ),
}


def _uuid_pk() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "firms",
        _uuid_pk(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_firms"),
        sa.UniqueConstraint("slug", name="uq_firms_slug"),
    )

    permissions = op.create_table(
        "permissions",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.PrimaryKeyConstraint("key", name="pk_permissions"),
    )
    roles = op.create_table(
        "roles",
        sa.Column("key", sa.String(32), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.PrimaryKeyConstraint("key", name="pk_roles"),
    )
    role_permissions = op.create_table(
        "role_permissions",
        sa.Column("role_key", sa.String(32), nullable=False),
        sa.Column("permission_key", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_key"],
            ["roles.key"],
            name="fk_role_permissions_role_key_roles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_key"],
            ["permissions.key"],
            name="fk_role_permissions_permission_key_permissions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_key", "permission_key", name="pk_role_permissions"),
    )
    op.bulk_insert(permissions, [{"key": k, "description": d} for k, d in PERMISSIONS.items()])
    op.bulk_insert(
        roles, [{"key": k, "name": n, "description": d} for k, (n, d, _) in ROLES.items()]
    )
    op.bulk_insert(
        role_permissions,
        [{"role_key": k, "permission_key": p} for k, (_, _, perms) in ROLES.items() for p in perms],
    )

    op.create_table(
        "users",
        _uuid_pk(),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role_key", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("failed_login_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.ForeignKeyConstraint(
            ["firm_id"], ["firms.id"], name="fk_users_firm_id_firms", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["role_key"], ["roles.key"], name="fk_users_role_key_roles", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("id", "firm_id", name="uq_users_id_firm_id"),
        sa.CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
    )
    op.create_index("ix_users_firm_id", "users", ["firm_id"])

    op.create_table(
        "clients",
        _uuid_pk(),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("legal_name", sa.String(300)),
        sa.Column("base_currency", sa.String(3), nullable=False, server_default="PKR"),
        sa.Column("fiscal_year_end_month", sa.Integer, nullable=False, server_default="12"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_clients"),
        sa.ForeignKeyConstraint(
            ["firm_id"], ["firms.id"], name="fk_clients_firm_id_firms", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("id", "firm_id", name="uq_clients_id_firm_id"),
        sa.UniqueConstraint("firm_id", "code", name="uq_clients_firm_id_code"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_clients_status_valid"),
        sa.CheckConstraint(
            "char_length(base_currency) = 3", name="ck_clients_currency_iso4217_len"
        ),
        sa.CheckConstraint(
            "fiscal_year_end_month BETWEEN 1 AND 12", name="ck_clients_fiscal_month_valid"
        ),
    )
    op.create_index("ix_clients_firm_id", "clients", ["firm_id"])

    op.create_table(
        "accounting_periods",
        _uuid_pk(),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("closed_by", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_accounting_periods"),
        sa.ForeignKeyConstraint(
            ["client_id", "firm_id"],
            ["clients.id", "clients.firm_id"],
            name="fk_accounting_periods_client_firm_clients",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("id", "firm_id", name="uq_accounting_periods_id_firm_id"),
        sa.UniqueConstraint("client_id", "label", name="uq_accounting_periods_client_id_label"),
        sa.CheckConstraint("end_date >= start_date", name="ck_accounting_periods_dates_ordered"),
        sa.CheckConstraint(
            "status IN ('open', 'closed')", name="ck_accounting_periods_status_valid"
        ),
        ExcludeConstraint(
            ("client_id", "="),
            (sa.text("daterange(start_date, end_date, '[]')"), "&&"),
            using="gist",
            name="ex_accounting_periods_no_overlap",
        ),
    )
    op.create_index("ix_accounting_periods_firm_id", "accounting_periods", ["firm_id"])
    op.create_index(
        "ix_accounting_periods_client_id_start_date",
        "accounting_periods",
        ["client_id", "start_date"],
    )

    op.create_table(
        "user_client_access",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True)),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("user_id", "client_id", name="pk_user_client_access"),
        sa.ForeignKeyConstraint(
            ["user_id", "firm_id"],
            ["users.id", "users.firm_id"],
            name="fk_user_client_access_user_firm_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["client_id", "firm_id"],
            ["clients.id", "clients.firm_id"],
            name="fk_user_client_access_client_firm_clients",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_user_client_access_client_id", "user_client_access", ["client_id"])

    op.create_table(
        "refresh_tokens",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        _ts("created_at"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_refresh_tokens_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    op.create_table(
        "audit_events",
        _uuid_pk(),
        sa.Column("firm_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_email", sa.String(320)),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target_type", sa.String(50)),
        sa.Column("target_id", postgresql.UUID(as_uuid=True)),
        sa.Column("client_id", postgresql.UUID(as_uuid=True)),
        sa.Column("outcome", sa.String(16), nullable=False, server_default="success"),
        sa.Column(
            "metadata", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("request_id", sa.String(100)),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index("ix_audit_events_firm_id_created_at", "audit_events", ["firm_id", "created_at"])
    op.create_index(
        "ix_audit_events_client_id_created_at", "audit_events", ["client_id", "created_at"]
    )
    op.create_index("ix_audit_events_target", "audit_events", ["target_type", "target_id"])

    # The audit trail is append-only: no UPDATE, DELETE or TRUNCATE, even for the app's DB role.
    op.execute(
        """
        CREATE FUNCTION audit_events_block_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only' USING ERRCODE = 'integrity_constraint_violation';
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_update_delete BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION audit_events_block_mutation()"
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_truncate BEFORE TRUNCATE ON audit_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_events_block_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_truncate ON audit_events")
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_update_delete ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS audit_events_block_mutation()")
    for table in (
        "audit_events",
        "refresh_tokens",
        "user_client_access",
        "accounting_periods",
        "clients",
        "users",
        "role_permissions",
        "roles",
        "permissions",
        "firms",
    ):
        op.drop_table(table)
