"""M2 against disposable PostgreSQL: MDL schema, constraints, grants and sealed credentials.

Every test creates its own database through the WP2 helpers (generated name, dropped
afterwards) and uses the real provision -> migrate -> runtime role separation.
"""

import base64
import os
import re
from uuid import uuid4

import psycopg
import pytest

from aq_uai_api.db.provision import MDL_RUNTIME_PRIVILEGES
from aq_uai_api.db.schema import REQUIRED_SCHEMA_REVISION
from aq_uai_api.mdl.credentials import (
    CredentialBinding,
    CredentialUnreadable,
    KeyRing,
    SealedCredential,
    endpoint_origin,
)
from aq_uai_api.mdl.models import MdlProvider

from .test_wp2_database import (
    alembic,
    assert_denied,
    connect,
    disposable_database,
    migrate,
    prepare,
)
from .test_wp2_database import pytestmark as postgres_marks

pytestmark = postgres_marks
MDL_TABLES = (
    "mdl_providers",
    "mdl_provider_credentials",
    "mdl_provider_agreements",
    "mdl_models",
    "mdl_connection_tests",
    "mdl_routing",
    "mdl_routing_revisions",
    "mdl_provider_agreement_withdrawals",  # M3 (0005)
)
# Columns the runtime login may UPDATE. Everything else in an MDL table is immutable to it.
UPDATABLE = {
    "mdl_providers": {
        "name",
        "api_style",
        "endpoint",
        "auth_scheme",
        "auth_header_name",
        "active",
        "connection_version",
        "updated_at",
    },
    "mdl_provider_credentials": {
        "ciphertext",
        "nonce",
        "key_id",
        "credential_version",
        "updated_by",
        "updated_at",
    },
    "mdl_provider_agreements": set(),
    "mdl_models": {
        "display_name",
        "supports_text",
        "supports_image",
        "supports_voice",
        "max_output_tokens",
        "risk_level",
        "active",
        "updated_at",
    },
    "mdl_connection_tests": {
        "status",
        "error_code",
        "http_status_class",
        "latency_ms",
        "finished_at",
    },
    "mdl_routing": {"primary_model_id", "fallback_model_id", "revision", "updated_by", "updated_at"},
    "mdl_routing_revisions": set(),
    "mdl_provider_agreement_withdrawals": set(),
}
SECRET = "sk-m2-canary-4f3c2a19-do-not-store"
KEY = base64.b64encode(os.urandom(32)).decode()
NEXT_KEY = base64.b64encode(os.urandom(32)).decode()


@pytest.fixture(scope="module")
def mdl_db():
    with disposable_database() as (admin, roles, owner, runtime):
        prepare(admin, roles)
        migrate(owner, roles)
        yield admin, roles, owner, runtime


def seed_tenant(owner_url, code):
    """Institution, unit and one user, created by the schema owner (no MDL rows)."""
    institution, unit, user = uuid4(), uuid4(), uuid4()
    with connect(owner_url) as connection:
        connection.execute(
            "INSERT INTO institutions (id, code, name) VALUES (%s, %s, %s)",
            (institution, code, code),
        )
        connection.execute(
            "INSERT INTO units (id, institution_id, code, name) VALUES (%s, %s, 'main', 'Main')",
            (unit, institution),
        )
        connection.execute(
            "INSERT INTO users (id, institution_id, primary_unit_id, username, display_name,"
            " code_type, institutional_code) VALUES (%s, %s, %s, %s, 'Admin', 'STAFF', '1')",
            (user, institution, unit, f"{code.lower()}-admin"),
        )
    return institution, user


def add_provider(connection, institution, name, provider_type="EXTERNAL", **fields):
    values = {
        "endpoint": "https://api.example.test/v1",
        "auth_scheme": "BEARER",
        "auth_header_name": None,
        "api_style": "OPENAI_COMPATIBLE",
        **fields,
    }
    return connection.execute(
        "INSERT INTO mdl_providers (institution_id, name, provider_type, api_style, endpoint,"
        " auth_scheme, auth_header_name) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (
            institution,
            name,
            provider_type,
            values["api_style"],
            values["endpoint"],
            values["auth_scheme"],
            values["auth_header_name"],
        ),
    ).fetchone()[0]


