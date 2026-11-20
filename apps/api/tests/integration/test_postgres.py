"""Opt-in test against the explicitly configured development/test PostgreSQL instance."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text

from aq_uai_api.db.models import AppMetadata
from aq_uai_api.db.session import get_engine
from aq_uai_api.main import app

pytestmark = pytest.mark.postgres


@pytest.mark.skipif(
    os.getenv("AQ_UAI_RUN_DB_TESTS") != "1",
    reason="Set AQ_UAI_RUN_DB_TESTS=1 only against a disposable local/CI database",
)
def test_database_migrated_and_http_reads_real_postgres() -> None:
    engine = get_engine()
    with engine.connect() as connection:
        assert "app_metadata" in inspect(connection).get_table_names()
        assert connection.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar_one() == 1
        assert connection.execute(
            select(AppMetadata.value).where(AppMetadata.key == "milestone")
        ).scalar_one() == "phase-1-foundation"
    with TestClient(app) as client:
        assert client.get("/api/v1/ready").status_code == 200
        response = client.get("/api/v1/system/info")
    assert response.status_code == 200
    assert response.json()["source"] == "postgresql"
