"""Typed application configuration.

All values come from environment variables (see .env.example). Secrets use
SecretStr so they never appear in logs or repr() output. There are no
credential defaults: a missing secret fails fast at startup.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_MARKER = "CHANGE_ME"
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ca-firm-backend"
    app_env: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8080"])

    # Dependencies (required; no credential defaults)
    database_url: SecretStr
    redis_url: SecretStr
    kafka_bootstrap_servers: str
    minio_endpoint: str
    minio_access_key: SecretStr
    minio_secret_key: SecretStr
    minio_bucket: str = "ca-firm-files"
    litellm_base_url: str
    litellm_api_key: SecretStr  # server-side only; never sent to the browser

    health_check_timeout_seconds: float = 3.0

    # --- Authentication (Phase 1) -------------------------------------------
    # HS256 signing key for access tokens. Server-side only; >= 32 chars.
    jwt_secret: SecretStr
    jwt_issuer: str = "ca-firm-system"
    jwt_audience: str = "ca-firm-api"
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_ttl_days: int = Field(default=7, ge=1, le=30)
    # Cookie `Secure` flag. Must be true in staging/production (enforced below).
    cookie_secure: bool = False
    login_max_failed_attempts: int = Field(default=5, ge=3, le=20)
    login_lockout_minutes: int = Field(default=15, ge=1, le=1440)

    # --- Object storage / uploads (Phase 2) -----------------------------------
    s3_region: str = "us-east-1"
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, ge=1024)
    # Comma-separated lowercase extensions accepted for upload.
    allowed_upload_extensions: str = "pdf,xlsx,xls,csv,png,jpg,jpeg"

    # --- Event publication (Phase 2; Phase 5 builds the full framework on this) ----
    file_uploaded_topic: str = "file-uploaded"
    # Background outbox relay. Disabled in tests, which drive the relay explicitly.
    outbox_relay_enabled: bool = True
    outbox_poll_interval_seconds: float = Field(default=2.0, gt=0)

    # --- Data intake / Agent 1 (Phase 3) -------------------------------------------
    # Background loop that extracts uploaded files. Disabled in tests (they call the service).
    intake_enabled: bool = True
    intake_poll_interval_seconds: float = Field(default=3.0, gt=0)
    intake_stale_after_minutes: int = Field(default=15, ge=1)
    intake_max_rows: int = Field(default=100_000, ge=100)  # rows kept per table; excess is flagged
    intake_max_pages: int = Field(default=300, ge=1)
    intake_max_uncompressed_bytes: int = Field(default=500 * 1024 * 1024, ge=1024)  # zip-bomb guard
    # Used only when a date such as 03/04/2025 cannot be resolved from the data itself.
    intake_default_date_order: Literal["DMY", "MDY"] = "DMY"
    intake_ocr_enabled: bool = True
    intake_ocr_timeout_seconds: int = Field(default=300, ge=10)
    intake_ocr_language: str = "eng"
    # LLM assistance for ambiguous columns. Which model is used comes from the firm's model
    # settings (Phase 4); nothing is sent unless a firm admin has enabled a model.
    intake_llm_enabled: bool = True
    intake_llm_min_confidence: float = Field(default=0.7, ge=0, le=1)

    # --- LLM gateway (Phase 4) -----------------------------------------------------
    # Every AI call goes through the LiteLLM proxy at LITELLM_BASE_URL with these limits.
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    llm_max_retries: int = Field(default=2, ge=0, le=5)  # retries of ONE alias, before any fallback
    llm_retry_backoff_seconds: float = Field(default=0.5, ge=0, le=10)  # doubles each retry
    llm_availability_timeout_seconds: float = Field(default=3.0, gt=0, le=30)

    @property
    def upload_extensions(self) -> frozenset[str]:
        return frozenset(
            e.strip().lower().lstrip(".")
            for e in self.allowed_upload_extensions.split(",")
            if e.strip()
        )

    @property
    def async_database_url(self) -> str:
        """SQLAlchemy async URL derived from DATABASE_URL (asyncpg driver)."""
        url = self.database_url.get_secret_value()
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+asyncpg://" + url[len(prefix) :]
        return url

    @model_validator(mode="after")
    def _validate_secrets_and_cookie_policy(self) -> "Settings":
        if len(self.jwt_secret.get_secret_value()) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(f"JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters")
        if self.app_env in ("staging", "production"):
            secrets = {
                "DATABASE_URL": self.database_url,
                "REDIS_URL": self.redis_url,
                "MINIO_ACCESS_KEY": self.minio_access_key,
                "MINIO_SECRET_KEY": self.minio_secret_key,
                "LITELLM_API_KEY": self.litellm_api_key,
                "JWT_SECRET": self.jwt_secret,
            }
            bad = [k for k, v in secrets.items() if PLACEHOLDER_MARKER in v.get_secret_value()]
            if bad:
                raise ValueError(
                    f"Placeholder secret values are not allowed in {self.app_env}: {bad}"
                )
            if not self.cookie_secure:
                raise ValueError(f"COOKIE_SECURE must be true in {self.app_env}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
