"""Provision least-privilege login roles for the dedicated AQ EduUAI database."""

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import Connection, sql

from aq_uai_api.core.config import Settings

LEGACY_TABLES = frozenset(
    {
        "alembic_version",
        "app_metadata",
        "institutions",
        "units",
        "users",
        "user_credentials",
        "account_groups",
        "group_memberships",
        "roles",
        "permissions",
        "role_permissions",
        "user_role_assignments",
        "group_role_assignments",
        "auth_sessions",
        "auth_throttle_buckets",
        "audit_events",
        # M2 (0004_mdl_schema). A database restored or migrated by the bootstrap owner
        # holds these too; provisioning must take them over like the tables above.
        "mdl_providers",
        "mdl_provider_credentials",
        "mdl_provider_agreements",
        "mdl_models",
        "mdl_connection_tests",
        "mdl_routing",
        "mdl_routing_revisions",
        "mdl_provider_agreement_withdrawals",  # M3 (0005)
        # Q1-R (0008_qta_schema). Keep every application table provisionable after restore.
        "qta_budget_revisions",
        "qta_quota_groups",
        "qta_group_model_quotas",
        "qta_group_sync_runs",
        "qta_suspensions",
        "qta_suspension_restorations",
        "qta_monthly_resets",
        "qta_events",
    }
)
RUNTIME_READ_TABLES = (
    "alembic_version",
    "app_metadata",
    "institutions",
    "units",
    "users",
    "account_groups",
    "group_memberships",
    "roles",
    "permissions",
    "role_permissions",
    "user_role_assignments",
    "group_role_assignments",
    "audit_events",
)


# M2 (0004_mdl_schema). Least privilege for the runtime login:
# - no DELETE on any MDL table (FR-MDL-012: no hard delete; history is append-only);
# - agreements, withdrawals and routing revisions are INSERT-only (append-only history);
# - immutable columns (institution_id, provider_type, provider_id, technical_id, ids,
#   creation times, test snapshots) are absent from every UPDATE list;
# - credentials: ciphertext, nonce and key ID only. The key never reaches PostgreSQL.
MDL_RUNTIME_PRIVILEGES = {
    "mdl_providers": (
        "SELECT, INSERT (institution_id, name, provider_type, api_style, endpoint, auth_scheme, "
        "auth_header_name), UPDATE (name, api_style, endpoint, auth_scheme, auth_header_name, "
        "active, connection_version, updated_at)"
    ),
    "mdl_provider_credentials": (
        "SELECT, INSERT (provider_id, institution_id, ciphertext, nonce, key_id, "
        "credential_version, updated_by), UPDATE (ciphertext, nonce, key_id, "
        "credential_version, updated_by, updated_at)"
    ),
    "mdl_provider_agreements": (
        "SELECT, INSERT (institution_id, provider_id, provider_type, basis, document_number, "
        "signed_on, recorded_by)"
    ),
    "mdl_models": (
        "SELECT, INSERT (institution_id, provider_id, technical_id, display_name, supports_text, "
        "supports_image, supports_voice, max_output_tokens, risk_level), UPDATE (display_name, "
        "supports_text, supports_image, supports_voice, max_output_tokens, risk_level, active, "
        "updated_at)"
    ),
    "mdl_connection_tests": (
        "SELECT, INSERT (institution_id, model_id, connection_version, credential_version, "
        "started_by), UPDATE (status, error_code, http_status_class, latency_ms, finished_at)"
    ),
    "mdl_routing": (
        "SELECT, INSERT (institution_id, primary_model_id, fallback_model_id, revision, "
        "updated_by), UPDATE (primary_model_id, fallback_model_id, revision, updated_by, "
        "updated_at)"
    ),
    "mdl_provider_agreement_withdrawals": (
        "SELECT, INSERT (agreement_id, institution_id, withdrawn_by)"
    ),
    "mdl_routing_revisions": (
        "SELECT, INSERT (institution_id, revision, before_primary_model_id, "
        "before_fallback_model_id, after_primary_model_id, after_fallback_model_id, "
        "before_primary_name, before_fallback_name, after_primary_name, after_fallback_name, "
        "decision_reference, changed_by)"
    ),
}
# Q1-R (0008_qta_schema). Least privilege for the runtime login:
# - no DELETE on any QTA table (FR-QTA-050 / RULE-QTA-04: append-only history);
# - budget revisions, sync runs, suspensions, restorations, monthly resets and events are
#   INSERT-only (no UPDATE, no DELETE);
# - registry rows allow UPDATE only on sync-maintained columns (in_directory, last_synced_at);
# - immutable identity columns are excluded from UPDATE on group quotas.
QTA_RUNTIME_PRIVILEGES = {
    "qta_budget_revisions": (
        "SELECT, INSERT (institution_id, period_month, revision, total_limit, "
        "decision_number, decision_date, recorded_by)"
    ),
    "qta_quota_groups": (
        "SELECT, INSERT (institution_id, group_id, group_kind, origin, in_directory, "
        "enrolled_by, last_synced_at), UPDATE (in_directory, last_synced_at)"
    ),
    "qta_group_model_quotas": (
        "SELECT, INSERT (institution_id, group_id, model_id, enabled, monthly_limit, "
        "warning_threshold_pct, updated_by), UPDATE (enabled, monthly_limit, "
        "warning_threshold_pct, updated_by, updated_at)"
    ),
    "qta_group_sync_runs": (
        "SELECT, INSERT (institution_id, system_group_count, active_member_count, "
        "specialist_group_count, groups_added, groups_retired, synced_by)"
    ),
    "qta_suspensions": (
        "SELECT, INSERT (institution_id, user_id, scope, reason, ordered_by, expires_at, "
        "suspended_by)"
    ),
    "qta_suspension_restorations": (
        "SELECT, INSERT (suspension_id, institution_id, restored_by, note)"
    ),
    "qta_monthly_resets": (
        "SELECT, INSERT (institution_id, period_month, trigger_mode, triggered_by)"
    ),
    "qta_events": (
        "SELECT, INSERT (institution_id, period_month, event_type, user_id, actor_id, summary)"
    ),
}
# The credential key ring is for the api service only (D14). Database setup refuses to
# run when it can see one, so a misconfigured Compose file fails loudly, not silently.
API_ONLY_ENVIRONMENT = ("AQ_UAI_MDL_CREDENTIAL_KEYS", "AQ_UAI_MDL_CREDENTIAL_ACTIVE_KEY_ID")


