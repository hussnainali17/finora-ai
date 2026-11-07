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

Authentication, authorization and tenant/client isolation are implemented in Phase 1. This document makes no
compliance or certification claims.
