# WP7 Phase 2 verification and handoff

Phase 2 is a modular FastAPI and PostgreSQL application with a separate browser administration site and the existing AI module demos. WP7 verifies the integrated application and recovery path with synthetic data. The [WP6 report](wp6-report.md) lists all 33 operations, matching screens, permissions, and browser evidence. The [handoff](phase2-handoff.md) covers daily use, bootstrap, approved upgrade, and recovery.

## Verification matrix

| Area | Evidence |
| --- | --- |
| Phase 1 diagnostics | Lifecycle, readiness, and PostgreSQL metadata returned through nginx. The browser restart test also ran the original HTTP smoke script. |
| WP1 identity and schema | Migration and named-constraint tests ran against PostgreSQL. Alembic retained head `0002_identity_foundation` and detected no schema drift. Both historical revision files are intact. |
| WP2 transactions and privileges | Fresh and legacy database tests checked role ownership, runtime grants, denial of privileged SQL, rollback on audit failure, request IDs, and sanitized errors. |
| WP3 authentication | API and browser tests covered initial password change, reauthentication, invalid and expired sessions, logout, username and account changes, throttling, secure Origin and CSRF requirements, and credential races. |
| WP4 permissions | API and browser tests covered institutional readers, exact-unit readers and managers, mixed global read and unit edit, inherited authorization, no-permission accounts, and visibility boundaries. |
| WP5 directory | Tested lifecycle, scoped counts, reference validation, all three last-admin races, transactional audit, membership UUID pairs, and append-only runtime audit permissions. |
| WP6 administration | Actual Chrome exercised the 33-operation interface, two separate hosts, request guards, text rendering, mobile navigation, keyboard access, and browser storage. |
| WP7 recovery | Legacy fixtures upgraded from Phase 1 and WP1. A logical archive was restored into a separate database, re-provisioned, compared, and tested by reading and writing through the application. |
| Compose configuration | Rendered with the example environment. Verified credential segregation, loopback bindings, read-only frontend/config mounts, and ordered startup. Container build and runtime checks remain pending. |
| CI | Expanded the existing workflow with PostgreSQL 18 client tools, nginx, pinned Playwright Chromium, browser checks, upgrades, and recovery. Local equivalent verification is recorded below. Hosted Actions was outside this run. |

## Commands and results

Verified on Python 3.12.3, PostgreSQL 18.7, nginx 1.18.0, and installed Google Chrome 158 using Playwright 1.59.0. nginx used the checked-in routing configuration with only the listener, two static roots, and API upstream adapted to temporary paths and loopback ports. The application's own database model, policy, credential code, services, and endpoints were used.

~~~bash
export AQ_PHASE2_PG_BIN=/usr/lib/postgresql/18/bin
export AQ_PHASE2_PYTHON=/tmp/aq-uai-phase2-tools/venv/bin/python
export AQ_NGINX=/tmp/aq-uai-phase2-nginx/usr/sbin/nginx
export AQ_NGINX_MIME_TYPES=/tmp/aq-uai-phase2-nginx/etc/nginx/mime.types
export AQ_CHROME=/usr/bin/google-chrome
export AQ_BROWSER_SCREENSHOTS=/tmp/aq-uai-phase2-screens
bash scripts/verify_phase2.sh
git diff --check
git diff --exit-code HEAD -- apps/web docs/prototype apps/api/migrations
~~~

The verification script runs Ruff, Node syntax checks, the demo asset verifier, sidebar regression, rendered Compose checks, `alembic upgrade head`, `alembic check`, `python -m pytest -p no:cacheprovider -q --tb=short apps/api/tests`, and `python -m pytest -p no:cacheprovider -q --tb=short tests/browser`. It starts its own private database cluster and uses generated credentials. Temporary tool paths above describe the verification run. Use the normal executable paths and dependencies in the handoff to reproduce it.

