# WP4 implementation and verification

**Assessment:** WP4 is implemented and ready for independent source review. Standalone PostgreSQL acceptance checks passed. WP5 requires separate approval.

## Implementation

WP4 adds the reusable authorization layer for the existing authenticated API. `read_authority` checks the WP3 session and resolves the current persisted role catalog and applicable assignments. `ActorAuthority` keeps provenance as typed `EffectiveGrant` values and derives a `PermissionScope` for one permission at a time. There is no cross-request permission cache or change to the `/auth/me` response.

Direct assignments are tied to the actor's institution. Inheritance requires an active membership and an active same-institution authorization group. SYSTEM and AI_SPECIALIST groups contribute no permission. FOUNDATION_ADMIN is direct GLOBAL only. DIRECTORY_READER permits GLOBAL or UNIT. UNIT_DIRECTORY_MANAGER permits UNIT only. Unknown role and permission codes fail closed. Central management, delegation, and audit permissions require a direct GLOBAL grant. Permission membership itself comes from PostgreSQL.

Unit scope covers the one specified active unit. It confers no authority from the user's home unit and no central access. GLOBAL covers the actor's institution, including historical directory records. Permission-specific filters apply institution and unit in SQL before detail retrieval, search, pagination, and totals. Pending and disabled recipients remain visible to authorized directory readers. An invisible or nonexistent target has the same `404`. A missing operation permission or a visible resource outside the operation's scope has `403`.

Profile payloads accept only display name. Central directory administration covers scope, identity, and account-state changes. Only central authorization administrators may manage authorization groups or validate role assignments. The assignment validator checks persisted subjects, group kind and activity, tenant, role and scope, and the unit's activity. Directory operations, grant changes, and last-admin protection remain WP5 work.

For writes, `require_authenticated_write` checks a valid unrestricted session, Origin, and exactly one session-bound CSRF header. WP3 password change and logout retain their restricted-session behavior. The service must call `resolve_write_authority` once at the start of an explicit outer write transaction before applying operation and resource checks. This takes an institution lock and sorted WP3 account locks, revalidates browser proof, and evaluates committed authority. Related account lock hints are filtered in SQL by the operation's permission scope before waiting. Scope-stable writes take a shared institution lock. Changes to grants, membership, eligibility, or organizational scope take the exclusive lock from the start. The guard rejects calls from a savepoint or a second call in the same transaction.

A request beginning after committed revocation sees current state. Already-started reads may finish with an earlier scope. Protected writes serialize with cooperating revokers. A revoker holding the relevant lock first forces the waiting mutation to recheck committed state. A writer holding its locks first may complete before a revocation. Out-of-band SQL that ignores the protocol has no in-flight guarantee. WP5 must also coordinate disablement with WP3 account locking and session revocation.

The [policy guide](wp4-policy.md) contains the complete interface reference, lock order, and synthetic examples of central checks, profile authorization, SQL filters, and transactional mutation revalidation. The guard introduces no new database grants or schema changes. Both historical revisions, the runtime privilege provisioning, infrastructure, and the five previously approved frontend changes are preserved. The required revision remains `0002_identity_foundation`.

## Exact file inventory

| Change | Files |
|---|---|
| Added authorization code | `apps/api/src/aq_uai_api/authorization/__init__.py`, `policy.py`, `dependencies.py`, and `writes.py` in the same directory |
| Added authentication guard | `apps/api/src/aq_uai_api/auth/write.py` |
| Modified WP3 integration | `apps/api/src/aq_uai_api/auth/service.py`, `apps/api/src/aq_uai_api/api/v1/auth.py` |
| Added tests | `apps/api/tests/unit/test_wp4_scope.py`, `apps/api/tests/integration/test_wp4_policy.py` |
| Added documentation | `docs/phase2/wp4-policy.md`, `docs/phase2/wp4-report.md` |
| Updated documentation | `AGENTS.md`, `README.md`, `docs/architecture/ADR-0002-phase2-shared-foundation.md`, `docs/phase2/plan.md`, `docs/phase2/schema.md` |

## Verification

Verification used Python 3.12.16 and standalone PostgreSQL 18.7 over a private scratch socket. The tests used disposable databases and roles. The bootstrap password was synthetic and loaded from the private fixture file.

**Final suite:** 100 passed, 0 failed, 0 skipped. It includes 72 Phase 1 and WP1–WP3 regressions and 28 WP4 tests. Four upstream Starlette and Alembic deprecation warnings remain.

