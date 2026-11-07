"""Worker process configuration. All values come from environment variables."""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"

    # Database (for job state and idempotency tracking)
    database_url: SecretStr

    # Kafka
    kafka_bootstrap_servers: str
    kafka_consumer_group_id: str = "ca-firm-workers"
    kafka_max_poll_interval_ms: int = 300_000
    kafka_session_timeout_ms: int = 30_000
    kafka_auto_offset_reset: str = "earliest"
    kafka_max_retries: int = 3
    kafka_retry_backoff_ms: int = 500
    dead_letter_suffix: str = "-dlq"

    # Health check server
    worker_health_port: int = Field(default=8001, ge=1024, le=65535)

    @property
    def async_database_url(self) -> str:
        """SQLAlchemy async URL (asyncpg driver)."""
        url = self.database_url.get_secret_value()
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+asyncpg://" + url[len(prefix) :]
        return url
