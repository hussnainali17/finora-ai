"""Identity and access models: firm, user, role, permission, assignments, refresh tokens.

Isolation design (see docs/database-design.md):
* Every tenant-owned row carries ``firm_id``.
* Child tables use COMPOSITE foreign keys ``(parent_id, firm_id)`` so the database itself
  refuses a row whose firm differs from its parent's firm.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col, updated_at_col, uuid_pk


class Firm(Base):
    __tablename__ = "firms"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Permission(Base):
    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(String(300), nullable=False)


class Role(Base):
    """System-defined roles (seeded by migration). Global, not per-firm, in Phase 1."""

    __tablename__ = "roles"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)

    permissions: Mapped[list["RolePermission"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_key: Mapped[str] = mapped_column(
        ForeignKey("roles.key", ondelete="CASCADE"), primary_key=True
    )
    permission_key: Mapped[str] = mapped_column(
        ForeignKey("permissions.key", ondelete="CASCADE"), primary_key=True
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Target for composite FKs from tenant-owned child tables.
        UniqueConstraint("id", "firm_id", name="uq_users_id_firm_id"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Globally unique so a login identifies exactly one firm.
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_key: Mapped[str] = mapped_column(
        ForeignKey("roles.key", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    role: Mapped[Role] = relationship(lazy="joined")
    firm: Mapped[Firm] = relationship(lazy="joined")


class Client(Base):
    """A client of the CA firm. Holds no accounting data in Phase 1 (and never a ledger)."""

    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("id", "firm_id", name="uq_clients_id_firm_id"),
        UniqueConstraint("firm_id", "code", name="uq_clients_firm_id_code"),
        CheckConstraint("status IN ('active', 'archived')", name="status_valid"),
        CheckConstraint("char_length(base_currency) = 3", name="currency_iso4217_len"),
        CheckConstraint("fiscal_year_end_month BETWEEN 1 AND 12", name="fiscal_month_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("firms.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(300))
    base_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="PKR", server_default="PKR"
    )
    fiscal_year_end_month: Mapped[int] = mapped_column(
        Integer, nullable=False, default=12, server_default="12"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class AccountingPeriod(Base):
    __tablename__ = "accounting_periods"
    __table_args__ = (
        ForeignKeyConstraint(
            ["client_id", "firm_id"],
            ["clients.id", "clients.firm_id"],
            name="fk_accounting_periods_client_firm_clients",
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "firm_id", name="uq_accounting_periods_id_firm_id"),
        # Target for documents' (period_id, client_id) foreign key.
        UniqueConstraint("id", "client_id", name="uq_accounting_periods_id_client_id"),
        UniqueConstraint("client_id", "label", name="uq_accounting_periods_client_id_label"),
        CheckConstraint("end_date >= start_date", name="dates_ordered"),
        CheckConstraint("status IN ('open', 'closed')", name="status_valid"),
        Index("ix_accounting_periods_client_id_start_date", "client_id", "start_date"),
        # A client's periods must never overlap (needs the btree_gist extension).
        ExcludeConstraint(
            ("client_id", "="),
            (text("daterange(start_date, end_date, '[]')"), "&&"),
            using="gist",
            name="ex_accounting_periods_no_overlap",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    firm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    start_date: Mapped[date] = mapped_column(nullable=False)
    end_date: Mapped[date] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default="open"
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class UserClientAccess(Base):
    """Explicit assignment of a user to a client (client-level authorization)."""

    __tablename__ = "user_client_access"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "firm_id"],
            ["users.id", "users.firm_id"],
            name="fk_user_client_access_user_firm_users",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["client_id", "firm_id"],
            ["clients.id", "clients.firm_id"],
            name="fk_user_client_access_client_firm_clients",
            ondelete="CASCADE",
        ),
        Index("ix_user_client_access_client_id", "client_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    firm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at_col()


class RefreshToken(Base):
    """Server-side record of an opaque refresh token. Only the SHA-256 hash is stored.

    Tokens rotate on every use and belong to a ``family_id``. Presenting an already-rotated
    (revoked) token is treated as theft and revokes the whole family.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_family_id", "family_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
