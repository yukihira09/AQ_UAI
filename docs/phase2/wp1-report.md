# Phase 2 WP1 implementation and verification

**Assessment:** WP1 schema and migration are implemented. The acceptance checks passed on disposable PostgreSQL 18.7. The installed development database and volume were left untouched. WP2 awaits human review.

## Changes and file inventory

| File | Change |
|---|---|
| [plan.md](plan.md) | Replaced the proposal with the approved seven-gate specification. Institutional identity choices are provisional. |
| [ADR-0002](../architecture/ADR-0002-phase2-shared-foundation.md) | Recorded the approved architecture and trade-offs. |
| [schema.md](schema.md) | Documented the table model, constraint boundaries, and service responsibilities. |
| [identity.py](../../apps/api/src/aq_uai_api/db/identity.py) | Added the 14 SQLAlchemy table mappings. |
| [env.py](../../apps/api/migrations/env.py) | Registered the new models in Alembic's metadata. |
| [0002_identity_foundation.py](../../apps/api/migrations/versions/0002_identity_foundation.py) | Added the schema and shared role catalog after `0001_phase1_metadata`. |
| [test_wp1_schema.py](../../apps/api/tests/integration/test_wp1_schema.py) | Added live PostgreSQL migration and constraint tests. |
| [wp1-report.md](wp1-report.md) | Recorded implementation, evidence, and local rollout steps. |

## Database and role catalog

The 14 new tables are `institutions`, `units`, `users`, `user_credentials`, `account_groups`, `group_memberships`, `roles`, `permissions`, `role_permissions`, `user_role_assignments`, `group_role_assignments`, `auth_sessions`, `auth_throttle_buckets`, and `audit_events`. The [schema guide](schema.md) explains their relationships. The migration seeds only three roles, five permissions, and eight role–permission links.

| Seeded role | Permission codes | Scope |
|---|---|---|
| `FOUNDATION_ADMIN` | `directory.read`, `directory.profile.update`, `directory.manage`, `authorization.manage`, `audit.read` | Direct `GLOBAL` only |
| `DIRECTORY_READER` | `directory.read` | `GLOBAL` or `UNIT` |
| `UNIT_DIRECTORY_MANAGER` | `directory.read`, `directory.profile.update` | `UNIT` only |

PostgreSQL enforces same-institution references, canonical username and code uniqueness, membership and grant uniqueness, scope shape, seeded role scope restrictions, session digest length and finite chronology, and retention of referenced audit actors. WP2–WP5 own credential handling, audit write protection, active state, group-kind immutability and eligibility, last-admin protection, and authorization. Raw SQL can change a group's kind or insert a limited role grant on an ineligible group. WP4 and WP5 must reject these grants and check eligibility on every use.

**Migration decision:** `0002_identity_foundation` is forward-only. Its downgrade stops before any changes because reversing it would delete identity and audit data. Restore a verified pre-WP1 backup to a separate database if recovery requires returning to Phase 1.

## Verification

Docker daemon access was denied. Verification used the host's installed PostgreSQL 18.7 in a separate cluster under `/tmp` and a temporary Python 3.12.16 virtual environment with the repository's declared dependencies. The cluster listened on a private Unix socket. No system-wide Python installation, development database credentials, Compose volume resets, or changes to the installed stack were required.

The following commands show the exact disposable test settings for the final suite. An earlier run used `aq_wp1_baseline` and `upgrade 0001_phase1_metadata` to establish the Phase 1 schema before generating the WP1 revision.

```bash
export PYTHONPATH=apps/api/src PYTHONDONTWRITEBYTECODE=1 AQ_UAI_ENVIRONMENT=test
export AQ_UAI_DB_HOST= PGHOST=/tmp/aq-uai-wp1.Idb9IyUL AQ_UAI_DB_PORT=56432
export AQ_UAI_DB_NAME=aq_wp1_verified AQ_UAI_DB_USER=huydev AQ_UAI_DB_PASSWORD=
export AQ_UAI_RUN_DB_TESTS=1
/usr/lib/postgresql/18/bin/createdb -h /tmp/aq-uai-wp1.Idb9IyUL -p 56432 aq_wp1_verified
/tmp/aq-uai-wp1.Idb9IyUL/venv/bin/python -m alembic -c apps/api/alembic.ini upgrade head
/tmp/aq-uai-wp1.Idb9IyUL/venv/bin/python -m pytest -p no:cacheprovider -q --tb=short apps/api/tests
```

