"""Q6 (4.2): Populated 0006 -> 0008 upgrade rehearsal & idempotency check (R18).

Upgrades a fresh disposable PostgreSQL 18 database to ``0006_mdl_routing_and_styles`` only,
seeds realistic pre-QTA institutional data (institution, units, users in ACTIVE/PENDING/
DISABLED states, SYSTEM/AI_SPECIALIST/AUTHORIZATION groups and memberships, MDL provider/
models/routing, audit rows, app_metadata), provisions roles, upgrades to head (``0008``),
and verifies:
- every pre-existing row is preserved byte-identically;
- ``alembic check`` reports zero pending operations;
- all 8 ``qta_*`` tables exist and are empty before sync (FR-QTA-001 AC2);
- QTA permissions/roles from 0007 exist and no existing user received a QTA role implicitly;
- ``aq_uai_runtime`` holds exact ``QTA_RUNTIME_PRIVILEGES`` (no DELETE anywhere, INSERT-only
  on history tables);
- re-running provision + upgrade is idempotent with zero data change;
- post-upgrade API sync, group quota configuration, additive lookup, and live ``allocated``
  calculation work end-to-end through the real FastAPI app.
"""

import re
from contextlib import contextmanager
from uuid import uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy.orm import Session, sessionmaker

from aq_uai_api.api.v1 import auth as auth_api
from aq_uai_api.auth import service as auth_service
from aq_uai_api.auth.security import hash_password
from aq_uai_api.authorization import writes as auth_writes
from aq_uai_api.core.config import Settings, get_settings
from aq_uai_api.db import session as db_session
from aq_uai_api.db.provision import QTA_RUNTIME_PRIVILEGES
from aq_uai_api.db.schema import REQUIRED_SCHEMA_REVISION
from aq_uai_api.main import create_app
from aq_uai_api.qta import models as _qta_models  # noqa: F401

from .test_q2_qta_groups import qta_get, qta_send
from .test_wp2_database import (
    alembic,
    assert_denied,
    connect,
    disposable_database,
    migrate,
    prepare,
)
from .test_wp2_database import pytestmark as postgres_marks
from .test_wp3_auth import ORIGIN, ORIGIN_HEADER
from .test_wp5_directory import add_grant

pytestmark = postgres_marks

PRE_QTA_TABLES = (
    "app_metadata",
    "institutions",
    "units",
    "users",
    "user_credentials",
    "account_groups",
    "group_memberships",
    "user_role_assignments",
    "mdl_providers",
    "mdl_models",
    "mdl_routing",
    "audit_events",
)
QTA_INSERT_ONLY_TABLES = frozenset(
    {
        "qta_budget_revisions",
        "qta_group_sync_runs",
        "qta_suspensions",
        "qta_suspension_restorations",
        "qta_monthly_resets",
        "qta_events",
    }
)
_CLAUSE = re.compile(r"\s*([A-Z]+)\s*(?:\(([^)]*)\))?\s*(?:,|$)")
ADMIN_PASSWORD = "q6-upgrade-admin-password-2026"
QTA_ADMIN_PASSWORD = "q6-upgrade-quota-password-2026"


def _expected_column_grants(privilege_spec: str) -> dict[str, set[str]]:
    grants: dict[str, set[str]] = {"INSERT": set(), "UPDATE": set()}
    for match in _CLAUSE.finditer(privilege_spec):
        verb, cols = match.group(1), match.group(2)
        if verb in grants and cols:
            grants[verb] = {c.strip() for c in cols.split(",") if c.strip()}
    return grants


def _dump_tables(url, tables) -> dict[str, list]:
    with connect(url) as conn:
        result: dict[str, list] = {}
        for table in tables:
            rows = conn.execute(
                sql.SQL("SELECT to_jsonb(t) FROM {} AS t ORDER BY to_jsonb(t)").format(
                    sql.Identifier(table)
                )
            ).fetchall()
            result[table] = [row[0] for row in rows]
        return result


