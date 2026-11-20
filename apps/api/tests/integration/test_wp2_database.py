"""Verify provisioning, readiness, and transactional audit against disposable PostgreSQL."""

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from aq_uai_api.core.config import get_settings
from aq_uai_api.db import session as sessions
from aq_uai_api.db.audit import ActiveChange, AuditAction, write_audit_event
from aq_uai_api.db.identity import Institution, Unit, User
from aq_uai_api.db.provision import DatabaseRoles, apply_runtime_privileges, prepare_database
from aq_uai_api.db.schema import REQUIRED_SCHEMA_REVISION
from aq_uai_api.main import create_app

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("AQ_UAI_RUN_DB_TESTS") != "1" or get_settings().environment != "test",
        reason="Requires AQ_UAI_RUN_DB_TESTS=1 and an explicitly disposable test environment",
    ),
]
CONFIG = Path(__file__).resolve().parents[2] / "alembic.ini"
MIGRATION_PASSWORD = "wp2-disposable-migration-only"
RUNTIME_PASSWORD = "wp2-disposable-runtime-only"
UNAVAILABLE = {"detail": {"code": "DATABASE_UNAVAILABLE", "message": "Database is not ready"}}


def connect(url, *, autocommit=False):
    return psycopg.connect(
        host=url.host or "",
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
        autocommit=autocommit,
        connect_timeout=3,
    )


def alembic(url, *args):
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(CONFIG), *args],
        env={
            **os.environ,
            "AQ_UAI_DB_HOST": url.host or "",
            "AQ_UAI_DB_PORT": str(url.port),
            "AQ_UAI_DB_NAME": url.database,
            "AQ_UAI_DB_USER": url.username,
            "AQ_UAI_DB_PASSWORD": url.password or "",
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


@contextmanager
def api_client(url):
    engine = sa.create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 2})
    app = create_app()

    def get_session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[sessions.get_session] = get_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        engine.dispose()


@contextmanager
def disposable_database():
    bootstrap = get_settings().database_url
    suffix = uuid4().hex[:16]
    database = f"aq_wp2_{suffix}"
    roles = DatabaseRoles(f"aq_wp2_schema_{suffix}", f"aq_wp2_runtime_{suffix}")
    with connect(bootstrap, autocommit=True) as admin:
        # All identifiers here come from the generated hexadecimal suffix.
        admin.execute(f'CREATE DATABASE "{database}"')
        try:
            yield (
                bootstrap.set(database=database),
                roles,
                bootstrap.set(
                    database=database, username=roles.migration, password=MIGRATION_PASSWORD
                ),
                bootstrap.set(database=database, username=roles.runtime, password=RUNTIME_PASSWORD),
            )
        finally:
            admin.execute(f'DROP DATABASE "{database}"')
            admin.execute(f'DROP ROLE IF EXISTS "{roles.runtime}", "{roles.migration}"')


def prepare(admin, roles):
    with connect(admin) as connection:
        prepare_database(connection, roles, MIGRATION_PASSWORD, RUNTIME_PASSWORD)


def migrate(owner, roles):
    alembic(owner, "upgrade", "head")
    with connect(owner) as connection:
        apply_runtime_privileges(connection, roles)


def assert_denied(connection, statement):
    with pytest.raises(psycopg.errors.InsufficientPrivilege), connection.transaction():
        connection.execute(statement)


