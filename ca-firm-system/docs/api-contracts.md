# API contracts (Phase 1 + Phase 2)

Base path `/api/v1`. JSON. Errors: `{"detail": "<message>"}` (422 validation errors use FastAPI's list
form). Authenticated routes need `Authorization: Bearer <access token>`. Interactive docs: `/docs`.

Status codes: `401` not authenticated / bad token, `403` authenticated but missing permission,
`404` not found **or outside your firm/client scope**, `409` conflict (duplicate, overlap, state),
`422` invalid input.

## Auth
| Method & path | Permission | Notes |
|---|---|---|
| `POST /auth/login` `{email, password}` | public | 200 `{access_token, token_type, expires_in, user}` + `Set-Cookie: ca_refresh`. Generic 401 for any failure. |
| `POST /auth/refresh` | refresh cookie | Rotates the cookie; returns the same body as login. 403 on untrusted `Origin`. |
| `POST /auth/logout` | refresh cookie | 204; idempotent; clears cookie; kills the session's access tokens. |
| `GET /auth/me` | any user | `{id, email, full_name, firm_id, firm_name, role, permissions[]}` |
| `POST /auth/change-password` `{current_password, new_password}` | any user | 204; revokes all sessions. |

## Users and roles (`user:read` / `user:manage`, firm-scoped)
| `GET /roles` (any user) | `GET /users?limit&offset` | `POST /users` `{email, full_name, role_key, password}` -> 201 |
|---|---|---|
| `GET /users/{id}` | `PATCH /users/{id}` `{full_name?, role_key?, is_active?}` | A firm must keep >= 1 active Firm Admin (409). Deactivating revokes sessions. |

## Clients (scope: assigned clients; Firm Admin = all in firm)
| Method & path | Permission |
|---|---|
| `GET /clients?limit&offset&status&q` | `client:read` |
| `POST /clients` `{code, name, legal_name?, base_currency, fiscal_year_end_month?, notes?}` | `client:create` (non-admin creator is auto-assigned) |
| `GET /clients/{id}` | `client:read` |
| `PATCH /clients/{id}` `{name?, legal_name?, fiscal_year_end_month?, notes?, status?}` | `client:update` (`status: archived` to archive) |
| `GET /clients/{id}/access` | `client:access_manage` |
| `POST /clients/{id}/access` `{user_id}` -> 201 (idempotent) | `client:access_manage` (user must be in the same firm and active) |
| `DELETE /clients/{id}/access/{user_id}` -> 204 | `client:access_manage` |

## Accounting periods
| Method & path | Permission |
|---|---|
| `GET /clients/{id}/periods` | `period:read` |
| `POST /clients/{id}/periods` `{label, start_date, end_date}` | `period:create` (409 on overlap / duplicate label / archived client) |
| `GET /clients/{id}/periods/{pid}` | `period:read` |
| `PATCH /clients/{id}/periods/{pid}` `{label?, start_date?, end_date?}` | `period:update` (open periods only) |
| `POST /clients/{id}/periods/{pid}/close` / `.../reopen` | `period:close` |

## Documents (Phase 2) - `/clients/{client_id}/periods/{period_id}/documents`
| Method & path | Permission | Notes |
|---|---|---|
| `POST` (multipart: `file`, `category`) | `document:upload` | 201 `DocumentOut`. Period must be open, client active. Errors: 413 too large, 415 type/content mismatch, 422 empty file/bad category, 409 closed period or **duplicate**, 503 storage unavailable. |
| `GET ?limit&offset&category&status&q` | `document:read` | Removed files are not listed. |
| `GET /{id}` | `document:read` | |
| `GET /{id}/download` | `document:read` | Streams the original through the API (no presigned/public URLs). `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`, `X-Content-SHA256`. Audited. |
| `DELETE /{id}` -> 204 | `document:delete` | Soft delete; object retained; open periods only. |

Duplicate response (409):
`{"detail": "This exact file has already been uploaded to this period", "code": "duplicate_document",
"existing_document_id": "...", "existing_filename": "..."}` - only ever reveals a file inside a client the
caller can already access.

`DocumentOut`: `{id, client_id, period_id, category, original_filename, content_type, size_bytes, sha256,
status, uploaded_by, uploaded_by_email, created_at}`.

Accepted types (configurable): pdf, xlsx, xls, csv, png, jpg/jpeg. The extension must be on the allow-list
**and** the bytes must match it (PDF/PNG/JPEG/OLE signatures; xlsx must be a zip containing
`[Content_Types].xml` and `xl/`; csv must be NUL-free text). Macro-enabled workbooks (.xlsm) and other
formats are rejected. Max size `MAX_UPLOAD_BYTES` (50 MiB).

## Audit
`GET /audit-events?limit&offset&action&client_id&actor_user_id&since&until` - `audit:read`.
Firm Admin: whole firm. Others with the permission: only events tied to their assigned clients.

## Health (unchanged from Phase 0)
`GET /health/live`, `GET /health/ready`.
