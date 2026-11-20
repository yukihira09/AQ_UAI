"""Exercise real Alembic upgrades and database constraints on disposable PostgreSQL."""

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.runtime.migration import MigrationContext
from sqlalchemy.exc import IntegrityError

from aq_uai_api.core.config import get_settings

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("AQ_UAI_RUN_DB_TESTS") != "1",
        reason="Set AQ_UAI_RUN_DB_TESTS=1 with a disposable PostgreSQL server",
    ),
]

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
PHASE1 = "0001_phase1_metadata"
WP1 = "0002_identity_foundation"
CATALOG = {
    "FOUNDATION_ADMIN": {
        "directory.read",
        "directory.profile.update",
        "directory.manage",
        "authorization.manage",
        "audit.read",
    },
    "DIRECTORY_READER": {"directory.read"},
    "UNIT_DIRECTORY_MANAGER": {"directory.read", "directory.profile.update"},
}


@pytest.fixture(scope="module")
def disposable_database():
    url = get_settings().database_url
    admin = sa.create_engine(url, isolation_level="AUTOCOMMIT")

    def create():
        # The name is generated here. Only this database is created and dropped.
        name = f"aq_wp1_{uuid4().hex}"
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
        engine = sa.create_engine(url.set(database=name), hide_parameters=True)
        databases.append((name, engine))
        return engine

    databases = []
    try:
        yield create
    finally:
        for name, engine in databases:
            engine.dispose()
            with admin.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        admin.dispose()


def alembic(engine, *arguments):
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *arguments],
        env={**os.environ, "AQ_UAI_DB_NAME": engine.url.database},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope="module")
def clean_head(disposable_database):
    engine = disposable_database()
    alembic(engine, "upgrade", "head")
    return engine


def current_revision(connection):
    return MigrationContext.configure(connection).get_current_revision()


def test_clean_database_reaches_wp1_and_matches_orm(clean_head):
    with clean_head.connect() as connection:
        assert current_revision(connection) == WP1
    alembic(clean_head, "check")


def test_populated_phase1_upgrade_preserves_all_metadata(disposable_database):
    engine = disposable_database()
    alembic(engine, "upgrade", PHASE1)
    with engine.begin() as connection:
        assert current_revision(connection) == PHASE1
        connection.execute(sa.text("INSERT INTO app_metadata VALUES ('custom', 'keep this row')"))
        before = dict(connection.execute(sa.text("SELECT key, value FROM app_metadata")).all())

    alembic(engine, "upgrade", "head")
    with engine.connect() as connection:
        assert current_revision(connection) == WP1
        role_ids = connection.execute(sa.text("SELECT id FROM roles ORDER BY code")).all()

    alembic(engine, "upgrade", "head")
    with engine.connect() as connection:
        assert current_revision(connection) == WP1
        assert (
            dict(connection.execute(sa.text("SELECT key, value FROM app_metadata")).all()) == before
        )
        assert connection.execute(sa.text("SELECT id FROM roles ORDER BY code")).all() == role_ids


def test_catalog_is_seeded_without_accounts_or_institutions(clean_head):
    with clean_head.connect() as connection:
        entries = connection.execute(
            sa.text("SELECT role_code, permission_code FROM role_permissions")
        )
        actual = {}
        for role, permission in entries:
            actual.setdefault(role, set()).add(permission)
        assert actual == CATALOG
        assert set(connection.scalars(sa.text("SELECT code FROM roles"))) == set(CATALOG)
        assert set(connection.scalars(sa.text("SELECT code FROM permissions"))) == set.union(
            *CATALOG.values()
        )
        for name in (
            "institutions",
            "units",
            "users",
            "user_credentials",
            "account_groups",
            "group_memberships",
            "user_role_assignments",
            "group_role_assignments",
            "auth_sessions",
            "auth_throttle_buckets",
            "audit_events",
        ):
            table = sa.Table(name, sa.MetaData(), autoload_with=connection)
            assert connection.scalar(sa.select(sa.func.count()).select_from(table)) == 0


@pytest.fixture(scope="module")
def tables(clean_head):
    metadata = sa.MetaData()
    metadata.reflect(bind=clean_head)
    return metadata.tables


@pytest.fixture
def sample(clean_head, tables):
    with clean_head.connect() as connection, connection.begin() as transaction:

        def insert(table, **values):
            connection.execute(tables[table].insert().values(**values))

        ids = {
            key: uuid4()
            for key in ("a", "b", "unit_a", "unit_b", "user", "user_b", "group", "group_b")
        }
        for suffix in ("a", "b"):
            insert("institutions", id=ids[suffix], code=suffix, name=suffix)
            insert(
                "units",
                id=ids[f"unit_{suffix}"],
                institution_id=ids[suffix],
                code="main",
                name="Main",
            )
        insert(
            "users",
            id=ids["user"],
            institution_id=ids["a"],
            primary_unit_id=ids["unit_a"],
            username="ada",
            display_name="Ada",
            code_type="STAFF",
            institutional_code="001",
            state="DISABLED",
        )
        insert(
            "account_groups",
            id=ids["group"],
            institution_id=ids["a"],
            code="auth",
            name="Authorization group",
            kind="AUTHORIZATION",
        )
        insert(
            "users",
            id=ids["user_b"],
            institution_id=ids["b"],
            primary_unit_id=ids["unit_b"],
            username="linh",
            display_name="Linh",
            code_type="STAFF",
            institutional_code="001",
        )
        insert(
            "account_groups",
            id=ids["group_b"],
            institution_id=ids["b"],
            code="auth",
            name="Other authorization group",
            kind="AUTHORIZATION",
        )
        yield connection, ids
        transaction.rollback()