def add_model(connection, institution, provider, technical_id, **fields):
    return connection.execute(
        "INSERT INTO mdl_models (institution_id, provider_id, technical_id, display_name,"
        " supports_text, max_output_tokens, risk_level) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        " RETURNING id",
        (
            institution,
            provider,
            technical_id,
            fields.get("display_name", technical_id),
            fields.get("supports_text", True),
            fields.get("max_output_tokens"),
            fields.get("risk_level"),
        ),
    ).fetchone()[0]


def rejected(connection, statement, params, sqlstate):
    with pytest.raises(psycopg.Error) as caught, connection.transaction():
        connection.execute(statement, params)
    assert caught.value.sqlstate == sqlstate, caught.value.sqlstate


def test_upgrade_creates_empty_tables_without_excluded_configuration(mdl_db):
    _, _, owner, _ = mdl_db
    alembic(owner, "check")
    with connect(owner) as connection:
        for table in MDL_TABLES:
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
        columns = [
            name
            for (name,) in connection.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = 'public' AND table_name LIKE 'mdl\\_%'"
            )
        ]
        assert columns
        # FR-MDL-040 / RULE-MDL-03: no prompt, temperature, creativity or template storage,
        # and no free-form JSON column that could smuggle one in.
        assert not [c for c in columns if re.search("prompt|temperature|creativ|template", c)]
        assert (
            connection.execute(
                "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public'"
                " AND table_name LIKE 'mdl\\_%' AND data_type IN ('json', 'jsonb')"
            ).fetchone()
            == (0,)
        )
        # No plaintext secret column exists anywhere in MDL.
        assert not [c for c in columns if re.search("secret|password|api_key|token$", c)]


def test_runtime_privilege_matrix(mdl_db):
    _, roles, _, runtime = mdl_db
    assert set(MDL_RUNTIME_PRIVILEGES) == set(MDL_TABLES)
    with connect(runtime, autocommit=True) as connection:
        for table in MDL_TABLES:
            # Writes are column-scoped: some INSERT columns, never a whole-table write.
            assert connection.execute(
                "SELECT has_any_column_privilege(current_user, %s, 'INSERT')",
                (f"public.{table}",),
            ).fetchone() == (True,)
            for privilege, expected in (
                ("SELECT", True),
                ("INSERT", False),
                ("UPDATE", False),
                ("DELETE", False),
                ("TRUNCATE", False),
                ("REFERENCES", False),
                ("TRIGGER", False),
            ):
                assert connection.execute(
                    "SELECT has_table_privilege(current_user, %s, %s)",
                    (f"public.{table}", privilege),
                ).fetchone() == (expected,), (table, privilege)
            for (column,) in connection.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = 'public' AND table_name = %s",
                (table,),
            ).fetchall():
                assert connection.execute(
                    "SELECT has_column_privilege(current_user, %s, %s, 'UPDATE')",
                    (f"public.{table}", column),
                ).fetchone() == (column in UPDATABLE[table],), (table, column)
            assert_denied(connection, f"DELETE FROM {table}")
            assert_denied(connection, f"TRUNCATE {table}")
            assert_denied(connection, f"ALTER TABLE {table} DISABLE TRIGGER ALL")
            assert_denied(connection, f"DROP TABLE {table}")
        for statement in (
            "UPDATE mdl_providers SET provider_type = provider_type",
            "UPDATE mdl_providers SET institution_id = institution_id",
            "UPDATE mdl_models SET technical_id = technical_id",
            "UPDATE mdl_models SET provider_id = provider_id",
            "UPDATE mdl_provider_credentials SET provider_id = provider_id",
            "UPDATE mdl_provider_agreements SET document_number = document_number",
            "UPDATE mdl_routing_revisions SET after_primary_name = after_primary_name",
            "UPDATE mdl_connection_tests SET connection_version = connection_version",
            "UPDATE mdl_routing SET institution_id = institution_id",
            "UPDATE mdl_provider_agreement_withdrawals SET withdrawn_at = withdrawn_at",
        ):
            assert_denied(connection, statement)
        assert connection.execute(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = %s", (roles.runtime,)
        ).fetchone() == (False,)


