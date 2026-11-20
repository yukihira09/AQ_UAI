# Phase 2 WP3 implementation report

**Acceptance assessment:** The frontend correction, local Git tracking repair, and WP3 implementation are ready for independent review. Standalone PostgreSQL, nginx, and Chrome verification passed. The live Compose environment and actual local rollout remain pending. WP4 needs separate approval.

## Frontend correction

The sidebar initially opened based on the module hash. The navigation and QTA tab handlers also reset visibility, and Module 2 and Module 3 overrode parts of the shared shell. The initial state now depends on viewport width. Desktop opens the sidebar on every module. The hamburger is the only control that changes visibility within the page. A hash listener handles direct navigation and browser history. The modules share the Module 1 shell dimensions and styles, and wide content scrolls within the main content area.

The five intentionally changed assets are `apps/web/shared/core.js`, `apps/web/shared/actions.js`, `apps/web/shared/base.css`, `apps/web/module2/module2.css`, and `apps/web/module3/module3.css`. The original manifests, six-script order, module content, dialog behavior, Vietnamese labels, and synthetic data were preserved. The historical parity script now stops at the first authorized change. Chrome exercised desktop widths of 1440, 1024, and 800 pixels and mobile width 390. The three modules had matching sidebar width and topbar height at each desktop width and no document-level horizontal overflow. The browser also exercised tab switching, intentional collapse, back/forward, refresh, and mobile navigation. The durable Node regression runs in CI.

## Git status and first push

The directory was already a valid Git checkout. Local `main` and cached `origin/main` both pointed to `2539e1f`. There was no upstream configured for `main`: `git branch -vv` showed the commit without a tracking branch. The authorized local repair was `git branch --set-upstream-to=origin/main main`. Afterward `git status --short --branch` reported `main...origin/main` and `git rev-list --left-right --count HEAD...origin/main` returned `0 0` against the cached reference. The two existing commits and the original remote URL `https://github.com/yukihira09/AQ_UAI.git` were preserved. The existing staged changes and untracked files remain available for review.

An unauthenticated `git ls-remote` reached GitHub with network permission and failed with `could not read Username for 'https://github.com': terminal prompts disabled`. Current remote history, visibility, and write access could not be confirmed anonymously. Check repository visibility in GitHub before uploading company-related material. Authenticate through your approved HTTPS credential manager or GitHub CLI if installed. Keep tokens out of URLs and shell history.

From this repository after approval and authentication:

```bash
git fetch origin
git rev-list --left-right --count HEAD...origin/main
git status --short --branch
git add -- .gitignore .dockerignore .env.example .github AGENTS.md README.md apps docs infra scripts
git diff --cached --name-status
git diff --cached
git commit -m "Build AQ EduUAI Phase 2 through WP3 authentication"
git push -u origin main
```

If the right-hand count after the fetch is nonzero, review and integrate the remote commits before pushing. Review staged file names and contents before the commit and remove any material outside the approved GitHub scope. The root FRD copies are outside the explicit staging paths. `.env.example` is tracked. Real dotenv files, PostgreSQL credential files, compressed and uncompressed dump files, local environments, and caches match the ignore rules. No Git commit or push was performed.

## Authentication and operating decisions

The [operations guide](wp3-operations.md) provides endpoint contracts, credential lifecycle, CLI examples, effective grants by role, the WP5 locking contract, and the consolidated backup-first rollout and recovery steps.