- Before adding the schema, the focused test `apps/api/tests/integration/test_wp1_schema.py::test_clean_database_reaches_wp1_and_matches_orm` failed as expected. PostgreSQL reported revision `0001_phase1_metadata` while the test required `0002_identity_foundation`. An earlier setup attempt could not reach the private socket through Alembic's rendered URL. Using libpq's `PGHOST` with an empty application host resolved the setup issue without changing application connection code.
- The review added independent tests for each membership foreign key and global username uniqueness across institutions. A focused run with `-k infinite` failed on all three new session regression cases before the finite-timestamp constraints were added.
- The final suite passed **42 tests**, with **0 failures and 0 skips**. This includes 33 WP1 checks and 9 Phase 1 checks. The suite emitted one upstream Starlette deprecation warning for its existing `httpx`-based test client. An earlier sandboxed unit-only run was interrupted after two tests. The full run included those tests.
- The live migration tests upgraded a clean database and a Phase 1 database with an extra metadata row. They checked the exact revision and a repeated upgrade. `alembic check` reported no pending operations under its configured comparisons. Separate live PostgreSQL writes verified the check constraints. The Phase 1 PostgreSQL test exercised readiness and database-backed system info.
- `/tmp/aq-uai-wp1.Idb9IyUL/venv/bin/python -m alembic -c apps/api/alembic.ini upgrade head --sql` generated PostgreSQL SQL successfully.
- `/tmp/aq-uai-wp1.Idb9IyUL/venv/bin/ruff check --no-cache apps/api/src apps/api/tests apps/api/migrations/env.py apps/api/migrations/versions/0002_identity_foundation.py` passed.
- `/usr/bin/python3 -B scripts/verify_frontend_assets.py` confirmed all 10 links and script order. `/usr/bin/python3 -B scripts/verify_frontend_baseline.py` matched all 14 original assets. `for f in apps/web/shared/*.js apps/web/module*/*.js; do node --check "$f" || exit; done` passed for all six scripts.
- `git diff --exit-code -- apps/api/migrations/versions/0001_phase1_metadata.py apps/web infra` found no WP1 changes to those paths. The Phase 1 migration also matched its staged Git blob. `git diff --check` passed.

The Docker Compose and nginx smoke path remains unverified from this session. Phase 1 diagnostics passed through FastAPI against actual PostgreSQL. The module FRDs still require their own implementation and acceptance evidence.

## Apply to the existing local database after human approval

From the repository root, with the existing development database running, create a private backup. Compose supplies its existing environment internally. Verify the dump's table-of-contents before migrating.

```bash
umask 077
wp1_backup="$(mktemp "$HOME/aq-uai-pre-wp1.XXXXXXXX.dump")"
docker compose --env-file .env -f infra/compose.yaml exec -T db sh -c \
  'pg_dump --format=custom --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' > "$wp1_backup"
docker compose --env-file .env -f infra/compose.yaml exec -T db pg_restore --list < "$wp1_backup"
```

Proceed only after both backup commands succeed. For a database with valuable data, verify a restore to a separate disposable database first. Build and run the existing migration service against the current database, then check the installed revision.

```bash
docker compose --env-file .env -f infra/compose.yaml run --rm --no-deps --build migrate
docker compose --env-file .env -f infra/compose.yaml run --rm --no-deps migrate \
  alembic -c alembic.ini current
python3 scripts/phase1_smoke.py
```

Expect `0002_identity_foundation (head)` and all three smoke checks to pass. Use the script's `--base-url` if the web port differs from the default. Keep the backup and existing volume. If migration fails, report the error and inspect the revision before retrying.