```bash
export PYTHONPATH=apps/api/src PYTHONDONTWRITEBYTECODE=1 AQ_UAI_ENVIRONMENT=test
export AQ_UAI_DB_HOST=/tmp/aq-uai-wp4.xyaFBGdK AQ_UAI_DB_PORT=56436
export AQ_UAI_DB_NAME=aq_wp4_suite AQ_UAI_DB_USER=huydev
read -r AQ_UAI_DB_PASSWORD < /tmp/aq-uai-wp4.xyaFBGdK/test-password
export AQ_UAI_DB_PASSWORD AQ_UAI_RUN_DB_TESTS=1
wp4_python=/tmp/aq-uai-wp1.Idb9IyUL/venv/bin/python
"$wp4_python" -m alembic -c apps/api/alembic.ini upgrade head
"$wp4_python" -m alembic -c apps/api/alembic.ini check
"$wp4_python" -m pytest -p no:cacheprovider -q --tb=short apps/api/tests
/tmp/aq-uai-wp1.Idb9IyUL/venv/bin/ruff check --no-cache apps/api/src apps/api/tests apps/api/migrations/env.py scripts/verify_wp2_compose.py
/usr/bin/python3 -B scripts/verify_frontend_assets.py
node scripts/test_sidebar_navigation.cjs
for f in apps/web/shared/*.js apps/web/module*/*.js; do node --check "$f" || exit; done
git diff --exit-code HEAD -- apps/web docs/prototype/frontend_source_manifest.json docs/prototype/original_archive_manifest.json apps/api/migrations/versions apps/api/src/aq_uai_api/db/provision.py infra
git diff --check
```

- The new policy unit tests first failed because the policy module did not exist. The initial restricted-role WP4 integration run passed 22 tests. An intermediate full run passed 98 tests.
- The PostgreSQL tests prove that a GLOBAL reader plus Unit A editor can read Unit B and receives `403` editing Unit B. Unit-only readers get the same `404` for invisible and missing objects. Exact-unit unions, institution boundaries, history visibility, and scoped result counts were exercised with actual queries.
- Active authorization-group inheritance succeeds. Inactive memberships, inactive groups, SYSTEM, AI_SPECIALIST, unknown permissions, and group-derived central rights fail closed. The suite tested the structural group-admin rejection and separately tested evaluator behavior with that constraint removed in a fixture database created and dropped solely for the test.
- Request tests reject invalid or restricted sessions, missing, duplicated, invalid, and cross-session CSRF, and an incorrect Origin. Revocation tests cover direct grants, memberships, groups, group-role assignments, user state, and sessions. Transaction tests cover revocation after HTTP precheck and waiting on both institution and WP3 account locks. The scope-filtered lock test confirms the guard skips out-of-scope target account locks.
- The real runtime role could query authorization data. It could not write the role catalog, insert assignments, change group authority, rewrite audit rows, or assume the migration role. WP1 tests covered schema and upgrade integrity. WP2 and WP3 regression tests covered provisioning, audit rollback, readiness, session and password behavior, and login versus committed account invalidation.
- Alembic reported no pending upgrade operations. Frontend asset resolution, JavaScript syntax, the sidebar regression, lint, and whitespace checks passed. The baseline diff check verified that WP4 did not alter the frontend, historical manifests, migrations, provisioning, or infrastructure.

## FRDs and remaining integration

FR-MDL-001 can use future institution-wide edit-equivalent authorization. FR-QTA-001 can use separate read and management scopes while FR-QTA-020, FR-QTA-022, and FR-QTA-030 retain their group and additive quota rules. FR-CRT-001, FR-CRT-010, and FR-CRT-013 can use independent permissions and exact recipient scope. FR-CRT-030's append-only ledger and transaction-time attribution are module responsibilities. No module permission or accounting policy was seeded.

WP5 must wire the policy into directory queries and mutation transactions, add the necessary narrowly scoped database grants, define typed audit and membership identifiers, enforce the last-admin rule under the exclusive institution lock, and enforce centralized transfer and account-state policy. The approved design remains in place. Defensive implementation decisions are direct GLOBAL central permissions and the shared/exclusive institution lock coordination with WP3 account locks.

Live Compose verification, actual deployment, and manual browser testing were deferred by instruction. GitHub authentication remains a separate developer task. No actual dotenv settings, accounts, databases, Docker volumes, or remote repositories were accessed or changed by WP4.
