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


def test_async_database_url_maps_schema_to_search_path() -> None:
    settings = Settings(
        **{
            **BASE,
            "database_url": "postgresql://user:pass@host/db?schema=tenant",
        }  # type: ignore[arg-type]
    )
    assert settings.async_database_url == "postgresql+asyncpg://user:pass@host/db"
    assert settings.async_database_connect_args == {
        "server_settings": {"search_path": "tenant"}
    }


def test_intake_defaults_are_safe_and_validated() -> None:
    s = Settings(**BASE)  # type: ignore[arg-type]
    assert s.intake_default_date_order == "DMY"
    assert s.intake_llm_min_confidence == 0.7
    assert s.intake_max_rows >= 100 and s.intake_max_pages >= 1
    with pytest.raises(ValidationError):
        Settings(**{**BASE, "intake_default_date_order": "YMD"})  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Settings(**{**BASE, "intake_llm_min_confidence": 1.5})  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Settings(**{**BASE, "intake_poll_interval_seconds": 0})  # type: ignore[arg-type]
