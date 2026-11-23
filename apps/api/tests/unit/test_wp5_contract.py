"""Verify public contract boundaries without a database connection."""

from fastapi.testclient import TestClient

from aq_uai_api.main import create_app


def test_directory_entry_points_require_authentication_and_disable_caching():
    with TestClient(create_app()) as browser:
        for path in ("users", "units", "groups", "roles", "audit-events", "directory/capabilities"):
            response = browser.get(f"/api/v1/{path}")
            assert response.status_code == 401
            assert response.headers["Cache-Control"] == "no-store"
            assert response.json()["request_id"] == response.headers["X-Request-ID"]
