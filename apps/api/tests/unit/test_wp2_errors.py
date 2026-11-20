"""Exercise request correlation and safe errors through test-only routes."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import UniqueViolation
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, OperationalError

from aq_uai_api.api.errors import DomainError, ErrorCode
from aq_uai_api.main import create_app

SYNTHETIC_SECRET = "wp2-sensitive-value"


class Submission(BaseModel):
    password: int


def test_errors_are_safe_and_correlated(caplog):
    app = create_app()

    @app.post("/test-validation")
    def validate(payload: Submission):
        return payload

    @app.get("/test-unexpected")
    def unexpected():
        raise RuntimeError(SYNTHETIC_SECRET)

    @app.get("/test-database")
    def database():
        raise OperationalError(
            "SELECT :value",
            {"value": SYNTHETIC_SECRET},
            RuntimeError(f"postgresql://user:{SYNTHETIC_SECRET}@example"),
        )

    with TestClient(app) as client:
        responses = [
            client.post("/test-validation", json={"password": SYNTHETIC_SECRET}),
            client.get("/test-unexpected", headers={"X-Request-ID": SYNTHETIC_SECRET}),
            client.get("/test-database"),
        ]

    ids = set()
    for response, status in zip(responses, [422, 500, 500], strict=True):
        assert response.status_code == status
        assert SYNTHETIC_SECRET not in response.text
        request_id = response.headers["X-Request-ID"]
        assert UUID(request_id).version == 4
        assert response.json()["request_id"] == request_id
        assert request_id in caplog.text
        ids.add(request_id)
    assert len(ids) == len(responses)
    assert SYNTHETIC_SECRET not in caplog.text


@pytest.mark.parametrize(
    ("code", "status"),
    [
        (ErrorCode.AUTH_REQUIRED, 401),
        (ErrorCode.FORBIDDEN, 403),
        (ErrorCode.NOT_FOUND, 404),
        (ErrorCode.CONFLICT, 409),
        (ErrorCode.RATE_LIMITED, 429),
        (ErrorCode.SERVICE_UNAVAILABLE, 503),
    ],
)
def test_domain_error_uses_stable_public_contract(code, status):
    app = create_app()

    @app.get("/test-domain")
    def fail():
        raise DomainError(code)

    with TestClient(app) as client:
        response = client.get("/test-domain")
    assert response.status_code == status
    assert response.json()["code"] == code.name
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_uniqueness_error_produces_safe_conflict(caplog):
    app = create_app()

    @app.get("/test-conflict")
    def conflict():
        raise IntegrityError(
            "INSERT INTO test VALUES (:name)",
            {"name": SYNTHETIC_SECRET},
            UniqueViolation(SYNTHETIC_SECRET),
        )

    with TestClient(app) as client:
        response = client.get("/test-conflict")
    assert response.status_code == 409 and response.json()["code"] == "CONFLICT"
    assert SYNTHETIC_SECRET not in response.text + caplog.text
