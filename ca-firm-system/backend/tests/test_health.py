import pytest
from fastapi.testclient import TestClient

from app.api import health as health_module
from app.core.config import Settings, get_settings
from app.integrations import health as checks
from app.integrations.health import DependencyStatus, run_dependency_checks


def test_live_returns_ok(client: TestClient) -> None:
    resp = client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_ok_when_all_dependencies_up(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake(_: Settings) -> list[DependencyStatus]:
        return [DependencyStatus("postgres", True, 1.0), DependencyStatus("redis", True, 1.0)]

    monkeypatch.setattr(health_module, "run_dependency_checks", fake)
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ready_503_when_a_dependency_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake(_: Settings) -> list[DependencyStatus]:
        return [
            DependencyStatus("postgres", True, 1.0),
            DependencyStatus("kafka", False, 3.0, "OSError"),
        ]

    monkeypatch.setattr(health_module, "run_dependency_checks", fake)
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert {d["name"]: d["ok"] for d in body["dependencies"]} == {"postgres": True, "kafka": False}


async def test_failed_check_reports_only_exception_class_not_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(_: Settings) -> None:
        raise RuntimeError("postgresql://user:supersecret@host/db failed")

    monkeypatch.setitem(checks.CHECKS, "postgres", boom)
    results = await run_dependency_checks(get_settings())
    pg = next(r for r in results if r.name == "postgres")
    assert pg.ok is False
    assert pg.detail == "RuntimeError"
    assert "supersecret" not in repr(results)


def test_correlation_id_is_generated_and_echoed(client: TestClient) -> None:
    assert client.get("/api/v1/health/live").headers["X-Request-ID"]
    echoed = client.get("/api/v1/health/live", headers={"X-Request-ID": "abc-123"})
    assert echoed.headers["X-Request-ID"] == "abc-123"
