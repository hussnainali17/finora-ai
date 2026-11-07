# Database and authorization design (Phase 1 + Phase 2)

PostgreSQL 16, SQLAlchemy 2 (async), Alembic. This is an **accounting review** product: there is no
ledger, journal, posting or transaction table, and a test (`test_no_ledger_or_bookkeeping_tables_exist`)
fails if one appears.

## Entity relationships

```
firms 1──* users *──1 roles *──* permissions            (role_permissions)
  │          │
  │          └──* user_client_access *──1 clients       (explicit client assignment)
  │
  └──* clients 1──* accounting_periods
clients 1──* documents *──1 accounting_periods          (Phase 2; metadata only - files live in S3/MinIO)
outbox_events                                            (Phase 2; events awaiting Kafka publication)
users 1──* refresh_tokens                                (hashed, rotating, per-session family)
audit_events                                             (append-only; no FKs by design)
```

| Table | Purpose | Notes |
|---|---|---|
| `firms` | Tenant (the CA firm). | `slug` unique. `is_active=false` blocks all its users. |
| `users` | Staff/client users. | One firm per user, one role per user. `email` is **globally unique and lowercase** (CHECK) so a login identifies exactly one firm. Argon2id `password_hash`, `failed_login_count`, `locked_until`. |
| `roles`, `permissions`, `role_permissions` | RBAC catalogue. | Four system roles, seeded by migration; mirrored in `app/core/permissions.py` (a test asserts they match). |
| `clients` | A client of the firm. | `(firm_id, code)` unique. `status` active/archived. `base_currency` is a 3-letter ISO code. |
| `accounting_periods` | A client's reporting period. | `end_date >= start_date`; `(client_id, label)` unique; **exclusion constraint forbids overlapping periods per client** (`btree_gist`). `open`/`closed`. |
| `user_client_access` | Who may work on which client. | PK `(user_id, client_id)`. |
| `refresh_tokens` | Server-side session records. | Only the SHA-256 of the opaque token is stored. `family_id` = one login session. |
| `audit_events` | Audit trail. | Append-only: DB triggers reject UPDATE, DELETE and TRUNCATE. No foreign keys so history survives and never blocks changes. |

All primary keys are UUIDs (`gen_random_uuid()`); all timestamps are `timestamptz`.

## Tenant isolation: three independent layers

1. **Query layer.** Every service takes a `Principal` (built from the database, never from request
   input) and filters by `principal.firm_id`. Client-scoped data is reached only through
   `authz.get_accessible_client()` / `authz.client_scope()`. `firm_id` is never accepted from a request
   body (`extra="forbid"` rejects it) and path ids are always re-checked against the caller's scope.
2. **Schema layer.** Child tables carry `firm_id` and use **composite foreign keys**
   `(client_id, firm_id) -> clients(id, firm_id)` and `(user_id, firm_id) -> users(id, firm_id)`.
   Even a buggy query or a hand-written INSERT cannot create a period or assignment whose firm differs
   from its parent's (tested by `test_database_rejects_cross_firm_rows...`).
3. **Test layer.** `tests/test_isolation.py` proves cross-firm and cross-client access is denied for
   reads, writes, listings, nested resources, user directory, access grants and the audit trail.

