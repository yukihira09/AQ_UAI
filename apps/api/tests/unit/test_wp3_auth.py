"""Public authentication contract tests requiring no database."""

from fastapi.testclient import TestClient

from aq_uai_api.auth.security import client_peer
from aq_uai_api.core.config import Settings
from aq_uai_api.main import create_app


def test_me_rejects_missing_session_without_caching_response():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"
    assert response.headers["Cache-Control"] == "no-store"


def test_forwarded_address_requires_exact_non_loopback_proxy_peer():
    config = Settings(auth_trusted_proxy_ip="172.22.0.6")
    assert client_peer(config, "172.22.0.6", ["192.0.2.5"]) == "192.0.2.5"
    assert client_peer(config, "172.22.0.9", ["192.0.2.5"]) == "172.22.0.9"
    assert client_peer(config, "172.22.0.6", ["192.0.2.5, 192.0.2.6"]) == "172.22.0.6"
    assert client_peer(config, "172.22.0.6", ["192.0.2.5", "192.0.2.6"]) == "172.22.0.6"
    loopback = Settings(auth_trusted_proxy_ip="127.0.0.1")
    assert client_peer(loopback, "127.0.0.1", ["192.0.2.5"]) == "127.0.0.1"