| Command group | Result |
| --- | --- |
| Phase 1 and WP1–WP5 pytest | **119 passed, 0 failed, 0 skipped** in 185.26 seconds. Four pre-existing dependency deprecation warnings from Starlette and Alembic. |
| WP6 browser gate | **7 passed, 0 failed, 0 skipped** at the transition to WP7. |
| Final Chromium and operations pytest | **13 passed, 0 failed, 0 skipped** in 151.74 seconds. Nine administration cases and four upgrade, restore, or restart cases. |
| Ruff, Node, demo assets, and Compose rendering | Passed. Listed demo assets exist in their original loading order. Sidebar regression passed. Frontend files and historical hashes match the previous tracked source. |
| Alembic consistency | No new upgrade operations detected on the clean database, both upgrade fixtures, and the restored database. |

The first manual API run lacked an Alembic upgrade in its control database and failed the Phase 1 setup check. The verification script now migrates its control database first. The original-demo browser test also needed to open the DPA tab before selecting **Thêm nhà cung cấp**. The corrected test passed through the preserved frontend without editing its assets. An initial sequential execution of the verification script hit the command runner's five-minute limit. The script runs the API and browser suites concurrently in separate fixture databases after preparing the control schema.

## Upgrade and restore rehearsal

- **Phase 1 upgrade.** Added a metadata marker at `0001_phase1_metadata`, exercised the pre-upgrade readiness error, then provisioned and migrated to current head. The original marker survived and the restricted runtime created a unit and corresponding audit event.
- **WP1 upgrade.** Kept a pre-existing administrator and a synthetic missing unit INSERT grant at the current schema revision. Readiness was green and the representative write failed. After grant reconciliation, the same administrator session and UUID remained usable and the write and audit event succeeded.
- **Archive and recovery.** Created a synthetic user with a credential, unit, authorization group, membership, direct and group roles, sessions, and events. Ran `pg_dump --format=custom`, inspected the archive with `pg_restore --list`, then used `pg_restore --no-owner --no-privileges --single-transaction --exit-on-error` against a different database. Ownership and runtime privileges were reapplied. A count and content digest of 15 tables, including credential, membership, assignment, session, and audit tables, matched before and after restore. The restricted login still could not modify history or create schema objects. The existing admin signed in, browsed the restored membership and audit history, and created a new unit with a new audit event.
- **Restart and demo isolation.** Restarted the standalone FastAPI process with nginx still serving both names. The browser restored its session and the unit was visible after reload. All three original module views opened. A synthetic QTA sync updated only the demo's local browser storage. The admin origin had no demo storage, and no directory group was created by the demo operation.

## Security and usability review

| Finding | Severity | Disposition |
| --- | --- | --- |
| Wrong current password and expired session both returned 401 during password change | Important | Confirm session with `/auth/me` and keep the password form usable only while the restricted session remains valid. Browser regression reproduced and verified the correction. |
| Shared cookie could change account in another tab while the shell still showed the prior identity | Important | Refresh identity and proof together on navigation and tab return. Reset the view when the account changes. Browser regression reproduced and verified the correction. |
| Wide directory table exceeded a narrow viewport width | Important usability | Constrain the workspace and scroll only the table region. The 360-pixel viewport and keyboard dialog tests passed. |
| Full reference search controls dominated filters and pushed form buttons below the fold | Minor usability | Keep the select visible and put search and paging behind a native disclosure control. Verify navigation to later results and preservation of the selection while searching. |
| Failed or lost mutation response may follow a committed change | Important usability | Show an explicit check-before-retry message. The browser test drops the response after a real unit creation, sees one committed result, and confirms the client sent one request. |
| Audit date outside the browser/server-supported range could fail without feedback | Minor | Validate conversion and show a localized filter error. |
| Audit or directory text could contain markup | Security control verified | Render text with native DOM nodes. The browser displayed a long Vietnamese string containing literal script markup without executing it. nginx CSP limits additional script sources. |
| A database connection with runtime credentials can issue the column-level SQL granted to it | Known architecture boundary | The authenticated application remains responsible for scopes and audit pairing. The runtime grants still forbid schema changes, catalog modification, and changes to historical audit rows. |

