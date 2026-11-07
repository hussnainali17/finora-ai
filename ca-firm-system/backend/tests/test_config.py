import pytest
from pydantic import ValidationError

from app.core.config import Settings

BASE = {
    "database_url": "postgresql://u:p@h/db",
    "redis_url": "redis://:p@h:6379/0",
    "kafka_bootstrap_servers": "kafka:9092",
    "minio_endpoint": "http://minio:9000",
    "minio_access_key": "a",
    "minio_secret_key": "b",
    "litellm_base_url": "http://litellm:4000",
    "litellm_api_key": "sk-x",
    "jwt_secret": "x" * 40,
}


def test_secrets_are_masked_in_repr() -> None:
    s = Settings(**BASE)  # type: ignore[arg-type]
    assert "postgresql://u:p@h/db" not in repr(s)
    assert "sk-x" not in repr(s)
    assert "x" * 40 not in repr(s)


def test_placeholder_secret_rejected_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(**{**BASE, "app_env": "production", "litellm_api_key": "CHANGE_ME"})  # type: ignore[arg-type]


def test_placeholder_allowed_in_local() -> None:
    Settings(**{**BASE, "app_env": "local", "litellm_api_key": "CHANGE_ME"})  # type: ignore[arg-type]


def test_missing_required_secret_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")
    incomplete = {k: v for k, v in BASE.items() if k != "database_url"}
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **incomplete)  # type: ignore[arg-type,call-arg]


def test_short_jwt_secret_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(**{**BASE, "jwt_secret": "short"})  # type: ignore[arg-type]


def test_placeholder_jwt_secret_rejected_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(
            **{
                **BASE,
                "app_env": "production",
                "cookie_secure": True,
                "jwt_secret": "CHANGE_ME" * 5,
            }  # type: ignore[arg-type]
        )


def test_insecure_cookie_rejected_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(**{**BASE, "app_env": "production", "cookie_secure": False})  # type: ignore[arg-type]


def test_async_database_url_uses_asyncpg_driver() -> None:
    assert Settings(**BASE).async_database_url == "postgresql+asyncpg://u:p@h/db"  # type: ignore[arg-type]
