"""Health/readiness endpoint behavior (no PostgreSQL required)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.routes.health import _database_healthy
from app.main import create_app
from tests.support import make_settings


def build_client() -> TestClient:
    # sqlite engine satisfies the SELECT 1 probe without PostgreSQL.
    settings = make_settings(database_url="sqlite+pysqlite:///:memory:")
    return TestClient(create_app(settings))


class TestLiveness:
    def test_healthz_reports_ok(self) -> None:
        client = build_client()

        response = client.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestReadiness:
    def test_readyz_ok_when_database_probe_succeeds(self) -> None:
        client = build_client()
        app = client.app
        app.dependency_overrides[_database_healthy] = lambda: True

        response = client.get("/readyz")

        assert response.status_code == 200
        assert response.json() == {"status": "ready", "database": "ok"}

    def test_readyz_returns_503_when_database_unavailable(self) -> None:
        client = build_client()
        app = client.app
        app.dependency_overrides[_database_healthy] = lambda: False

        response = client.get("/readyz")

        assert response.status_code == 503
        assert response.json() == {"status": "not_ready", "database": "unavailable"}

    def test_default_probe_executes_against_configured_engine(self) -> None:
        client = build_client()

        response = client.get("/readyz")

        assert response.status_code == 200