- `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `POST /api/v1/auth/change-password`, and `POST /api/v1/auth/logout` use the WP2 error and request-ID contract. Login and the two authenticated writes return `204` on success. Current-user identification returns the minimal identity, temporary-password flag, and session-bound CSRF token. Auth responses use `no-store`.
- The operator CLI uses the existing schema-owner login and hidden interactive passwords. Bootstrap atomically creates the first institution, unit, active administrator, hash, direct global admin grant, and audit row. Reset preserves active identities and grants while setting a temporary credential and revoking sessions. Pending and disabled accounts are rejected. Active temporary-password accounts can use only the three restricted operations until password change.
- An Origin check precedes login. Sorted advisory locks serialize the login and address buckets. The account lock then precedes fresh credential and state reads. Password reset and authenticated credential changes take the same account lock. WP5 must acquire it before changing an account's state and revoke sessions before committing disablement. No user-table write privilege was added for locking.
- Use Argon2id and opaque eight-hour sessions with a 32-byte digest in PostgreSQL. Sessions are rechecked for current account state, revocation, and expiry. Writes require an exact Origin and a CSRF token keyed by that specific session. New login rotates a presented same-account session. Password changes and resets revoke all account sessions.
- The five- and 30-failure thresholds apply to fixed 15-minute windows. Both counters survive a successful login until expiration. Cleanup deletes at most 100 rows older than one day per login. The local default ignores forwarded addresses, which can create a shared nginx address bucket. There is an opt-in for one exact non-loopback private nginx peer. Rotating the digest key makes old buckets irrelevant and cleanup removes them after their retention interval.
- Runtime gains credential reads and column-restricted credential writes, session reads and column-restricted insert/revoke operations, and throttle mutations with bounded cleanup in service code. Runtime directory, role assignment, catalog, and audit rewrite operations remain denied. Audit records typed successful and failed authentication actions, with no fabricated actor for operator actions or rejected login. Failed mandatory audit writes roll back session issuance and password changes.
- nginx's demo host allows only the Phase 1 diagnostic API paths. The admin host exposes the API and a non-sensitive placeholder, and does not serve demo files. The published ports remain on loopback. Direct API access has the same authentication, exact Origin, and CSRF checks.
- WP1 and WP2 were accepted using standalone verification. WP3 reuses the existing tables and keeps `0002_identity_foundation` as the required revision. The unchanged revision hashes were verified. No RBAC evaluator, directory routes, auth UI, or MDL/QTA/CRT business functionality is part of WP3. Membership history still needs a WP5 decision about how to identify both parts of the association.

## Exact verification commands

Python 3.12.16, PostgreSQL 18.7, and temporary fixture credentials were used. The scratch database and listeners were separate from the development environment.

**Final API suite:** 72 passed, 0 failed, 0 skipped. It includes 59 Phase 1, WP1, and WP2 checks and 13 WP3 checks. Four dependency deprecation warnings were reported. The final run exercised the operator reset concurrently with login and verified that a failed password-change audit preserves both the previous credential and its session.

```bash
export PYTHONPATH=apps/api/src PYTHONDONTWRITEBYTECODE=1 AQ_UAI_ENVIRONMENT=test
export AQ_UAI_DB_HOST=/tmp/aq-uai-wp3.ftgDHprT AQ_UAI_DB_PORT=56435
export AQ_UAI_DB_NAME=aq_wp3_suite AQ_UAI_DB_USER=huydev
read -r AQ_UAI_DB_PASSWORD < /tmp/aq-uai-wp3.ftgDHprT/test-password
export AQ_UAI_DB_PASSWORD AQ_UAI_RUN_DB_TESTS=1
wp3_python=/tmp/aq-uai-wp1.Idb9IyUL/venv/bin/python
"$wp3_python" -m alembic -c apps/api/alembic.ini upgrade head
"$wp3_python" -m pytest -p no:cacheprovider -q --tb=short apps/api/tests
env AQ_UAI_DB_PORT=invalid "$wp3_python" -m alembic -c apps/api/alembic.ini upgrade head --sql
/tmp/aq-uai-wp1.Idb9IyUL/venv/bin/ruff check --no-cache apps/api/src apps/api/tests apps/api/migrations/env.py scripts/verify_wp2_compose.py
/usr/bin/python3 -B scripts/verify_frontend_assets.py
node scripts/test_sidebar_navigation.cjs
for f in apps/web/shared/*.js apps/web/module*/*.js; do node --check "$f" || exit; done
bash -n scripts/dev-up.sh
/usr/bin/python3 -B scripts/verify_wp2_compose.py --env-file .env.example --project-name aq-wp3-verify
git diff --check
```

- **Standalone PostgreSQL:** The suite includes Phase 1 diagnostics, WP1 migration checks, WP2 provisioning and privilege checks, and WP3 credential, throttle, CSRF, audit, and concurrency tests. Schema consistency was checked with Alembic as the disposable schema owner. The tests use the real restricted role for authentication writes and privilege denials. The sidebar regression and missing-session test failed before their respective changes and passed after implementation.
- **Standalone nginx and Chrome:** `/home/huydev/anaconda3/bin/python /tmp/aq-uai-wp3.ftgDHprT/native-smoke.py` passed. The scratch harness ran the real provisioning and migration commands, used a pseudo-terminal for hidden-input bootstrap and reset, and started the restricted API, nginx 1.18, and Chrome 158. It substituted only the nginx listen addresses, upstream, static root, and temporary paths for the standalone setup. `nginx -t` succeeded. `python scripts/phase1_smoke.py --base-url http://localhost:58083` passed all three diagnostics through nginx to PostgreSQL. The smoke test covered origin failures, valid admin login and logout, admin rejection of demo assets, direct API Origin enforcement, recovery, and browser layout.
- **Docker:** Docker daemon access was denied at `/var/run/docker.sock` through the normal permission mechanism. Rendered Compose environment checks passed. Live Compose services, effective container environments, and the developer's consolidated deployment remain unverified. No actual dotenv settings, credentials, database contents, accounts, or persistent volumes were changed. The [rollout guide](wp3-operations.md#rollout-after-approval) gives the minimal manual steps for a developer with Docker access.

