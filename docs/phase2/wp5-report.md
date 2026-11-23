# WP5 protected directory implementation report

**Acceptance assessment.** WP5 implementation and disposable PostgreSQL verification are complete. All 33 directory operations are available under `/api/v1`. The API end-to-end, security, migration, and concurrency suite passed. WP5 awaits independent acceptance. WP6 and live rollout remain separate decisions. [Complete endpoint and permission matrix, schemas, lifecycle rules, and WP6 examples](wp5-api.md)

## Implementation and review decisions

- The directory uses the existing schema, FastAPI routing, WP3 sessions, and WP4 permissions. Institution and permission scopes come from the authenticated actor. SQL queries apply that scope before reading a record or computing filtered counts. Stable ordering and bounded pages support the future interface.
- Central administrators can create pending accounts or provision initial temporary credentials in the create request. Activation can add an initial credential, or restore access to an already provisioned account with its existing password. Disablement and username changes revoke all sessions. Transfer preserves the account UUID, memberships, and the scope attached to existing grants. Unit deactivation is blocked by active users or any stored unit-scoped assignment.
- A group's persisted kind determines management authority. The group's code and kind are fixed. The API preserves a single membership record per user and group, records real state transitions, and permits repeated safe removals. Group deactivation removes inherited authority while preserving links. Role assignments are validated against the subject, role matrix, and active same-institution units and groups. Direct grants to pending or disabled accounts remain ineffective until eligibility.
- Writes use the WP4 lock order and recheck authority in their own transactions. Last-admin checks flush the proposed state before querying for another usable direct global administrator. Session revocation rolls back if that check fails. Group membership chooses the target account's lock hint using the visible group's immutable kind. The implementation rejects the attempt if a concurrently created group appears after an absent hint, because the target account was never coordinated. Subsequent attempts can resolve the new group normally.
- Audit events commit in the same transaction as the state change. A membership event uses `target_type = group_membership` and the group UUID in `target_id`, and carries `user_id`, `before`, and `after` in typed changes. The reader handles historical two-state membership events. Typed snapshots can preserve older blank names and unit codes when an administrator repairs them. New event time comes from the database clock at insertion.
- Column-specific grants for directory writes preserve immutable UUIDs, tenant keys, group kinds, and historical rows. Assigned grants can be inserted and explicitly deleted. PostgreSQL restricts raw SQL to the granted operations. The service enforces per-actor authority, state invariants, and the audit pairing. Runtime SQL within its privileges can bypass these service checks. [Privileges and rollout](wp5-api.md#database-access-and-rollout)

The full endpoint set, the existing Alembic head, and the approved seven-package sequence are retained. This implementation chose `409` for repeated explicit lifecycle transitions, `200` and `204` for unchanged membership additions and removals, and group codes that stay fixed after creation. No new schema revision was needed.

## WP5 file inventory

| Change | Files |
| --- | --- |
| New routes | `apps/api/src/aq_uai_api/api/v1/directory.py` |
| New directory package | `apps/api/src/aq_uai_api/directory/__init__.py`, `apps/api/src/aq_uai_api/directory/schemas.py`, `apps/api/src/aq_uai_api/directory/queries.py`, `apps/api/src/aq_uai_api/directory/service.py` |
| Modified application and database code | `apps/api/src/aq_uai_api/main.py`, `apps/api/src/aq_uai_api/api/errors.py`, `apps/api/src/aq_uai_api/db/audit.py`, `apps/api/src/aq_uai_api/db/provision.py` |
| New tests | `apps/api/tests/unit/test_wp5_contract.py`, `apps/api/tests/integration/test_wp5_directory.py` |
| Modified regression tests | `apps/api/tests/unit/test_health.py`, `apps/api/tests/integration/test_wp3_auth.py`, `apps/api/tests/integration/test_wp4_policy.py` |
| New documentation | `docs/phase2/wp5-api.md`, `docs/phase2/wp5-report.md` |
| Modified milestone and architecture documentation | `AGENTS.md`, `README.md`, `docs/phase2/plan.md`, `docs/phase2/schema.md`, `docs/architecture/ADR-0002-phase2-shared-foundation.md` |

The pre-existing WP4 source and its policy/report documents were carried forward. WP5 modified its integration test for deliberately changed database permissions. The prior `GET /users` absence check now expects `401`. The WP3 and WP4 raw SQL denials now test immutable tenant, membership-key, and assignment fields after the corresponding inserts and explicit lifecycle writes became valid. The test suite retains checks for the authorization catalog, privileged roles, historical audit records, schema ownership, and authentication data boundaries.

## Verification

Executed from the repository root with Python 3.12.16, standalone PostgreSQL 18.7 on a private Unix socket, and Node 21.4.0. The integration fixtures provisioned separate disposable databases and made API requests as the restricted runtime role. The commands below use only the temporary test configuration. The bootstrap password was synthetic.

```sh
wp5_python=/tmp/aq-uai-wp1.Idb9IyUL/venv/bin/python
wp5_socket=/tmp/aq-uai-wp5.k0376Xqx
read -r wp5_test_password < "$wp5_socket/test-password"

wp5_run() {
  env PYTHONPATH=apps/api/src PYTHONDONTWRITEBYTECODE=1 \
    AQ_UAI_ENVIRONMENT=test AQ_UAI_DB_HOST="$wp5_socket" AQ_UAI_DB_PORT=56437 \
    AQ_UAI_DB_NAME=aq_wp5_suite AQ_UAI_DB_USER=huydev \
    AQ_UAI_DB_PASSWORD="$wp5_test_password" AQ_UAI_RUN_DB_TESTS=1 "$wp5_python" "$@"
}

wp5_run -m pytest -p no:cacheprovider -q --tb=short apps/api/tests
wp5_run -m alembic -c apps/api/alembic.ini check
/tmp/aq-uai-wp1.Idb9IyUL/venv/bin/ruff check --no-cache \
  apps/api/src apps/api/tests apps/api/migrations/env.py scripts/verify_wp2_compose.py
/usr/bin/python3 -B scripts/verify_frontend_assets.py
node --test scripts/test_sidebar_navigation.cjs
for source in apps/web/shared/*.js apps/web/module*/*.js; do
  node --check "$source" || exit
done
git diff --check
git diff --exit-code HEAD -- apps/web docs/prototype apps/api/migrations/versions infra
```

| Check | Result |
| --- | --- |
| Full Phase 1 and WP1–WP5 API suite | **119 passed, 0 failed, 0 skipped** in 164.20 seconds. Four dependency deprecation warnings cover Starlette's TestClient and Alembic configuration. |
| Alembic consistency | No new upgrade operations detected. The migrations remain `0001_phase1_metadata` and `0002_identity_foundation`. |
| Ruff and diff checks | Passed. The migration files, frontend assets and historical manifests, and infrastructure match the pre-WP5 tracked source. |
| Frontend asset and sidebar checks | All 10 required assets present with the same script order. Sidebar regression script passed with 1 test and no failures or skips. Shared and module JavaScript passed syntax checks. |

An in-process OpenAPI comparison also matched all 33 documented operations and success statuses. The local Phase 2 documentation links resolved.

### Important outcomes

- New users signed in with temporary credentials and were denied directory access until password change and reauthentication. Pending users could not sign in before activation. Fresh clients saw persisted users, units, and grants. Username changes and disablement invalidated prior sessions, and reactivation never restored those sessions.
- Tests rejected forged body fields, unauthorized scopes, cross-institution references, duplicate identifiers, invalid group kinds or assignments, and incorrect or missing Origin and CSRF proof. Invisible and missing targets returned the same error code and message. Counts excluded hidden rows. Expired sessions returned `401`.
- A unit transfer preserved the original grant scope. Unit deactivation failed first with an active user, then with a retained grant after transfer. Ordinary membership and AI-specialist membership never acquired role authority. Reactivated memberships reused their original stored link and resulting audit history.
- In each simultaneous last-admin scenario, one operation succeeded and the other returned `409`: two disables, two grant removals, and a disable competing with a grant removal. The persisted check found one remaining usable administrator. A pending, disabled, or unprovisioned account did not satisfy the rule. An active administrator with a temporary credential could complete the normal password-change flow.
- Real database transactions showed a waiting profile write denied after grant revocation, and WP3 login and operator recovery denied after waiting for a WP5 disablement. The concurrent group creation test confirmed that an attempt lacking an account lock creates no membership.
- Revoking the runtime audit INSERT privilege caused unit changes, user creation with credentials, disablement with session revocation, group membership changes, and grant creation to roll back. Reprovisioning restored the intended access while raw SQL remained unable to change immutable or historical records. Institutional audit APIs excluded cross-institution and unattributed events and projected stored change payloads through their allowlists.

## Remaining gates

WP6 can consume the documented endpoints through the admin origin after WP5 acceptance and explicit approval. The browser interface, Docker rollout, actual environment configuration, manual website checks, and GitHub synchronization were outside this verification. Before any live deployment, reapply runtime privileges even though Alembic stays at `0002_identity_foundation`.

The directory is a shared prerequisite for MDL permissions, QTA group entitlement, and CRT recipient and unit scoping. It introduces no provider configuration, quota or credit accounting, token-to-credit conversion, or historical ledger visibility policy. The three module FRDs still need their own verification. [Open institution and module decisions](plan.md#frd-requirements-and-product-owner-decisions)
