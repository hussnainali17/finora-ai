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

    @model_validator(mode="after")
    def _reject_placeholder_secrets_outside_local(self) -> "Settings":
        if self.app_env in ("staging", "production"):
            secrets = {
                "DATABASE_URL": self.database_url,
                "REDIS_URL": self.redis_url,
                "MINIO_ACCESS_KEY": self.minio_access_key,
                "MINIO_SECRET_KEY": self.minio_secret_key,
                "LITELLM_API_KEY": self.litellm_api_key,
            }
            bad = [k for k, v in secrets.items() if PLACEHOLDER_MARKER in v.get_secret_value()]
            if bad:
                raise ValueError(
                    f"Placeholder secret values are not allowed in {self.app_env}: {bad}"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
