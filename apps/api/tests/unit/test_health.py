"""Phase-1 HTTP contract tests without a live DB."""

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from aq_uai_api.db.models import AppMetadata
from aq_uai_api.db.schema import REQUIRED_SCHEMA_REVISION
from aq_uai_api.db.session import get_session
from aq_uai_api.main import create_app


class _ScalarResult:
    def all(self) -> list[str]:
        return [REQUIRED_SCHEMA_REVISION]


class FakeDatabase:
    def scalars(self, statement: object) -> _ScalarResult:
        return _ScalarResult()

    def get(self, model: type, key: str) -> AppMetadata | None:
        assert model is AppMetadata
        values = {"name": "AQ EduUAI", "milestone": "phase-1-foundation"}
        return AppMetadata(key=key, value=values[key]) if key in values else None


class BrokenDatabase(FakeDatabase):
    def scalars(self, statement: object) -> _ScalarResult:
        raise OperationalError("SELECT 1", {}, RuntimeError("database offline"))

    def get(self, model: type, key: str) -> AppMetadata | None:
        raise OperationalError("SELECT 1", {}, RuntimeError("database offline"))


def get_client(database: FakeDatabase | BrokenDatabase) -> TestClient:
    app = create_app()

    def override():
        yield database

    app.dependency_overrides[get_session] = override
    return TestClient(app)


def test_health_does_not_require_database() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.1.0"


def test_ready_when_database_and_migration_available() -> None:
    with get_client(FakeDatabase()) as client:
        response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}


def test_ready_fails_closed_when_database_is_down() -> None:
    with get_client(BrokenDatabase()) as client:
        response = client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DATABASE_UNAVAILABLE"


def test_info_reads_database_values() -> None:
    with get_client(FakeDatabase()) as client:
        response = client.get("/api/v1/system/info")
    assert response.status_code == 200
    assert response.json() == {
        "name": "AQ EduUAI",
        "milestone": "phase-1-foundation",
        "source": "postgresql",
    }


def test_system_info_fails_closed() -> None:
    with get_client(BrokenDatabase()) as client:
        response = client.get("/api/v1/system/info")
    assert response.status_code == 503


def test_business_routes_not_pretended_to_exist() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/providers").status_code == 404
        assert client.get("/api/v1/users").status_code == 401
        assert client.get("/api/v1/ledger").status_code == 404