@pytest.mark.parametrize("prior", [None, "0001_phase1_metadata", "0002_identity_foundation"])
def test_provisioning_is_repeatable_and_preserves_data(prior):
    assert (
        ScriptDirectory.from_config(Config(str(CONFIG))).get_current_head()
        == REQUIRED_SCHEMA_REVISION
    )
    with disposable_database() as (admin, roles, owner, runtime):
        identity_id = uuid4()
        if prior:
            alembic(admin, "upgrade", prior)
            with connect(admin) as connection:
                connection.execute(
                    "INSERT INTO public.app_metadata VALUES ('wp2_extra', 'preserved')"
                )
                connection.execute("GRANT ALL ON TABLE public.app_metadata TO PUBLIC")
                if prior == "0002_identity_foundation":
                    connection.execute(
                        "GRANT SELECT (password_hash) ON public.user_credentials TO PUBLIC"
                    )
                    connection.execute("GRANT UPDATE (action) ON public.audit_events TO PUBLIC")
                    connection.execute(
                        "CREATE PROCEDURE public.wp2_legacy_proc() LANGUAGE sql AS 'SELECT 1'"
                    )
                    connection.execute(
                        "INSERT INTO public.institutions (id, code, name) VALUES (%s, 'OFFICE', 'Office')",
                        (identity_id,),
                    )

        prepare(admin, roles)
        with api_client(runtime) as client:
            previous = client.get("/api/v1/ready")
            assert previous.status_code == (200 if prior == REQUIRED_SCHEMA_REVISION else 503)
            if previous.status_code == 503:
                assert previous.json() == UNAVAILABLE
        migrate(owner, roles)
        prepare(admin, roles)
        migrate(owner, roles)
        alembic(owner, "check")

        with connect(owner) as connection:
            assert connection.execute(
                "SELECT current_user, rolsuper FROM pg_roles WHERE rolname = current_user"
            ).fetchone() == (roles.migration, False)
            connection.execute("CREATE TABLE public.wp2_acl_probe (id int PRIMARY KEY)")
            connection.execute(
                "CREATE FUNCTION public.wp2_private() RETURNS int LANGUAGE sql AS 'SELECT 1'"
            )
        with connect(runtime, autocommit=True) as connection:
            assert_denied(connection, "SELECT * FROM wp2_acl_probe")
            assert_denied(connection, "SELECT wp2_private()")
        prepare(admin, roles)

        with api_client(runtime) as client:
            assert client.get("/api/v1/ready").json() == {
                "status": "ready",
                "database": "connected",
            }
            assert client.get("/api/v1/system/info").json() == {
                "name": "AQ EduUAI",
                "milestone": "phase-1-foundation",
                "source": "postgresql",
            }

        for login in (
            runtime.set(password=MIGRATION_PASSWORD),
            owner.set(password=RUNTIME_PASSWORD),
        ):
            with pytest.raises(psycopg.OperationalError):
                connect(login)
        with connect(runtime, autocommit=True) as connection:
            assert connection.execute("SELECT current_user").fetchone() == (roles.runtime,)
            assert (
                connection.execute(
                    "SELECT rolsuper, rolcreatedb, rolcreaterole, rolinherit, rolreplication, rolbypassrls "
                    "FROM pg_roles WHERE rolname = current_user"
                ).fetchone()
                == (False,) * 6
            )
            assert connection.execute(
                "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()"
            ).fetchone() == (admin.username,)
            assert connection.execute(
                "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'public'"
            ).fetchone() == (roles.migration,)
            assert connection.execute(
                "SELECT DISTINCT pg_get_userbyid(c.relowner) FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'i')"
            ).fetchall() == [(roles.migration,)]
            if prior:
                assert connection.execute(
                    "SELECT value FROM app_metadata WHERE key = 'wp2_extra'"
                ).fetchone() == ("preserved",)
            if prior == "0002_identity_foundation":
                assert connection.execute(
                    "SELECT name FROM institutions WHERE id = %s", (identity_id,)
                ).fetchone() == ("Office",)
                assert_denied(connection, "CALL public.wp2_legacy_proc()")

            for statement in (
                f'SET ROLE "{roles.migration}"',
                f'SET ROLE "{admin.username}"',
                "SET ROLE pg_database_owner",
                "CREATE TABLE public.wp2_forbidden (id int)",
                "CREATE TEMP TABLE wp2_forbidden (id int)",
                "CREATE SCHEMA wp2_forbidden",
                "CREATE ROLE wp2_forbidden",
                "ALTER TABLE audit_events ADD COLUMN forbidden int",
                "ALTER TABLE audit_events OWNER TO CURRENT_USER",
                "UPDATE roles SET code = code",
                "DELETE FROM permissions",
                "TRUNCATE role_permissions",
                "UPDATE app_metadata SET value = value",
                "UPDATE alembic_version SET version_num = version_num",
                "UPDATE institutions SET name = name",
                "UPDATE user_credentials SET user_id = user_id",
                "DELETE FROM user_credentials",
                "UPDATE auth_sessions SET expires_at = expires_at",
                "DELETE FROM auth_sessions",
                "UPDATE auth_throttle_buckets SET key_digest = key_digest",
                "SELECT * FROM wp2_acl_probe",
                "SELECT wp2_private()",
                "UPDATE audit_events SET action = action",
                "DELETE FROM audit_events",
                "TRUNCATE audit_events",
            ):
                assert_denied(connection, statement)

        with connect(runtime) as connection:
            connection.execute(
                "INSERT INTO audit_events (action, target_type, outcome, request_id) "
                "VALUES ('wp2.test', 'login', 'FAILURE', 'wp2-test')"
            )
            assert connection.execute("SELECT actor_id FROM audit_events").fetchall() == [(None,)]


