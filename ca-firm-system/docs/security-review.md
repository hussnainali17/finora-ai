# Production Security Review & Threat Model (Phase 11)

This document provides a comprehensive security assessment of the CA Firm System against the OWASP Top 10, multi-tenant isolation requirements, and accounting compliance principles.

---

## 1. Multi-Tenant & Client Isolation

### Layer 1: Query Layer Filtering
- All data access is filtered by `principal.firm_id` extracted from verified JWT tokens.
- Client access is strictly governed by `UserClientAccess` assignments. Non-admin users are denied access to unassigned clients.

### Layer 2: Schema Composite Foreign Keys
- All tenant child tables carry composite foreign keys:
  - `(client_id, firm_id) REFERENCES clients(id, firm_id)`
  - `(period_id, client_id) REFERENCES accounting_periods(id, client_id)`
- Prevents cross-tenant insertion even in the event of an application logic defect.

### Layer 3: Automated Isolation Test Suite
- `backend/tests/test_isolation.py` and `backend/tests/test_security.py` execute automated cross-firm access attempts across all endpoints and verify 404 responses (preventing resource existence disclosure).

---

## 2. Authentication & Session Security

- **Password Hashing**: Argon2id with memory-hard parameters and per-password unique salt.
- **Brute-Force Protection**: Account lockout after consecutive failed attempts (`LOGIN_MAX_FAILED_ATTEMPTS`).
- **Token Model**: Short-lived access tokens (15m) + rotating refresh token family with reuse theft detection.
- **CSRF Defense**: `SameSite=Strict`, HTTP-only, `Secure` cookie flag in production, and `Origin` header validation against `CORS_ALLOWED_ORIGINS`.

---

## 3. Storage & Document Processing Security

- **Storage Location**: Original files reside outside the database in MinIO/S3. The database stores only object keys, sizes, and SHA-256 hashes.
- **Immutability Trigger**: Database trigger blocks UPDATE or DELETE on uploaded document metadata.
- **Zip-Bomb & Memory Guards**: Extraction pipelines limit max uncompressed bytes (500 MB) and max pages (300 pages).
- **No Direct LLM arithmetic**: AI agents never perform arithmetic; all arithmetic runs through deterministic Python `Decimal` algorithms with explicit rounding rules.

---

## 4. Immutable Audit Trail

- `audit_events` and `llm_call_logs` have database triggers preventing UPDATE, DELETE, and TRUNCATE.
- Tamper-evident record of all CA decisions, file uploads, and model parameter changes.

---

## 5. Network & Infrastructure Hardening

- **TLS Termination**: Modern TLS 1.2 / 1.3 ciphers only (`infrastructure/nginx/nginx.prod.conf`).
- **Security Headers**:
  - `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
  - `Content-Security-Policy: default-src 'self' ...`
  - `X-Frame-Options: DENY`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
- **Rate Limiting**: Rate-limiting zones for `/api/v1/auth/login` (5 req/min) and general endpoints.