@contextmanager
def _mounted_runtime_app(runtime_url, monkeypatch):
    """Mount the real FastAPI app against ``runtime_url`` under the restricted runtime role."""
    engine = sa.create_engine(runtime_url, hide_parameters=True, connect_args={"connect_timeout": 3})
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(db_session, "write_transaction", factory.begin)
    monkeypatch.setattr(auth_service, "write_transaction", factory.begin)
    monkeypatch.setattr(auth_writes, "write_transaction", factory.begin)
    settings = Settings(
        environment="test",
        auth_origin=ORIGIN,
        auth_allow_http_local=True,
        auth_throttle_key="a5" * 32,
        db_host=runtime_url.host or "",
        db_port=runtime_url.port,
        db_name=runtime_url.database,
        db_user=runtime_url.username,
        db_password=runtime_url.password or "",
    )
    monkeypatch.setattr(auth_api, "get_settings", lambda: settings)
    app = create_app()

    def get_test_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[db_session.get_session] = get_test_session
    app.dependency_overrides[get_settings] = lambda: settings

    class _Box:
        pass

    box = _Box()
    box.app = app
    box.settings = settings
    try:
        yield box
    finally:
        engine.dispose()


def _sign_in_with_password(box, username: str, password: str) -> TestClient:
    browser = TestClient(box.app, base_url=ORIGIN)
    browser.__enter__()
    response = browser.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers=ORIGIN_HEADER,
    )
    assert response.status_code == 204, response.text
    me = browser.get("/api/v1/auth/me")
    assert me.status_code == 200
    browser.csrf = me.json()["csrf_token"]
    return browser