def test_incompatible_and_unreachable_schema_preserve_diagnostic_body():
    with disposable_database() as (admin, roles, owner, runtime):
        prepare(admin, roles)
        migrate(owner, roles)
        with connect(owner) as connection:
            connection.execute("UPDATE alembic_version SET version_num = 'incompatible'")
        with api_client(runtime) as client:
            response = client.get("/api/v1/ready")
            assert response.status_code == 503 and response.json() == UNAVAILABLE
            assert response.headers["X-Request-ID"]
        with api_client(runtime.set(database="wp2_database_does_not_exist")) as client:
            response = client.get("/api/v1/ready")
            assert response.status_code == 503 and response.json() == UNAVAILABLE
            assert client.get("/api/v1/health").status_code == 200


def test_explicit_service_transaction_commits_or_rolls_back_audit(monkeypatch):
    with disposable_database() as (admin, roles, owner, runtime):
        prepare(admin, roles)
        migrate(owner, roles)
        # Real schema owner simulates a later package with an authorized business write.
        # The test never broadens the runtime grants to make this example pass.
        engine = sa.create_engine(owner, hide_parameters=True)
        try:
            factory = sessionmaker(bind=engine, autoflush=False)
            monkeypatch.setattr(sessions, "get_session_factory", lambda: factory)
            institution, unit, actor = uuid4(), uuid4(), uuid4()
            actor_fields = {
                "institution_id": institution,
                "actor_id": actor,
                "target_id": unit,
                "action": AuditAction.UNIT_STATE_CHANGED,
            }
            with sessions.write_transaction() as db:
                db.add(Institution(id=institution, code="WP2", name="WP2 test"))
                db.flush()
                db.add(Unit(id=unit, institution_id=institution, code="MAIN", name="Main"))
                db.flush()
                db.add(
                    User(
                        id=actor,
                        institution_id=institution,
                        primary_unit_id=unit,
                        username="wp2-test",
                        display_name="WP2 Test",
                        code_type="STAFF",
                        institutional_code="1",
                    )
                )

            request_id = uuid4()
            with sessions.write_transaction() as db:
                db.get(Unit, unit).active = False
                write_audit_event(
                    db,
                    request_id=request_id,
                    changes=ActiveChange(before=True, after=False),
                    **actor_fields,
                )

            with connect(runtime) as connection:
                assert connection.execute("SELECT active FROM units").fetchone() == (False,)
                assert connection.execute(
                    "SELECT request_id, outcome, actor_id, changes, occurred_at FROM audit_events"
                ).fetchone()[:4] == (
                    str(request_id),
                    "SUCCESS",
                    actor,
                    {"before": True, "after": False},
                )

            with pytest.raises(sa.exc.IntegrityError), sessions.write_transaction() as db:
                db.get(Unit, unit).active = True
                db.flush()
                write_audit_event(
                    db,
                    request_id=uuid4(),
                    changes=ActiveChange(before=False, after=True),
                    **(actor_fields | {"actor_id": uuid4()}),
                )

            with pytest.raises(sa.exc.IntegrityError), sessions.write_transaction() as db:
                write_audit_event(
                    db,
                    request_id=uuid4(),
                    changes=ActiveChange(before=False, after=True),
                    **actor_fields,
                )
                db.flush()
                db.add(Institution(code="WP2", name="Duplicate"))

            reader = sessions.get_session()
            db = next(reader)
            db.get(Unit, unit).active = True
            db.flush()
            reader.close()

            with connect(runtime) as connection:
                assert connection.execute("SELECT active FROM units").fetchone() == (False,)
                assert connection.execute("SELECT count(*) FROM audit_events").fetchone() == (1,)

            runtime_engine = sa.create_engine(runtime, hide_parameters=True)
            try:
                monkeypatch.setattr(
                    sessions, "get_session_factory", lambda: sessionmaker(bind=runtime_engine)
                )
                rejected_id = uuid4()
                with sessions.write_transaction() as db:
                    write_audit_event(
                        db, action=AuditAction.AUTH_LOGIN_REJECTED, request_id=rejected_id
                    )
                with connect(runtime) as connection:
                    assert connection.execute(
                        "SELECT actor_id, outcome, changes FROM audit_events WHERE request_id = %s",
                        (str(rejected_id),),
                    ).fetchone() == (None, "FAILURE", {})
            finally:
                runtime_engine.dispose()
        finally:
            engine.dispose()