@pytest.mark.parametrize(
    ("table_name", "values", "sqlstate"),
    [
        ("users", {"username": "Ada"}, "23514"),
        ("users", {"username": " ada "}, "23514"),
        ("users", {"username": "ada"}, "23505"),
        ("users", {"username": "ada", "institution_id": "b", "primary_unit_id": "unit_b"}, "23505"),
        ("users", {"institutional_code": "001"}, "23505"),
        ("users", {"primary_unit_id": "unit_b"}, "23503"),
        ("group_memberships", {"user_id": "user_b"}, "23503"),
        ("group_memberships", {"group_id": "group_b"}, "23503"),
        ("user_role_assignments", {"institution_id": "b", "unit_id": "unit_b"}, "23503"),
        ("user_role_assignments", {"unit_id": "unit_b"}, "23503"),
        ("group_role_assignments", {"institution_id": "b", "unit_id": "unit_b"}, "23503"),
        ("group_role_assignments", {"unit_id": "unit_b"}, "23503"),
        ("user_role_assignments", {"scope": "GLOBAL"}, "23514"),
        ("user_role_assignments", {"unit_id": None}, "23514"),
        ("user_role_assignments", {"role_code": "FOUNDATION_ADMIN"}, "23514"),
        (
            "group_role_assignments",
            {"role_code": "FOUNDATION_ADMIN", "scope": "GLOBAL", "unit_id": None},
            "23514",
        ),
        ("audit_events", {"institution_id": "b"}, "23503"),
        ("audit_events", {"institution_id": None}, "23514"),
    ],
)
def test_invalid_relationship_or_identity_is_rejected(sample, tables, table_name, values, sqlstate):
    connection, ids = sample
    defaults = {
        "users": dict(
            institution_id=ids["a"],
            primary_unit_id=ids["unit_a"],
            username="grace",
            institutional_code="002",
            display_name="Grace",
            code_type="STAFF",
        ),
        "group_memberships": dict(
            institution_id=ids["a"], user_id=ids["user"], group_id=ids["group"]
        ),
        "user_role_assignments": dict(
            institution_id=ids["a"],
            user_id=ids["user"],
            role_code="DIRECTORY_READER",
            scope="UNIT",
            unit_id=ids["unit_a"],
        ),
        "group_role_assignments": dict(
            institution_id=ids["a"],
            group_id=ids["group"],
            role_code="DIRECTORY_READER",
            scope="UNIT",
            unit_id=ids["unit_a"],
        ),
        "audit_events": dict(
            institution_id=ids["a"],
            actor_id=ids["user"],
            action="test",
            target_type="user",
            outcome="SUCCESS",
            request_id="test-request",
        ),
    }
    row = defaults[table_name] | {key: ids.get(value, value) for key, value in values.items()}
    with pytest.raises(IntegrityError) as error, connection.begin_nested():
        connection.execute(tables[table_name].insert().values(**row))
    assert error.value.orig.sqlstate == sqlstate


@pytest.mark.parametrize(
    ("table_name", "scope"),
    [
        ("group_memberships", None),
        ("user_role_assignments", "GLOBAL"),
        ("user_role_assignments", "UNIT"),
        ("group_role_assignments", "GLOBAL"),
        ("group_role_assignments", "UNIT"),
    ],
)
def test_duplicate_memberships_and_grants_are_rejected(sample, tables, table_name, scope):
    connection, ids = sample
    values = {"institution_id": ids["a"]}
    if table_name != "group_role_assignments":
        values["user_id"] = ids["user"]
    if table_name != "user_role_assignments":
        values["group_id"] = ids["group"]
    if scope:
        values.update(
            role_code="DIRECTORY_READER",
            scope=scope,
            unit_id=ids["unit_a"] if scope == "UNIT" else None,
        )
    statement = tables[table_name].insert().values(**values)
    connection.execute(statement)
    with pytest.raises(IntegrityError) as error, connection.begin_nested():
        connection.execute(statement)
    assert error.value.orig.sqlstate == "23505"


@pytest.mark.parametrize(
    "invalid",
    ["expiry", "revocation", "digest", "infinite_expiry", "infinite_revocation", "infinite_issue"],
)
def test_session_structure_is_enforced(sample, tables, invalid):
    connection, ids = sample
    issued_at = datetime(2026, 1, 1, tzinfo=UTC)
    fields = dict(
        user_id=ids["user"],
        token_digest=b"d" * 32,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(hours=1),
    )
    fields.update(
        {
            "expiry": {"expires_at": issued_at},
            "revocation": {"revoked_at": issued_at - timedelta(seconds=1)},
            "digest": {"token_digest": b"short"},
            "infinite_expiry": {"expires_at": sa.literal_column("'infinity'::timestamptz")},
            "infinite_revocation": {"revoked_at": sa.literal_column("'infinity'::timestamptz")},
            "infinite_issue": {"issued_at": sa.literal_column("'-infinity'::timestamptz")},
        }[invalid]
    )
    with pytest.raises(IntegrityError) as error, connection.begin_nested():
        connection.execute(tables["auth_sessions"].insert().values(**fields))
    assert error.value.orig.sqlstate == "23514"


def test_audit_actor_reference_preserves_historical_identity(sample, tables):
    connection, ids = sample
    connection.execute(
        tables["audit_events"]
        .insert()
        .values(
            institution_id=ids["a"],
            actor_id=ids["user"],
            action="test",
            target_type="user",
            outcome="SUCCESS",
            request_id="test-request",
        )
    )
    with pytest.raises(IntegrityError) as error, connection.begin_nested():
        connection.execute(tables["users"].delete().where(tables["users"].c.id == ids["user"]))
    assert error.value.orig.sqlstate == "23503"