@dataclass(frozen=True)
class DatabaseRoles:
    migration: str = "aq_uai_schema"
    runtime: str = "aq_uai_runtime"


class ProvisioningError(Exception):
    """Operator-safe message with no SQL, server diagnostics, or credentials."""


def _connect(settings: Settings, *, provisioning: bool = False) -> Connection:
    return psycopg.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        connect_timeout=3,
        options="-c log_transaction_sample_rate=0" if provisioning else None,
    )


def _ensure_role(connection: Connection, name: str, database: str, purpose: str, password: str):
    marker = f"AQ EduUAI WP2 {purpose} for {database}"
    existing = connection.execute(
        "SELECT oid, shobj_description(oid, 'pg_authid') FROM pg_roles WHERE rolname = %s", (name,)
    ).fetchone()
    role = sql.Identifier(name)
    if existing is None:
        connection.execute(sql.SQL("CREATE ROLE {}").format(role))
        connection.execute(sql.SQL("COMMENT ON ROLE {} IS {}").format(role, sql.Literal(marker)))
    elif existing[1] != marker:
        raise ProvisioningError("A managed role name is already used by another installation.")
    elif connection.execute(
        "SELECT 1 FROM pg_auth_members WHERE member = %s OR roleid = %s", (existing[0], existing[0])
    ).fetchone():
        raise ProvisioningError("Remove unexpected memberships on the managed database roles.")

    # PostgreSQL's ALTER ROLE grammar requires a literal. Send a SCRAM verifier,
    # and suppress statement logging for this provisioning transaction.
    verifier = connection.pgconn.encrypt_password(
        password.encode(), name.encode(), b"scram-sha-256"
    ).decode()
    connection.execute(
        sql.SQL(
            "ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
            "NOREPLICATION NOBYPASSRLS PASSWORD {}"
        ).format(role, sql.Literal(verifier))
    )


_PRIVILEGE_CLAUSE = re.compile(r"\s*([A-Z]+)\s*(?:\(([^)]*)\))?\s*(?:,|$)")


def present_privileges(privileges: str, existing: set[str]) -> str:
    """Keep only columns that exist now (M5 fix).

    ``prepare`` runs before ``migrate``: on an older database a column added by a later
    migration (for example ``decision_reference`` in 0006) does not exist yet, and a
    column grant naming it would abort provisioning. The grant after migration (``migrate``
    calls this again) then includes the new column. Clause order and spelling are kept.
    """
    clauses = []
    for match in _PRIVILEGE_CLAUSE.finditer(privileges):
        verb, names = match.group(1), match.group(2)
        if names is None:
            clauses.append(verb)
            continue
        kept = [name.strip() for name in names.split(",") if name.strip() in existing]
        if kept:
            clauses.append(f"{verb} ({', '.join(kept)})")
    if not clauses:
        raise ProvisioningError("No privilege applies to the current table definition.")
    return ", ".join(clauses)


