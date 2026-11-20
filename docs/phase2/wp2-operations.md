# WP2 database roles and rollout

For the current checkout, first configure the authentication settings in the [WP3 operations guide](wp3-operations.md#rollout-after-approval). That guide also lists the additional WP3 runtime privileges.

WP2 separates PostgreSQL maintenance, schema changes, and requests. The API receives a restricted database login. This limits what an API failure or an unintended database write can change.

## Effective privileges

| Capability in the AQ EduUAI database | Bootstrap owner | `aq_uai_schema` | `aq_uai_runtime` |
|---|---|---|---|
| PostgreSQL superuser and database owner | Yes | No | No |
| Own or change the application schema, tables, and indexes | Maintenance authority | Owns `public` and application objects | No |
| Run Alembic and reconcile runtime table grants | Maintenance authority | Yes | No |
| Read metadata, the revision, directory, and authorization catalog | Yes | Yes | Yes |
| Read credentials, session digests, and throttle state | Yes | Yes | No |
| Write directory rows, the catalog, or migration metadata | Yes | Yes | No |
| Read and append audit events | Yes | Yes | Yes |
| Edit, delete, truncate, or alter audit events | Maintenance authority | Maintenance authority | No |
| Create roles, databases, schemas, or temporary tables | Yes | No | No |

The provisioning step removes ambient `PUBLIC` access in the target database and reconciles default privileges for objects the schema owner creates. It refuses a pre-existing role name from a different installation or unexpected role memberships. Existing Phase 1 and WP1 tables are transferred in-place. PostgreSQL transfers their indexes with the tables. Unmanaged objects with an unexpected owner require review. This procedure assumes the dedicated AQ EduUAI database and a dedicated local PostgreSQL instance. It does not configure access to other databases in the instance.

The runtime table grants are an allowlist. Future packages must extend it alongside the operations that need additional privileges. Audit events are append-only for the runtime role. The schema owner and maintenance account can still perform controlled recovery.

## Configure credentials

Use three distinct passwords. Generate each with a password manager or `openssl rand -hex 32` redirected to a private file. Avoid putting password values in shell commands. Edit `.env` locally and restrict its permissions with `chmod 600 .env`.

- `POSTGRES_USER` and `POSTGRES_PASSWORD` identify the database bootstrap owner. They are used by PostgreSQL and the provisioning service. On an existing volume, keep the actual initialized username and password. Editing these variables alone cannot change passwords in a volume that PostgreSQL has already initialized.
- `AQ_UAI_MIGRATION_PASSWORD` is for `aq_uai_schema`. It goes to provisioning and is mapped to `AQ_UAI_DB_PASSWORD` in the migration container.
- `AQ_UAI_RUNTIME_PASSWORD` is for `aq_uai_runtime`. It goes to provisioning and is mapped to `AQ_UAI_DB_PASSWORD` in the API container.
- `POSTGRES_DB` identifies the existing application database. Keep its value when transitioning an existing volume. The three published ports remain bound to localhost.

Compose substitutes explicitly listed variables. It does not load the full dotenv file into either application service. Docker administrators can inspect container credentials. Treat access to Docker as privileged.

## Fresh installation

1. Copy `.env.example` to a new `.env` and set the three passwords.
2. From the repository root run `bash scripts/dev-up.sh`. Compose starts PostgreSQL, runs provisioning, applies Alembic with the schema owner, grants runtime access, then starts the API and nginx.
3. Run the verification below. Stop with `bash scripts/dev-down.sh` when done. Retain the database volume.

## Existing Phase 1 or WP1 installation

Do this after review, during a local maintenance window. Use the original Compose project and named volume. Add the two new password settings first, keeping the database name and original bootstrap credentials. Compose resolves all service variables even when a command targets only the database. Take a backup while the existing database is running. Both commands below must succeed before proceeding.

```bash
umask 077
wp2_backup="$(mktemp "$HOME/aq-uai-before-wp2.XXXXXXXX.dump")"
docker compose --env-file .env -f infra/compose.yaml exec -T db sh -c \
  'pg_dump --format=custom --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' > "$wp2_backup"
docker compose --env-file .env -f infra/compose.yaml exec -T db pg_restore --list < "$wp2_backup"
```

For valuable data, rehearse restoring the backup in a separate disposable PostgreSQL instance. Stop the old API and web services before changing ownership. Run each step in order and check its exit status.

```bash
docker compose --env-file .env -f infra/compose.yaml stop api web
docker compose --env-file .env -f infra/compose.yaml run --rm --no-deps --build provision
docker compose --env-file .env -f infra/compose.yaml run --rm --no-deps --build migrate
docker compose --env-file .env -f infra/compose.yaml up -d --no-deps --build api
docker compose --env-file .env -f infra/compose.yaml up -d --no-deps web
```

Provisioning is one PostgreSQL transaction. It reconciles passwords and grants and preserves data. A failed provisioning transaction rolls back ownership and ACL changes. Alembic and the grant reconciliation in the migration job are separate transactions. If the migration job fails, leave the API stopped, fix the reported role, connectivity, or schema issue, and rerun the failed job. A repeated migration at head is safe. If recovery needs a prior database state, restore the verified backup to a separate cluster and verify it before switching over. Avoid discarding the original volume.

## Verify

```bash
python3 scripts/phase1_smoke.py
docker compose --env-file .env -f infra/compose.yaml run --rm --no-deps migrate \
  alembic -c alembic.ini current
```

Expect three HTTP checks to pass and `0002_identity_foundation (head)`. Use the smoke script's `--base-url` for a nondefault nginx port. To check privileges with the API's own connection, run this read-only probe. It prints no credential values.

```bash
docker compose --env-file .env -f infra/compose.yaml exec -T api python - <<'PY'
from sqlalchemy import text
from aq_uai_api.db.session import get_engine

with get_engine().connect() as db:
    row = db.execute(text("""
        SELECT current_user,
               has_schema_privilege(current_user, 'public', 'CREATE'),
               has_table_privilege(current_user, 'public.audit_events', 'INSERT'),
               has_table_privilege(current_user, 'public.audit_events', 'UPDATE'),
               has_table_privilege(current_user, 'public.audit_events', 'DELETE'),
               has_table_privilege(current_user, 'public.audit_events', 'TRUNCATE'),
               has_table_privilege(current_user, 'public.roles', 'UPDATE')
    """)).one()
assert tuple(row) == ("aq_uai_runtime", False, True, False, False, False, False)
print("PASS: restricted runtime login and audit privileges")
PY
```

For a disposable Compose project with synthetic passwords, use `scripts/verify_wp2_compose.py --env-file <test-env> --project-name <test-project> --live` after starting that project. Assign distinct loopback ports and use a separate project name so the test uses its own volume. The probe checks the rendered configuration, effective API and migration environments, and the users authenticated by PostgreSQL. Without `--live`, it checks the rendered configuration only.

## Service transaction and audit conventions

Use the request session dependency for reads. Closing a read session rolls back any pending work. A mutation service opens a fresh `write_transaction()` before its first query. It authorizes the target and performs the write and audit insert in that same session. Pass the active session to helpers. This avoids SQLAlchemy *autobegin*, which starts a transaction on the first database operation and can conflict with a later explicit begin. Leaving the context commits before returning success. Any failure rolls back the work. Mutation services explicitly update `updated_at` when changing rows with that column.

Example for a future service with already verified actor, institution, and target UUIDs. WP2's restricted runtime grants allow the audit insert. The package introducing this directory mutation must also grant the necessary unit update.

```python
from uuid import UUID

from aq_uai_api.db.audit import ActiveChange, AuditAction, write_audit_event
from aq_uai_api.db.identity import Unit
from aq_uai_api.db.session import write_transaction

# IDs from a synthetic fixture. The production service obtains these from
# verified database records and the authenticated actor.
verified_institution_id = UUID("11111111-1111-4111-8111-111111111111")
verified_actor_id = UUID("22222222-2222-4222-8222-222222222222")
verified_unit_id = UUID("33333333-3333-4333-8333-333333333333")

with write_transaction() as db:
    # Future service authorizes this exact unit within the same transaction.
    unit = db.get(Unit, verified_unit_id)
    before = unit.active
    unit.active = False
    write_audit_event(
        db,
        action=AuditAction.UNIT_STATE_CHANGED,
        request_id=UUID(request.state.request_id),
        institution_id=verified_institution_id,
        actor_id=verified_actor_id,
        target_id=unit.id,
        changes=ActiveChange(before=before, after=False),
    )
```

Each audit action determines target type, outcome, and accepted fields. Payload fields are booleans or enumerated states. Extend the action catalog with a typed payload when adding another operation. Keep passwords, hashes, tokens, headers, connection strings, and request bodies out of it. For an unverified rejected login, WP3 can open a separate `write_transaction()` and call `write_audit_event(db, action=AuditAction.AUTH_LOGIN_REJECTED, request_id=UUID(request.state.request_id))`. It records no actor, target ID, or change payload.

Use the same write boundary for future RBAC assignments and directory changes. MDL can record configuration changes and audits together. External model connection tests must occur outside an open database transaction. QTA and CRT must keep each successful state or ledger change and its audit event atomic. Their product rules and business records are separate from the operational audit infrastructure.

### Errors and readiness

The API generates a fresh UUID for every request and returns it in `X-Request-ID`. Application error envelopes contain stable `code`, `message`, and `request_id`. Validation input, SQL arguments, and driver diagnostics are omitted. Expected uniqueness conflicts convert to `409`. Other failures use a generic safe message and a log entry with the error code and request ID. SQLAlchemy hides parameters on both engines. Offline Alembic uses the PostgreSQL dialect without reading connection settings. Migration CLI failures use safe messages. Keep sensitive values out of migration scripts and out of URL paths and query strings, including those processed by proxies.

Phase 1 diagnostics retain their response bodies. Readiness checks that the database has exactly the version this API release requires and that its Phase 1 metadata marker is present. Change `REQUIRED_SCHEMA_REVISION` with each compatible API schema release. The PostgreSQL suite compares the constant with the Alembic head.