The review also checked inactive and restricted users, mixed grant scopes, cross-tenant PostgreSQL references, immediate server-side revocation, successful audit pairing, absence of session and password values in sampled service logs, and absence of persistent browser credentials. See the [accepted Phase 2 architecture](../architecture/ADR-0002-phase2-shared-foundation.md) for the unchanged service boundary.

Reviewed 11 Chromium captures covering sign-in, required password change, overview, units, user listing and creation, member management, assignment, audit detail, read-only access, and mobile layout. Follow-up screenshots showed the create form's action buttons within the desktop viewport and wide tables contained on mobile. The captures used synthetic records and stayed outside the repository.

## Live deployment gate

`docker version --format '{{.Server.Version}}'` returned a permission error connecting to `/var/run/docker.sock`. Local checks using the Compose plugin's rendered configuration passed. Image builds, fresh and legacy Compose startups, in-container checks, and controlled restart of a Compose service await a Docker-enabled environment. The existing database, application accounts, configuration, and volumes were untouched. Hosted GitHub Actions remains unverified.

On an approved Docker host, use separate synthetic credentials and loopback ports for a uniquely named disposable project. Keep the existing development project and volume out of this rehearsal.

~~~bash
test_env=/absolute/private/path/to/synthetic.env
test_project=aq-phase2-disposable
docker compose -p "$test_project" --env-file "$test_env" -f infra/compose.yaml up --build -d
python scripts/verify_wp2_compose.py --env-file "$test_env" --project-name "$test_project" --live
~~~

Use the handoff's bootstrap and smoke procedures with the isolated project and its port. Confirm a directory write and audit record, restart the isolated API, and verify data and session persistence. Stop the isolated project with the same project and environment arguments. Upgrade the developer's original volume only after separate approval. [Backup-first rollout and recovery guide](phase2-handoff.md)

## File inventory for WP6 and WP7

| Type | Exact files |
| --- | --- |
| Added admin frontend | `apps/admin/index.html`, `apps/admin/assets/admin.css`, `apps/admin/assets/api.mjs`, `apps/admin/assets/app.mjs`, `apps/admin/assets/pages.mjs`, `apps/admin/assets/ui.mjs` |
| Added verification | `tests/browser/__init__.py`, `tests/browser/conftest.py`, `tests/browser/requirements.txt`, `tests/browser/test_admin.py`, `tests/browser/test_operations.py`, `scripts/verify_phase2.sh` |
| Added reports and guide | `docs/phase2/wp6-wp7-plan.md`, `docs/phase2/wp6-report.md`, `docs/phase2/wp7-report.md`, `docs/phase2/phase2-handoff.md` |
| Modified deployment and CI | `infra/nginx/default.conf`, `infra/compose.yaml`, `.github/workflows/ci.yml`, `scripts/verify_wp2_compose.py` |
| Modified milestone and setup docs | `README.md`, `AGENTS.md`, `docs/phase2/plan.md`, `docs/architecture/ADR-0002-phase2-shared-foundation.md`, `docs/setup/PHASE_0_1.md` |

The working tree already contained WP4 and WP5 changes at the start. WP6 and WP7 introduced no changes to the API source, Alembic revisions, or original demo assets and manifests. [Deferred Product Owner decisions](plan.md#frd-requirements-and-product-owner-decisions)

## Acceptance

**WP6:** The browser integration meets the source and standalone verification gate. Each WP5 operation is reachable through its authorized workflow.

**WP7:** The source and automated verification gate passes on disposable PostgreSQL, FastAPI, nginx, and Chromium. Hosted CI and live Compose operational acceptance remain pending.
