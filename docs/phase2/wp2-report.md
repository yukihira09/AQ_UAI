# Phase 2 WP2 implementation and verification

**Assessment:** WP2 is implemented and ready for independent review. The standalone PostgreSQL acceptance suite and rendered Compose configuration checks passed. Effective container environments and the Compose/nginx smoke path remain open because Docker daemon access was denied in this session.

## Implementation

Compose now runs a short-lived privileged provisioning job, followed by migrations as `aq_uai_schema` and application requests as `aq_uai_runtime`. Each service receives an explicit set of environment variables. The database's original owner keeps maintenance authority. The migration login owns the application schema, current tables, and indexes. Runtime has schema usage and specific table reads, including Phase 1 metadata, the Alembic revision, and authorization data. Its only write privilege is audit insertion. It lacks default access to future tables and routines. See the [effective privilege matrix, credential map, backup-first rollout, and recovery steps](wp2-operations.md).

Fresh provisioning creates the logins before Alembic creates tables. Existing Phase 1 and WP1 tables transfer to the schema owner in place. Repeating provisioning and migration reapplies the same effective grants and preserves data. A role name assigned to another installation, unexpected role memberships, or unmanaged objects that would require ownership changes cause provisioning to stop for review.

The [service examples](wp2-operations.md#service-transaction-and-audit-conventions) show a typed audit insert inside `write_transaction()` and a rejected sign-in event with an absent actor. An audit error rolls back the business write. A business error rolls back the audit event. Read dependency sessions close without committing. Future writers must set `updated_at` explicitly.

The API returns a server-generated UUID in `X-Request-ID`. Phase 2 errors include `code`, `message`, and `request_id`. Logs correlate failures by that ID and omit exception text and submitted values. Readiness requires the exact supported revision and the Phase 1 metadata marker. Its existing `503` body is preserved. The two original Alembic revisions are preserved. WP2 adds no schema revision.

## Changed files

| File | Change |
|---|---|
| `.env.example` | Added two role password placeholders. |
| `.github/workflows/ci.yml` | Added rendered Compose credential checks and retained PostgreSQL test coverage. |
| `README.md` | Updated setup and added the backup-first transition link. |
| `infra/compose.yaml` | Added provisioning, scoped environment variables, migration ordering, and safe API logging flags. |
| `apps/api/Dockerfile` | Disabled raw request access logging for the API's default command. |
| `apps/api/migrations/env.py` | Preserved ORM registration and redacted migration output paths. |
| `apps/api/src/aq_uai_api/api/errors.py` | Added error responses and request correlation. |
| `apps/api/src/aq_uai_api/api/v1/system.py` | Added schema-aware readiness and preserved diagnostic bodies. |
| `apps/api/src/aq_uai_api/core/config.py` | Defaulted the connection username to the runtime role. |
| `apps/api/src/aq_uai_api/db/audit.py` | Added typed audit payloads and a transaction-bound writer. |
| `apps/api/src/aq_uai_api/db/provision.py` | Added repeatable credential, ownership, and privilege provisioning. |
| `apps/api/src/aq_uai_api/db/schema.py` | Added the required revision constant. |
| `apps/api/src/aq_uai_api/db/session.py` | Hid engine parameters and added an explicit write context. |
| `apps/api/src/aq_uai_api/main.py` | Installed shared request middleware and handlers. |
| `apps/api/tests/integration/test_wp2_database.py` | Added real privilege, transition, transaction, and readiness tests. |
| `apps/api/tests/unit/test_health.py` | Updated the Phase 1 readiness test double for revision queries. |
| `apps/api/tests/unit/test_wp2_audit.py` | Added audit payload and transaction-boundary tests. |
| `apps/api/tests/unit/test_wp2_errors.py` | Added status, redaction, conflict, and request ID tests. |
| `docs/architecture/ADR-0002-phase2-shared-foundation.md` | Recorded the three-role and credential boundary. |
| `docs/phase2/plan.md` | Recorded WP1 acceptance and WP2 authorization. |
| `docs/phase2/schema.md` | Linked the implemented WP2 boundaries. |
| `docs/phase2/wp2-operations.md` | Added privilege, rollout, recovery, and service usage guidance. |
| `docs/phase2/wp2-report.md` | Recorded implementation and verification results. |
| `docs/setup/PHASE_0_1.md` | Directed current users from the historical guide to the WP2 setup. |
| `scripts/dev-up.sh` | Updated setup hints and placeholder checks for three credentials. |
| `scripts/verify_wp2_compose.py` | Added redacted Compose configuration and optional live probes. |

## Verification commands and evidence

Verification used Python 3.12.16 and PostgreSQL 18.7. The PostgreSQL cluster and all databases were disposable and listened on a private Unix socket. The commands below use the reported test socket. The synthetic bootstrap password came from a private fixture file.

**Final suite:** 59 passed, 0 failed, 0 skipped. This includes 42 Phase 1 and WP1 tests and 17 WP2 tests. The run emitted four dependency deprecation warnings about Starlette's test client and Alembic's legacy path parsing. The initial request-redaction test failed before middleware was implemented. A later legacy-procedure regression exposed a grant reconciliation step that the migration owner lacked authority to run. Moving legacy routine revocation to the bootstrap transaction resolved it.

```bash
export PYTHONPATH=apps/api/src PYTHONDONTWRITEBYTECODE=1 AQ_UAI_ENVIRONMENT=test
export AQ_UAI_DB_HOST=/tmp/aq-uai-wp2.sMphzTI0 AQ_UAI_DB_PORT=56433
export AQ_UAI_DB_NAME=aq_wp2_suite AQ_UAI_DB_USER=huydev
read -r AQ_UAI_DB_PASSWORD < /tmp/aq-uai-wp2.sMphzTI0/test-password
export AQ_UAI_DB_PASSWORD AQ_UAI_RUN_DB_TESTS=1
wp2_python=/tmp/aq-uai-wp1.Idb9IyUL/venv/bin/python
"$wp2_python" -m alembic -c apps/api/alembic.ini upgrade head
"$wp2_python" -m pytest -p no:cacheprovider -q --tb=short apps/api/tests
"$wp2_python" -m alembic -c apps/api/alembic.ini upgrade head --sql > /tmp/aq-uai-wp2.sMphzTI0/schema.sql
/usr/bin/python3 -B scripts/verify_wp2_compose.py --env-file /tmp/aq-uai-wp2.sMphzTI0/compose-test.env --project-name aq-wp2-verify
/usr/bin/python3 -B scripts/verify_wp2_compose.py --env-file .env.example --project-name aq-wp2-ci
/usr/bin/python3 -B scripts/verify_frontend_assets.py
/usr/bin/python3 -B scripts/verify_frontend_baseline.py
for f in apps/web/shared/*.js apps/web/module*/*.js; do node --check "$f" || exit; done
/tmp/aq-uai-wp1.Idb9IyUL/venv/bin/ruff check --no-cache apps/api/src apps/api/tests apps/api/migrations/env.py scripts/verify_wp2_compose.py
bash -n scripts/dev-up.sh
git diff --check
```

- **Standalone PostgreSQL.** The suite used separate administrative and restricted connections. It verified fresh provisioning, transitions from Phase 1 and populated WP1 databases, repetition, identity and metadata preservation, catalog protection, append-only audit, and expected rollback. It verified separate migration and runtime logins and rejected each role's password for the other role. Alembic consistency checks passed as the schema owner.
- **Standalone service commands.** On the separate `aq_wp2_cli` database, `python -m aq_uai_api.db.provision prepare --config apps/api/alembic.ini` and `python -m aq_uai_api.db.provision migrate --config apps/api/alembic.ini` ran with their respective synthetic credentials. `python -m uvicorn aq_uai_api.main:app --host 127.0.0.1 --port 58082 --no-access-log` ran with the restricted runtime account. `python scripts/phase1_smoke.py --base-url http://127.0.0.1:58082` passed all three checks against Uvicorn directly. The smoke script's final summary mentions nginx. This run used direct HTTP.
- **Compose configuration.** Rendered synthetic configuration and checked the exact service environment keys and distinct credential mapping without printing values. The optional `--live` script is available for a disposable Compose project.
- **Docker and nginx.** Daemon access was denied on both attempts. Live Compose start-up, effective container environment probes, and the nginx smoke path remain unverified.
- **Regression.** The original 0001 and 0002 migration file hashes matched their starting values. The asset and script checks verified 10 links, 14 original files, and six JavaScript files. Phase 1 diagnostics were exercised against PostgreSQL.

WP2 ran without editing the actual dotenv file, development database, database roles, Docker volume, or frontend assets. Module FRD acceptance and later authentication, authorization, and management services remain independently gated.
