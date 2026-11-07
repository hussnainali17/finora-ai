# Secrets and security policy (Phase 0)

1. `.env` is git-ignored; only `.env.example` (placeholders) is committed. `CHANGE_ME` values are rejected by the
   backend in `staging`/`production`.
2. Provider API keys (OpenAI, Anthropic, Gemini, ...) are set only on the `litellm` container. The backend,
   workers and frontend never receive them.
3. Frontend variables (`VITE_*`) are public by design - never place secrets in them.
4. Never put secrets, API keys or full document contents in logs or Kafka messages.
5. All host ports are bound to `127.0.0.1` in local Docker Compose.
6. Secret scanning: `gitleaks` via pre-commit (`pre-commit install`) and in CI.
7. Rotate any credential that was ever committed or shared; production secrets live in a secrets manager
   (Phase 11).

## Phase 1 additions

8. `JWT_SECRET` (>= 32 chars, `openssl rand -hex 32`) signs access tokens. Server-side only; rotating it signs
   everyone out. The backend refuses to start with a short secret, and with a `CHANGE_ME` secret or
   `COOKIE_SECURE=false` in staging/production.
9. The access token is held in browser **memory only** (never web storage). The refresh token is an
   `HttpOnly`, `SameSite=Strict`, path-scoped cookie and only its SHA-256 is stored in the database.
10. Passwords are Argon2id hashed; never logged; never stored in audit metadata (keys named like
    `password`/`token`/`secret`/`api_key`/`hash` are stripped).
11. Brute force: per-account lockout (5 failures -> 15 min) in the backend plus a per-IP `limit_req`
    on `/auth/login` in Nginx. Redis-based global rate limiting is a Phase 11 item.
12. Tenant/client isolation is enforced in the service layer and by composite foreign keys - see
    [database-design.md](database-design.md). Out-of-scope resources return 404.
13. The audit trail is append-only at the database level.
14. Create the first account with `python -m app.cli bootstrap-firm`; the password comes from
    `BOOTSTRAP_ADMIN_PASSWORD` or an interactive no-echo prompt, never a command-line argument.

**Known limitations (tracked for Phase 11):** audit-log IPs show the proxy address until uvicorn is run
with `--proxy-headers` and a restricted `--forwarded-allow-ips`; HS256 is a shared-secret scheme (move to
asymmetric keys if tokens are ever verified by other services); no MFA; no email-based password reset (an
admin sets passwords); two browser tabs refreshing simultaneously are handled by a single-flight lock in
the frontend, but two *separate devices* sharing one cookie jar would trip reuse detection and be signed
out. This document makes no compliance or certification claims.