Not implemented (deliberately, see decisions #15): PostgreSQL row-level security. It can be added in
Phase 11 as a fourth layer.

## Authorization model

**Permissions** (`app/core/permissions.py`): `user:read`, `user:manage`, `client:read`, `client:create`,
`client:update`, `client:access_all`, `client:access_manage`, `period:read`, `period:create`,
`period:update`, `period:close`, `audit:read`.

| Permission | Firm Admin | CA / Reviewer | Accountant | Client User |
|---|:-:|:-:|:-:|:-:|
| `user:read`, `user:manage` | ✔ | | | |
| `client:read` | ✔ | ✔ | ✔ | ✔ |
| `client:create`, `client:update` | ✔ | ✔ | | |
| `client:access_all` (reach every client in the firm) | ✔ | | | |
| `client:access_manage` (assign users to clients) | ✔ | | | |
| `period:read` | ✔ | ✔ | ✔ | ✔ |
| `period:create`, `period:update` | ✔ | ✔ | ✔ | |
| `period:close` (close / reopen) | ✔ | ✔ | | |
| `audit:read` | ✔ (whole firm) | ✔ (assigned clients only) | | |

**Two checks on every request:**
1. *Permission* - does the role grant the action? No -> **403**.
2. *Scope* - is the resource in the caller's firm, and (unless `client:access_all`) assigned to the
   caller? No -> **404**. Out-of-scope resources are reported as "not found", never "forbidden", so
   other firms'/clients' existence is not disclosed. Permission is checked first, then scope.

**Live permissions.** Roles/permissions are *not* in the JWT. Each request loads the user, role and
session from the database, so deactivation, role changes and access revocation apply instantly.

## Authentication

Self-contained secure JWT (the roadmap allows "OIDC provider *or* secure JWT"):

* **Login** `POST /auth/login` -> short-lived (15 min) HS256 **access token** in the response body +
  opaque **refresh token** in an `HttpOnly; SameSite=Strict; Path=/api/v1/auth` cookie (`Secure` outside
  local dev). The browser keeps the access token in memory only.
* **Refresh** rotates the refresh token on every use. Replaying an already-rotated token is treated
  as theft: the whole session family is revoked and an `auth.refresh_reuse_detected` event is written.
* **Logout** revokes the session family. Access tokens carry the session id (`sid`), and every request
  verifies that session is still live, so logout takes effect immediately rather than after 15 minutes.
* **Passwords**: Argon2id, 12-128 chars. Unknown-user logins burn an equal hash verification and return
  the same generic 401. **Lockout**: 5 failures -> 15 min (configurable). Changing a password revokes all
  sessions.
* **JWT validation**: algorithm allow-list (`HS256` only), `iss`, `aud`, `exp`, `iat`, `typ=access`
  all required.
* **CSRF**: bearer tokens are not auto-sent by browsers; the cookie endpoints (`refresh`, `logout`) add
  SameSite=Strict plus an `Origin` allow-list check.
* **No self-registration.** The first firm and Firm Admin are created with
  `python -m app.cli bootstrap-firm`; further users are created by a Firm Admin.

Swapping to Keycloak/OIDC later only replaces `core/security.decode_access_token` and the login/refresh
service functions; authorization is independent of how identity is proven.

## Audit trail

`record_audit()` adds an event **in the same transaction** as the change it describes (commit together
or not at all). Each event stores actor id + email snapshot, action, target type/id, client id, outcome
(`success`/`failure`), JSON metadata, source IP and request/correlation id. Keys that look like
credentials (`password`, `token`, `secret`, `api_key`, `hash`, ...) are stripped before storage.

Audited actions: `auth.login`, `auth.login_failed`, `auth.logout`, `auth.refresh_reuse_detected`,
`auth.password_changed`, `auth.password_change_failed`, `user.created`, `user.updated`,
`user.deactivated`, `user.role_changed`, `client.created`, `client.updated`, `client.archived`,
`client.active`, `client_access.granted`, `client_access.revoked`, `period.created`, `period.updated`,
`period.closed`, `period.reopened`, `firm.bootstrapped`.

## Migrations

`backend/migrations/versions/0001_identity_tenancy_audit.py` builds everything from an empty database
(it also enables `btree_gist` and seeds roles/permissions). `alembic check` runs in the test suite and
fails if the ORM models and migrations drift apart. Run: `make migrate` (Docker) or
`cd backend && alembic upgrade head` (needs `DATABASE_URL`).

## Phase 2 additions: documents and the outbox

`documents` holds **metadata only**; the bytes are in S3/MinIO under
`firms/{firm}/clients/{client}/periods/{period}/{document_id}/original` (no user-supplied text in keys).

| Column(s) | Notes |
|---|---|
| `client_id, firm_id` | composite FK to `clients(id, firm_id)`. |
| `period_id, client_id` | composite FK to `accounting_periods(id, client_id)`: **a document's period must belong to its client** (needs `uq_accounting_periods_id_client_id`). |
| `uploaded_by, firm_id` | composite FK to `users(id, firm_id)`. |
| `category` | trial_balance, bank_statement, invoice, receipt, contract, fixed_asset_schedule, inventory_report, payroll_schedule, other. |
| `original_filename`, `content_type`, `size_bytes`, `sha256`, `object_key` | sanitised display name; content type derived from verified bytes; SHA-256 of the exact bytes. |
| `status` | `uploaded` -> `queued` (event published) -> `processing` -> `processed` / `failed`. Phase 2 sets the first two; Phase 3+ the rest. |
| `deleted_at`, `deleted_by` | soft delete. The object is **retained**. |

* **Immutable originals (database-enforced).** A trigger rejects any UPDATE of the file-identity columns
  (firm, client, period, category, filename, key, content type, size, hash, uploader, created_at) and any
  DELETE. Only `status`, `updated_at` and `deleted_*` may change. The object key embeds a fresh UUID so no
  upload ever overwrites an existing object, and the MinIO bucket is versioned.
* **Duplicate detection.** Partial unique index `uq_documents_live_hash (client_id, period_id, sha256)
  WHERE deleted_at IS NULL`. The same bytes cannot be live twice in a client period (a removed file can be
  re-uploaded; the same file in a different period is allowed). The service also pre-checks to avoid
  uploading bytes it will reject, and the index settles concurrent races.
* **Permissions added:** `document:read` (all roles), `document:upload` (Firm Admin, CA/Reviewer,
  Accountant), `document:delete` (Firm Admin, CA/Reviewer). Scope rules are unchanged: client assignment
  applies, out-of-scope = 404. Closed periods and archived clients accept neither uploads nor removals.

`outbox_events` implements the **transactional outbox**: an event row is inserted in the same transaction
as the document, so an event exists if and only if the upload committed. See
[event-contracts.md](event-contracts.md).

Audited actions added: `document.uploaded`, `document.upload_rejected`, `document.duplicate_rejected`,
`document.downloaded`, `document.deleted`.