def test_constraints_enforce_identity_tenancy_and_routing_rules(mdl_db):
    _, _, owner, runtime = mdl_db
    tenant, actor = seed_tenant(owner, "M2A")
    other, other_actor = seed_tenant(owner, "M2B")
    with connect(runtime, autocommit=True) as db:
        external = add_provider(db, tenant, "Vendor")
        internal = add_provider(
            db, tenant, "On-prem", "INTERNAL", endpoint="http://ollama:11434/v1", auth_scheme="NONE"
        )
        foreign = add_provider(db, other, "Vendor")  # same name, other tenant: allowed
        first = add_model(db, tenant, external, "model-a", risk_level="LOW")
        second = add_model(db, tenant, internal, "model-b")
        foreign_model = add_model(db, other, foreign, "model-a")
        add_model(db, tenant, internal, "model-a")  # same technical ID, other provider: allowed

        provider_sql = (
            "INSERT INTO mdl_providers (institution_id, name, provider_type, api_style, endpoint,"
            " auth_scheme, auth_header_name) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )
        good = [tenant, "X", "EXTERNAL", "OPENAI_COMPATIBLE", "https://x.test", "BEARER", None]
        for index, value, state in (
            (1, "VENDOR", "23505"),  # case-insensitive unique name per tenant
            (1, " padded", "23514"),
            (1, "", "23514"),
            (2, "CLOUD", "23514"),
            (3, "ANTHROPIC_NATIVE", "23514"),
            (4, "ftp://x.test", "23514"),
            (4, "https://user:pw@x.test", "23514"),
            (4, "https://x.test/a b", "23514"),
            (5, "OAUTH", "23514"),
        ):
            rejected(db, provider_sql, [*good[:index], value, *good[index + 1 :]], state)
        rejected(db, provider_sql, [*good[:5], "HEADER_KEY", None], "23514")
        rejected(db, provider_sql, [*good[:5], "BEARER", "X-Api-Key"], "23514")
        rejected(db, provider_sql, [*good[:5], "HEADER_KEY", "Bad Header"], "23514")
        rejected(db, provider_sql, [*good[:5], "HEADER_KEY", "X\r\nInjected"], "23514")
        add_provider(db, tenant, "Keyed", auth_scheme="HEADER_KEY", auth_header_name="X-Api-Key")
        rejected(
            db,
            provider_sql,
            [uuid4(), "Orphan", "EXTERNAL", "OPENAI_COMPATIBLE", "https://x.test", "NONE", None],
            "23503",
        )

        model_sql = (
            "INSERT INTO mdl_models (institution_id, provider_id, technical_id, display_name,"
            " supports_text, supports_image, supports_voice, max_output_tokens, risk_level)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        base = [tenant, external, "model-z", "Z", True, False, False, None, None]
        for index, value, state in (
            (0, other, "23503"),  # provider of another institution
            (2, "model-a", "23505"),  # duplicate technical ID under the same provider
            (2, " model", "23514"),
            (3, "", "23514"),
            (7, 0, "23514"),
            (8, "NONE", "23514"),
            (8, "Cao", "23514"),  # prototype labels are not stored codes
        ):
            rejected(db, model_sql, [*base[:index], value, *base[index + 1 :]], state)
        rejected(db, model_sql, [*base[:4], False, False, False, None, None], "23514")

        agreement_sql = (
            "INSERT INTO mdl_provider_agreements (institution_id, provider_id, provider_type,"
            " basis, document_number, recorded_by) VALUES (%s, %s, %s, %s, %s, %s)"
        )
        db.execute(
            agreement_sql, (tenant, external, "EXTERNAL", "NO_TRAINING_COMMITMENT", "HD-01", actor)
        )
        rejected(  # agreements exist only for external providers
            db,
            agreement_sql,
            (tenant, internal, "INTERNAL", "NO_TRAINING_COMMITMENT", "HD-02", actor),
            "23514",
        )
        rejected(  # and the copied type must match the provider's real type
            db,
            agreement_sql,
            (tenant, internal, "EXTERNAL", "NO_TRAINING_COMMITMENT", "HD-02", actor),
            "23503",
        )
        for basis, number, recorder, state in (
            ("LEGAL_OPINION", "HD-03", actor, "23514"),
            ("SCHOOL_WRITTEN_AUTHORIZATION", "  ", actor, "23514"),
            ("SCHOOL_WRITTEN_AUTHORIZATION", "HD-04", other_actor, "23503"),  # foreign actor
        ):
            rejected(
                db, agreement_sql, (tenant, external, "EXTERNAL", basis, number, recorder), state
            )

        routing_sql = (
            "INSERT INTO mdl_routing (institution_id, primary_model_id, fallback_model_id,"
            " revision, updated_by) VALUES (%s, %s, %s, %s, %s)"
        )
        rejected(db, routing_sql, (tenant, first, first, 1, actor), "23514")  # fallback = primary
        rejected(db, routing_sql, (tenant, None, first, 1, actor), "23514")  # fallback alone
        rejected(db, routing_sql, (tenant, foreign_model, None, 1, actor), "23503")
        rejected(db, routing_sql, (tenant, first, foreign_model, 1, actor), "23503")
        rejected(db, routing_sql, (tenant, first, None, 0, actor), "23514")
        rejected(db, routing_sql, (tenant, first, None, 1, other_actor), "23503")
        db.execute(routing_sql, (tenant, first, second, 1, actor))
        rejected(db, routing_sql, (tenant, second, None, 2, actor), "23505")  # singleton (D8)
        rejected(
            db,
            "UPDATE mdl_routing SET fallback_model_id = primary_model_id WHERE institution_id = %s",
            (tenant,),
            "23514",
        )

        revision_sql = (
            "INSERT INTO mdl_routing_revisions (institution_id, revision, after_primary_model_id,"
            " after_primary_name, after_fallback_model_id, after_fallback_name, changed_by)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )
        db.execute(revision_sql, (tenant, 1, first, "A", second, "B", actor))
        rejected(db, revision_sql, (tenant, 1, first, "A", None, None, actor), "23505")
        rejected(db, revision_sql, (tenant, 2, first, None, None, None, actor), "23514")
        rejected(db, revision_sql, (tenant, 2, first, "A", first, "A", actor), "23514")
        rejected(db, revision_sql, (tenant, 2, foreign_model, "F", None, None, actor), "23503")

        test_sql = (
            "INSERT INTO mdl_connection_tests (institution_id, model_id, connection_version,"
            " credential_version, started_by) VALUES (%s, %s, %s, %s, %s) RETURNING id, status"
        )
        running, status = db.execute(test_sql, (tenant, first, 1, 1, actor)).fetchone()
        assert status == "RUNNING"
        rejected(db, test_sql, (tenant, first, 1, 1, actor), "23505")  # one RUNNING per model
        rejected(db, test_sql, (tenant, foreign_model, 1, 1, actor), "23503")
        rejected(db, test_sql, (tenant, second, 0, None, actor), "23514")
        complete = "UPDATE mdl_connection_tests SET status = %s, error_code = %s, finished_at = %s"
        rejected(db, complete + " WHERE id = %s", ("PASSED", None, None, running), "23514")
        rejected(db, complete + " WHERE id = %s", ("FAILED", None, "now", running), "23514")
        rejected(db, complete + " WHERE id = %s", ("PASSED", "TIMEOUT", "now", running), "23514")
        rejected(db, complete + " WHERE id = %s", ("FAILED", "bad code", "now", running), "23514")
        db.execute(complete + " WHERE id = %s", ("FAILED", "TIMEOUT", "now", running))
        db.execute(test_sql, (tenant, first, 1, 1, actor))  # a new run is allowed afterwards


def test_sealed_credentials_round_trip_through_the_runtime_login(mdl_db):
    _, _, owner, runtime = mdl_db
    tenant, actor = seed_tenant(owner, "M2C")
    keys = KeyRing.parse(f"k1:{KEY}", "k1")
    with connect(runtime, autocommit=True) as db:
        endpoint = "https://API.example.test/v1"
        providers = [add_provider(db, tenant, name, endpoint=endpoint) for name in ("P1", "P2")]

        origin = endpoint_origin(endpoint)

        def binding(provider, version=1, bound_origin=None):
            return CredentialBinding(tenant, provider, bound_origin or origin, version)

        def store(provider, sealed, version=1):
            db.execute(
                "INSERT INTO mdl_provider_credentials (provider_id, institution_id, ciphertext,"
                " nonce, key_id, credential_version, updated_by)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (provider, tenant, sealed.ciphertext, sealed.nonce, sealed.key_id, version, actor),
            )

        def load(provider):
            ciphertext, nonce, key_id, version = db.execute(
                "SELECT ciphertext, nonce, key_id, credential_version"
                " FROM mdl_provider_credentials WHERE provider_id = %s",
                (provider,),
            ).fetchone()
            return SealedCredential(bytes(ciphertext), bytes(nonce), key_id), version

        for provider in providers:
            store(provider, keys.seal(SECRET, binding(provider)))
        sealed, version = load(providers[0])
        assert keys.open(sealed, binding(providers[0], version)).get_secret_value() == SECRET

        # Plaintext and key material never reach the database, in any column of any table.
        dump = " ".join(
            str(row)
            for table in (*MDL_TABLES, "audit_events")
            for row in db.execute(f"SELECT row_to_json(t)::text FROM {table} t").fetchall()
        )
        assert SECRET not in dump and KEY not in dump
        assert db.execute(
            "SELECT count(*) FROM mdl_provider_credentials"
            " WHERE position(convert_to(%s, 'UTF8') in ciphertext) > 0",
            (SECRET,),
        ).fetchone() == (0,)

        # Duplicate credential row for a provider and a foreign-tenant row are refused.
        rejected(
            db,
            "INSERT INTO mdl_provider_credentials (provider_id, institution_id, ciphertext, nonce,"
            " key_id, updated_by) VALUES (%s, %s, %s, %s, %s, %s)",
            (providers[0], tenant, sealed.ciphertext, sealed.nonce, "k1", actor),
            "23505",
        )
        for ciphertext, nonce, key_id in (
            (sealed.ciphertext, b"short", "k1"),
            (b"x" * 16, sealed.nonce, "k1"),
            (b"x" * 4113, sealed.nonce, "k1"),
            (sealed.ciphertext, sealed.nonce, "K1"),
        ):
            rejected(
                db,
                "UPDATE mdl_provider_credentials SET ciphertext = %s, nonce = %s, key_id = %s"
                " WHERE provider_id = %s",
                (ciphertext, nonce, key_id, providers[0]),
                "23514",
            )

        # Swapping ciphertext between providers (a database-level tamper) fails closed.
        other_sealed, _ = load(providers[1])
        db.execute(
            "UPDATE mdl_provider_credentials SET ciphertext = %s, nonce = %s WHERE provider_id = %s",
            (other_sealed.ciphertext, other_sealed.nonce, providers[0]),
        )
        swapped, _ = load(providers[0])
        with pytest.raises(CredentialUnreadable):
            keys.open(swapped, binding(providers[0]))

        # Redirecting the endpoint to another host in the database fails closed.
        db.execute(
            "UPDATE mdl_providers SET endpoint = 'https://evil.example.test/v1' WHERE id = %s",
            (providers[1],),
        )
        current = db.execute(
            "SELECT endpoint FROM mdl_providers WHERE id = %s", (providers[1],)
        ).fetchone()[0]
        stored, version = load(providers[1])
        with pytest.raises(CredentialUnreadable):
            keys.open(stored, binding(providers[1], version, endpoint_origin(current)))
        # A rolled-back credential_version also fails closed.
        db.execute(
            "UPDATE mdl_provider_credentials SET credential_version = 2 WHERE provider_id = %s",
            (providers[1],),
        )
        stored, version = load(providers[1])
        with pytest.raises(CredentialUnreadable):
            keys.open(stored, binding(providers[1], version))

        # Rotation through the runtime grants: rewrap to a new active key in place.
        provider = add_provider(db, tenant, "P3", endpoint=endpoint)
        store(provider, keys.seal(SECRET, binding(provider)))
        rotated = KeyRing.parse(f"k1:{KEY},k2:{NEXT_KEY}", "k2")
        old, version = load(provider)
        new = rotated.rewrap(old, binding(provider, version))
        db.execute(
            "UPDATE mdl_provider_credentials SET ciphertext = %s, nonce = %s, key_id = %s,"
            " updated_at = now() WHERE provider_id = %s",
            (new.ciphertext, new.nonce, new.key_id, provider),
        )
        reloaded, version = load(provider)
        assert reloaded.key_id == "k2"
        retired = KeyRing.parse(f"k2:{NEXT_KEY}", "k2")
        assert retired.open(reloaded, binding(provider, version)).get_secret_value() == SECRET


def test_orm_mapping_matches_and_has_no_secret_fields():
    columns = {column.name for column in MdlProvider.__table__.columns}
    assert not columns & {"secret", "api_key", "credential", "password", "ciphertext"}


def test_populated_m1_database_upgrades_to_m2_without_changes():
    """0003 database with an MDL admin grant -> provision -> migrate to 0004."""
    with disposable_database() as (admin, roles, owner, runtime):
        alembic(admin, "upgrade", "0003_mdl_access_catalog")
        institution, unit, user = uuid4(), uuid4(), uuid4()
        with connect(admin) as connection:
            connection.execute(
                "INSERT INTO institutions (id, code, name) VALUES (%s, 'M1', 'M1')", (institution,)
            )
            connection.execute(
                "INSERT INTO units (id, institution_id, code, name) VALUES (%s, %s, 'u', 'U')",
                (unit, institution),
            )
            connection.execute(
                "INSERT INTO users (id, institution_id, primary_unit_id, username, display_name,"
                " code_type, institutional_code) VALUES (%s, %s, %s, 'm1', 'M1', 'STAFF', '1')",
                (user, institution, unit),
            )
            connection.execute(
                "INSERT INTO user_role_assignments (institution_id, user_id, role_code, scope)"
                " VALUES (%s, %s, 'AI_MODEL_ADMIN', 'GLOBAL')",
                (institution, user),
            )
            before = connection.execute(
                "SELECT (SELECT count(*) FROM roles), (SELECT count(*) FROM role_permissions),"
                " (SELECT count(*) FROM user_role_assignments), (SELECT count(*) FROM users)"
            ).fetchone()
        prepare(admin, roles)
        migrate(owner, roles)
        alembic(owner, "check")
        migrate(owner, roles)  # second run is a no-op
        with connect(runtime) as connection:
            assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
                REQUIRED_SCHEMA_REVISION,
            )
            # Upgrading 0003 -> head adds QTA roles (+2) and role_permissions (+3) while
            # preserving all existing user_role_assignments and users verbatim.
            after = connection.execute(
                "SELECT (SELECT count(*) FROM roles), (SELECT count(*) FROM role_permissions),"
                " (SELECT count(*) FROM user_role_assignments), (SELECT count(*) FROM users)"
            ).fetchone()
            assert after == (before[0] + 2, before[1] + 3, before[2], before[3])
            assert connection.execute(
                "SELECT role_code, scope FROM user_role_assignments WHERE user_id = %s", (user,)
            ).fetchone() == ("AI_MODEL_ADMIN", "GLOBAL")
            for table in MDL_TABLES:
                assert connection.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
            # Owner of every MDL relation is the schema role, not the runtime or bootstrap.
            owners = connection.execute(
                "SELECT DISTINCT pg_get_userbyid(relowner) FROM pg_class"
                " WHERE relname LIKE 'mdl\\_%'"
            ).fetchall()
            assert owners == [(roles.migration,)]