def test_populated_0006_upgrades_to_0008_preserves_data_and_enables_qta(monkeypatch):
    """R18 / FR-QTA-001 AC2: populated 0006 -> 0008 upgrade, idempotent re-run & live QTA API."""
    with disposable_database() as (admin, roles, owner, runtime):
        # 1. Bring fresh DB to 0006_mdl_routing_and_styles only.
        alembic(admin, "upgrade", "0006_mdl_routing_and_styles")

        # 2. Seed realistic pre-QTA institutional data via SQL.
        inst_id = uuid4()
        unit_main, unit_cs = uuid4(), uuid4()
        admin_id, qta_mgr_id, member_active_id, member_pending_id, member_disabled_id = (
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
        )
        g_sys_id, g_spec_id, g_auth_id = uuid4(), uuid4(), uuid4()
        prov_id, m1_id, m2_id = uuid4(), uuid4(), uuid4()

        with connect(admin) as conn:
            conn.execute("INSERT INTO app_metadata (key, value) VALUES ('q6_pre_upgrade', 'preserved')")
            conn.execute(
                "INSERT INTO institutions (id, code, name) VALUES (%s, 'U_Q6', 'Trường Q6')",
                (inst_id,),
            )
            conn.execute(
                "INSERT INTO units (id, institution_id, code, name) VALUES"
                " (%s, %s, 'MAIN', 'Khối chính'), (%s, %s, 'CS', 'Khoa CNTT')",
                (unit_main, inst_id, unit_cs, inst_id),
            )
            conn.execute(
                "INSERT INTO users (id, institution_id, primary_unit_id, username, display_name,"
                " code_type, institutional_code, state) VALUES"
                " (%s, %s, %s, 'q6admin', 'Quản trị nền', 'STAFF', 'ADM-01', 'ACTIVE'),"
                " (%s, %s, %s, 'q6quota', 'Người phụ trách QTA', 'STAFF', 'QTA-01', 'ACTIVE'),"
                " (%s, %s, %s, 'q6active', 'Giảng viên Hoạt động', 'STAFF', 'GV-01', 'ACTIVE'),"
                " (%s, %s, %s, 'q6pending', 'Sinh viên Chờ', 'STUDENT', 'SV-01', 'PENDING'),"
                " (%s, %s, %s, 'q6disabled', 'Tài khoản Khóa', 'STUDENT', 'SV-02', 'DISABLED')",
                (
                    admin_id, inst_id, unit_main,
                    qta_mgr_id, inst_id, unit_main,
                    member_active_id, inst_id, unit_cs,
                    member_pending_id, inst_id, unit_cs,
                    member_disabled_id, inst_id, unit_cs,
                ),
            )
            conn.execute(
                "INSERT INTO user_credentials (user_id, password_hash, must_change_password) VALUES"
                " (%s, %s, false), (%s, %s, false)",
                (admin_id, hash_password(ADMIN_PASSWORD), qta_mgr_id, hash_password(QTA_ADMIN_PASSWORD)),
            )
            conn.execute(
                "INSERT INTO user_role_assignments (id, institution_id, user_id, role_code, scope, unit_id)"
                " VALUES (%s, %s, %s, 'FOUNDATION_ADMIN', 'GLOBAL', NULL)",
                (uuid4(), inst_id, admin_id),
            )
            conn.execute(
                "INSERT INTO account_groups (id, institution_id, code, name, kind, active) VALUES"
                " (%s, %s, 'G_GV_PRE', 'Nhóm Giảng viên 0006', 'SYSTEM', true),"
                " (%s, %s, 'AI_LAB_PRE', 'Nhóm Chuyên biệt 0006', 'AI_SPECIALIST', true),"
                " (%s, %s, 'AUTH_PRE', 'Nhóm Phân quyền 0006', 'AUTHORIZATION', true)",
                (g_sys_id, inst_id, g_spec_id, inst_id, g_auth_id, inst_id),
            )
            conn.execute(
                "INSERT INTO group_memberships (institution_id, group_id, user_id, active) VALUES"
                " (%s, %s, %s, true), (%s, %s, %s, true), (%s, %s, %s, true), (%s, %s, %s, true)",
                (
                    inst_id, g_sys_id, member_active_id,
                    inst_id, g_spec_id, member_active_id,
                    inst_id, g_sys_id, member_pending_id,
                    inst_id, g_sys_id, member_disabled_id,
                ),
            )
            conn.execute(
                "INSERT INTO mdl_providers (id, institution_id, name, provider_type, api_style,"
                " endpoint, auth_scheme) VALUES"
                " (%s, %s, 'Internal Pre-QTA', 'INTERNAL', 'OPENAI_COMPATIBLE', 'https://local.test/v1', 'NONE')",
                (prov_id, inst_id),
            )
            conn.execute(
                "INSERT INTO mdl_models (id, institution_id, provider_id, technical_id, display_name,"
                " supports_text, risk_level, active) VALUES"
                " (%s, %s, %s, 'pre-m1', 'Mô hình Pre-1', true, 'LOW', true),"
                " (%s, %s, %s, 'pre-m2', 'Mô hình Pre-2', true, 'LOW', true)",
                (m1_id, inst_id, prov_id, m2_id, inst_id, prov_id),
            )
            conn.execute(
                "INSERT INTO mdl_routing (institution_id, primary_model_id, fallback_model_id, revision, updated_by)"
                " VALUES (%s, %s, %s, 1, %s)",
                (inst_id, m1_id, m2_id, admin_id),
            )
            conn.execute(
                "INSERT INTO audit_events (id, request_id, institution_id, actor_id, action,"
                " outcome, target_type, target_id, changes) VALUES"
                " (%s, %s, %s, %s, 'unit.created', 'SUCCESS', 'UNIT', %s, '{\"code\":\"CS\",\"name\":\"Khoa CNTT\"}'::jsonb)",
                (uuid4(), uuid4(), inst_id, admin_id, unit_cs),
            )

        before_dump = _dump_tables(admin, PRE_QTA_TABLES)

        # 3. Provision and upgrade 0006 -> 0008 (head), then verify alembic check.
        prepare(admin, roles)
        migrate(owner, roles)
        alembic(owner, "check")

        # 4. Assert every pre-existing row is preserved byte-identically.
        assert _dump_tables(owner, PRE_QTA_TABLES) == before_dump

        with connect(owner) as conn:
            assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == (
                REQUIRED_SCHEMA_REVISION,
            )
            # All 8 qta_* tables exist and are EMPTY before sync (FR-QTA-001 AC2).
            for table_name in QTA_RUNTIME_PRIVILEGES:
                assert conn.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table_name))
                ).fetchone() == (0,), table_name

            # 0007 QTA permissions & roles exist; zero users/groups received a QTA role implicitly.
            qta_perms = {
                row[0]
                for row in conn.execute(
                    "SELECT code FROM permissions WHERE code LIKE 'qta.%'"
                ).fetchall()
            }
            assert qta_perms == {"qta.read", "qta.manage"}
            qta_roles = {
                row[0]
                for row in conn.execute(
                    "SELECT code FROM roles WHERE code IN ('AI_QUOTA_ADMIN', 'AI_QUOTA_VIEWER')"
                ).fetchall()
            }
            assert qta_roles == {"AI_QUOTA_ADMIN", "AI_QUOTA_VIEWER"}
            assert conn.execute(
                "SELECT count(*) FROM user_role_assignments WHERE role_code IN ('AI_QUOTA_ADMIN', 'AI_QUOTA_VIEWER')"
            ).fetchone() == (0,)
            assert conn.execute(
                "SELECT count(*) FROM group_role_assignments WHERE role_code IN ('AI_QUOTA_ADMIN', 'AI_QUOTA_VIEWER')"
            ).fetchone() == (0,)

        # 5. Assert aq_uai_runtime holds EXACTLY QTA_RUNTIME_PRIVILEGES (no DELETE, INSERT-only history).
        with connect(runtime, autocommit=True) as rconn:
            for table_name, spec in QTA_RUNTIME_PRIVILEGES.items():
                expected = _expected_column_grants(spec)
                for priv, should_have in (
                    ("SELECT", True),
                    ("INSERT", False),
                    ("UPDATE", False),
                    ("DELETE", False),
                    ("TRUNCATE", False),
                    ("REFERENCES", False),
                    ("TRIGGER", False),
                ):
                    assert rconn.execute(
                        "SELECT has_table_privilege(current_user, %s, %s)",
                        (f"public.{table_name}", priv),
                    ).fetchone() == (should_have,), (table_name, priv)

                columns = [
                    col
                    for (col,) in rconn.execute(
                        "SELECT column_name FROM information_schema.columns"
                        " WHERE table_schema = 'public' AND table_name = %s",
                        (table_name,),
                    ).fetchall()
                ]
                assert columns
                for col in columns:
                    assert rconn.execute(
                        "SELECT has_column_privilege(current_user, %s, %s, 'INSERT')",
                        (f"public.{table_name}", col),
                    ).fetchone() == (col in expected["INSERT"],), (table_name, col, "INSERT")
                    assert rconn.execute(
                        "SELECT has_column_privilege(current_user, %s, %s, 'UPDATE')",
                        (f"public.{table_name}", col),
                    ).fetchone() == (col in expected["UPDATE"],), (table_name, col, "UPDATE")

                if table_name in QTA_INSERT_ONLY_TABLES:
                    assert expected["UPDATE"] == set()
                assert_denied(rconn, f"DELETE FROM {table_name}")

        # 6. Idempotent second upgrade run: zero errors, zero data change.
        prepare(admin, roles)
        migrate(owner, roles)
        alembic(owner, "check")
        assert _dump_tables(owner, PRE_QTA_TABLES) == before_dump
        with connect(owner) as conn:
            for table_name in QTA_RUNTIME_PRIVILEGES:
                assert conn.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table_name))
                ).fetchone() == (0,)

        # 7. End-to-end API exercise on the upgraded database: grant QTA role, sync, quotas, lookup & allocated.
        with _mounted_runtime_app(runtime, monkeypatch) as box:
            foundation_admin = _sign_in_with_password(box, "q6admin", ADMIN_PASSWORD)
            qta_admin = _sign_in_with_password(box, "q6quota", QTA_ADMIN_PASSWORD)
            try:
                add_grant(foundation_admin, f"/users/{qta_mgr_id}", "AI_QUOTA_ADMIN")
                # Refresh qta_admin session/CSRF after grant (session already valid; re-read /me).
                assert qta_get(qta_admin, "/groups")["total"] == 0  # empty before sync!

                sync_run = qta_send(qta_admin, "POST", "/groups/sync")
                assert sync_run["system_group_count"] == 1
                assert sync_run["specialist_group_count"] == 1
                assert sync_run["groups_added"] == 2  # G_GV_PRE (SYNC) + AI_LAB_PRE (SPECIALIST); AUTH_PRE excluded

                qta_send(
                    qta_admin,
                    "PUT",
                    f"/groups/{g_sys_id}/quotas",
                    {"quotas": [{"model_id": str(m1_id), "enabled": True, "monthly_limit": 1000}]},
                )
                qta_send(
                    qta_admin,
                    "PUT",
                    f"/groups/{g_spec_id}/quotas",
                    {"quotas": [{"model_id": str(m1_id), "enabled": True, "monthly_limit": 3000}]},
                )

                ent = qta_get(qta_admin, f"/users/{member_active_id}/entitlements")
                by_mid = {m["model_id"]: m for m in ent["models"]}
                assert by_mid[str(m1_id)]["base_entitlement"] == 4000
                assert ent["base_entitlement_total"] == 4000

                # Institutional allocated counts ONLY ACTIVE user (4,000); PENDING & DISABLED contribute 0.
                budget = qta_get(qta_admin, "/budgets")
                assert budget["allocated"] == 4000
                assert budget["status"] == "NOT_RECORDED"
            finally:
                qta_admin.__exit__(None, None, None)
                foundation_admin.__exit__(None, None, None)