## Exact changed-file inventory

| Area | Files |
|---|---|
| Demo layout | `apps/web/shared/core.js`, `apps/web/shared/actions.js`, `apps/web/shared/base.css`, `apps/web/module2/module2.css`, `apps/web/module3/module3.css` |
| Git safety and frontend regression | `.gitignore`, `.github/workflows/ci.yml`, `scripts/test_sidebar_navigation.cjs` |
| Authentication API | `apps/api/src/aq_uai_api/api/v1/auth.py`, `apps/api/src/aq_uai_api/api/errors.py`, `apps/api/src/aq_uai_api/main.py` |
| Authentication service | `apps/api/src/aq_uai_api/auth/__init__.py`, `apps/api/src/aq_uai_api/auth/operator.py`, `apps/api/src/aq_uai_api/auth/security.py`, `apps/api/src/aq_uai_api/auth/service.py` |
| Backend configuration, audit, and provisioning | `apps/api/pyproject.toml`, `apps/api/src/aq_uai_api/core/config.py`, `apps/api/src/aq_uai_api/db/audit.py`, `apps/api/src/aq_uai_api/db/provision.py`, `apps/api/src/aq_uai_api/db/session.py` |
| PostgreSQL and API tests | `apps/api/tests/integration/__init__.py`, `apps/api/tests/integration/test_wp2_database.py`, `apps/api/tests/integration/test_wp3_auth.py`, `apps/api/tests/unit/test_wp3_auth.py` |
| Compose and nginx | `.env.example`, `apps/api/Dockerfile`, `infra/compose.yaml`, `infra/nginx/default.conf`, `scripts/dev-up.sh`, `scripts/verify_wp2_compose.py` |
| Documentation | `AGENTS.md`, `README.md`, `docs/setup/PHASE_0_1.md`, `docs/phase2/plan.md`, `docs/phase2/wp2-operations.md`, `docs/phase2/wp3-operations.md`, `docs/phase2/wp3-report.md` |

The Git upstream change was local repository metadata. The WP2 example now reflects that `Unit` has no `updated_at` column. Later services maintain timestamps on models that define them. The remaining operational limits are the shared local nginx address bucket by default, live Compose verification, and later acceptance of the three module FRDs.