def apply_runtime_privileges(connection: Connection, roles: DatabaseRoles) -> None:
    """Reconcile ACLs after ownership transfer and again after Alembic creates tables."""
    runtime = sql.Identifier(roles.runtime)
    for kind in ("TABLES", "SEQUENCES"):
        connection.execute(
            sql.SQL("REVOKE ALL ON ALL {} IN SCHEMA public FROM PUBLIC, {}").format(
                sql.SQL(kind), runtime
            )
        )
    present = {
        name
        for (name,) in connection.execute(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')"
        )
    }
    for table in RUNTIME_READ_TABLES:
        if table in present:
            connection.execute(
                sql.SQL("GRANT SELECT ON TABLE {} TO {}").format(
                    sql.Identifier("public", table), runtime
                )
            )
    if "audit_events" in present:
        connection.execute(
            sql.SQL("GRANT INSERT ON TABLE public.audit_events TO {}").format(runtime)
        )
    if "user_credentials" in present:
        connection.execute(
            sql.SQL(
                "GRANT SELECT, INSERT (user_id, password_hash, must_change_password), "
                "UPDATE (password_hash, must_change_password, updated_at) "
                "ON TABLE public.user_credentials TO {}"
            ).format(runtime)
        )
    if "auth_sessions" in present:
        connection.execute(
            sql.SQL(
                "GRANT SELECT, INSERT (user_id, token_digest, issued_at, expires_at), "
                "UPDATE (revoked_at) ON TABLE public.auth_sessions TO {}"
            ).format(runtime)
        )
    if "auth_throttle_buckets" in present:
        connection.execute(
            sql.SQL(
                "GRANT SELECT, INSERT, UPDATE (failure_count), DELETE "
                "ON TABLE public.auth_throttle_buckets TO {}"
            ).format(runtime)
        )
    directory_writes = {
        "units": "INSERT (institution_id, code, name), UPDATE (code, name, active)",
        "users": (
            "INSERT (institution_id, primary_unit_id, username, display_name, code_type, "
            "institutional_code, state), UPDATE (primary_unit_id, username, display_name, "
            "code_type, institutional_code, state, updated_at)"
        ),
        "account_groups": (
            "INSERT (institution_id, code, name, kind), UPDATE (name, active, updated_at)"
        ),
        "group_memberships": (
            "INSERT (institution_id, group_id, user_id, active), UPDATE (active, updated_at)"
        ),
        "user_role_assignments": (
            "INSERT (institution_id, user_id, role_code, scope, unit_id), DELETE"
        ),
        "group_role_assignments": (
            "INSERT (institution_id, group_id, role_code, scope, unit_id), DELETE"
        ),
    }
    columns: dict[str, set[str]] = {}
    for table, column in connection.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public'"
    ):
        columns.setdefault(table, set()).add(column)
    for table, privileges in (
        directory_writes | MDL_RUNTIME_PRIVILEGES | QTA_RUNTIME_PRIVILEGES
    ).items():
        if table in present:
            connection.execute(
                sql.SQL("GRANT {} ON TABLE {} TO {}").format(
                    sql.SQL(present_privileges(privileges, columns[table])),
                    sql.Identifier("public", table),
                    runtime,
                )
            )


def prepare_database(
    connection: Connection,
    roles: DatabaseRoles,
    migration_password: str,
    runtime_password: str,
) -> None:
    """Run as the bootstrap owner inside one PostgreSQL transaction."""
    database, bootstrap, owner, superuser = connection.execute(
        "SELECT current_database(), current_user, pg_get_userbyid(d.datdba), r.rolsuper "
        "FROM pg_database d JOIN pg_roles r ON r.rolname = current_user "
        "WHERE d.datname = current_database()"
    ).fetchone()
    if not superuser or bootstrap != owner or len({bootstrap, roles.migration, roles.runtime}) != 3:
        raise ProvisioningError("Use the dedicated database's original bootstrap owner.")
    if database in {"postgres", "template0", "template1"}:
        raise ProvisioningError("Provision a dedicated application database.")
    if (
        any(
            len(password) < 16 or password.startswith("CHANGE_THIS_")
            for password in (migration_password, runtime_password)
        )
        or migration_password == runtime_password
    ):
        raise ProvisioningError(
            "Set distinct migration and runtime passwords of at least 16 characters."
        )
    connection.execute("SELECT pg_advisory_xact_lock(18002802)")
    connection.execute("SET LOCAL log_statement = 'none'")
    connection.execute("SET LOCAL log_duration = off")
    connection.execute("SET LOCAL log_min_duration_statement = -1")
    connection.execute("SET LOCAL log_min_duration_sample = -1")
    connection.execute("SET LOCAL log_transaction_sample_rate = 0")
    connection.execute("SET LOCAL log_min_error_statement = 'panic'")

    # Treat public as the dedicated app schema. Refuse unrelated schemas or
    # objects with unknown owners instead of reassigning a whole cluster role.
    if connection.execute(
        "SELECT 1 FROM pg_namespace "
        "WHERE nspname NOT IN ('public', 'information_schema') AND nspname !~ '^pg_'"
    ).fetchone():
        raise ProvisioningError("Unexpected user schemas exist in the application database.")
    schema_owner = connection.execute(
        "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'public'"
    ).fetchone()
    if schema_owner is None or schema_owner[0] not in {
        bootstrap,
        "pg_database_owner",
        roles.migration,
    }:
        raise ProvisioningError("The public schema has an unexpected owner.")

    _ensure_role(connection, roles.migration, database, "migration", migration_password)
    _ensure_role(connection, roles.runtime, database, "runtime", runtime_password)
    migrator = sql.Identifier(roles.migration)
    runtime = sql.Identifier(roles.runtime)
    database_name = sql.Identifier(database)
    connection.execute(
        sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC, {}, {}").format(
            database_name, migrator, runtime
        )
    )
    connection.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(database_name, migrator, runtime)
    )
    connection.execute(sql.SQL("ALTER SCHEMA public OWNER TO {}").format(migrator))
    connection.execute(sql.SQL("REVOKE ALL ON SCHEMA public FROM PUBLIC, {}").format(runtime))
    connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(runtime))

    for name, kind, object_owner in connection.execute(
        "SELECT c.relname, c.relkind, pg_get_userbyid(c.relowner) FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')"
    ).fetchall():
        if object_owner == roles.migration:
            continue
        if object_owner != bootstrap or name not in LEGACY_TABLES or kind != "r":
            raise ProvisioningError("An unmanaged relation requires an explicit ownership review.")
        connection.execute(
            sql.SQL("ALTER TABLE {} OWNER TO {}").format(sql.Identifier("public", name), migrator)
        )

    for kind in ("TABLES", "SEQUENCES", "FUNCTIONS", "TYPES"):
        for scope in (sql.SQL(""), sql.SQL(" IN SCHEMA public")):
            connection.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {}{} REVOKE ALL ON {} FROM PUBLIC, {}"
                ).format(migrator, scope, sql.SQL(kind), runtime)
            )
    # The bootstrap owner can revoke legacy routine grants. The migrator's
    # default privileges protect new routines after the handoff.
    connection.execute(
        sql.SQL("REVOKE ALL ON ALL ROUTINES IN SCHEMA public FROM PUBLIC, {}").format(runtime)
    )
    apply_runtime_privileges(connection, roles)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "migrate"))
    parser.add_argument("--config", type=Path, default=Path("alembic.ini"))
    args = parser.parse_args()
    roles = DatabaseRoles()
    try:
        if any(name in os.environ for name in API_ONLY_ENVIRONMENT):
            raise ProvisioningError(
                "The MDL credential key ring must be given to the api service only."
            )
        settings = Settings()
        if args.operation == "prepare":
            migration_password = os.environ.get("AQ_UAI_MIGRATION_PASSWORD", "")
            runtime_password = os.environ.get("AQ_UAI_RUNTIME_PASSWORD", "")
            if not settings.db_password or settings.db_password in {
                migration_password,
                runtime_password,
            }:
                raise ProvisioningError("Set distinct bootstrap, migration, and runtime passwords.")
            with _connect(settings, provisioning=True) as connection:
                prepare_database(connection, roles, migration_password, runtime_password)
        else:
            if settings.db_user != roles.migration:
                raise ProvisioningError("Run migrations with the dedicated schema-owner login.")
            command.upgrade(Config(str(args.config)), "head")
            with _connect(settings) as connection:
                apply_runtime_privileges(connection, roles)
    except ProvisioningError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        print(
            "Database setup failed. Check the role settings, connectivity, and schema state.",
            file=sys.stderr,
        )
        return 1
    print("Database setup step completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
