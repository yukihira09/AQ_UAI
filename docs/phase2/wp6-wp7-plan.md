# WP6 and WP7 implementation plan

WP6 connects a separate administration UI to the existing Phase 2 API. WP7 verifies the integrated application and packages the recovery and rollout instructions. The MDL, QTA, and CRT prototype stays under `apps/web/`. The directory supports later work for FR-MDL-001, FR-QTA-001/020/022/030, and FR-CRT-001/010/013/030. Module-specific rules remain with those modules.

## WP6 browser application

1. Add `apps/admin/index.html` and `apps/admin/assets/{admin.css,app.mjs,api.mjs,ui.mjs,pages.mjs}`. Use native HTML, CSS, and JavaScript modules. The Vietnamese UI follows the demo's blue accents, pale background, persistent sidebar, and topbar. Use native dialogs, labeled fields, keyboard focus, and a mobile navigation toggle. Keep the original demo's assets and script order.
2. `api.mjs` owns relative `/api/v1` requests, query encoding, empty responses, sanitized errors, and CSRF proof held in memory. `app.mjs` owns authentication, hash navigation, current capabilities, request cancellation when navigating, and the persistent shell. Restore `/auth/me` at startup and reload capabilities for protected views. After `204` on a password change, return to sign-in. On `401` for established sessions, clear the protected UI. On `403`, preserve the signed-in identity and show the rejection.
3. `ui.mjs` provides native DOM components, bounded pagination, accessible forms, confirmation, feedback, and button locking during writes. `pages.mjs` composes rows, details, filters, and commands from the actual WP5 schemas. View navigation uses hash URLs without form data or authentication state.
4. Mount `apps/admin` read-only in Compose and serve its index and assets only on `admin.localhost`. Keep `localhost` on the demo root and proxy only Phase 1 diagnostics. Keep unexpected hosts denied and host ports bound to loopback. Add an admin content security policy with same-origin scripts, styles, and connections. Use the browser's Origin and the existing host-only HTTP-only cookie.

| Screen | WP5 operations |
| --- | --- |
| Overview and shared navigation | Capabilities and current session identity |
| Accounts | List, detail, create, profile, identity, activation, disablement, transfer |
| Units | List, detail, create, edit, activate, deactivate |
| Groups | List, detail, create, rename, activate, deactivate, member list, add/reactivate, remove |
| Roles and assignments | Role catalog, plus list, create, and remove for each subject type |
| Audit | Search/filter list and get event details |

Use the scoped unit selector for active references. Paginate it instead of assuming the first result page contains the correct unit. Use visible directory records for membership selection. Global reading, exact-unit editing, authorization-group management, and audit each use their own permissions. Existing groups use their stored kind. A restricted session sees only password change and logout. New group assignments are offered only for active authorization groups, and the assignment form uses the approved scope matrix. [WP5 contract](wp5-api.md)

### Plan review before implementation

- An empty login or mutation response must never be parsed as JSON. A failed mutation is never automatically retried. On a lost response, tell the operator to refresh and check its outcome.
- A stale asynchronous render must never restore a protected view after logout, expiry, or navigation. Abort stale reads and clear the authenticated DOM and in-memory session data on invalidation.
- A permission can be institution-wide for reads while another is unit-scoped for writes. Test the controls and the server response independently. Group lifecycle uses the server's group kind. Missing object and forbidden action keep their distinct messages.
- Treat all displayed fields, including audit payloads, as text. Keep passwords in the applicable form and transport request. Use browser-native labels, focus, form validation, and dialogs. Keep filters and pagination local to the current route.
- Preserve account state and grant invariants in the backend. After a successful write, reload the affected view and capabilities. Present safe explanations for uniqueness, last-admin, and unit deactivation conflicts without guessing which invariant the generic response represents.

## WP6 verification gate

Write browser tests first under `tests/browser/`. Launch the real FastAPI app and restricted PostgreSQL runtime identity through disposable nginx. Use Playwright only as a test dependency. Verify login, forced password change and reauthentication, refresh, logout and revocation, throttling, CSRF/Origin, and browser storage. Cover all directory workflows, scoped UI and direct API denials, search, pagination, hostile-looking strings, navigation, mobile and keyboard behavior. Map the 33 methods to UI actions and executed tests in `wp6-report.md`. Continue to WP7 after the primary browser and security workflows pass.

## WP7 verification and handoff

1. Run Phase 1 and WP1–WP5 API tests, Ruff, Alembic consistency, demo assets, sidebar regression, admin JavaScript checks, and nginx routing through the same production config with only disposable paths, port, and upstream substituted. Verify the demo in Chromium and verify browser state plus PostgreSQL persistence after restarting the disposable API.
2. Use synthetic legacy fixtures at Phase 1 and WP1, apply current provisioning and migration, and exercise a protected write as the restricted role. Dump a populated disposable database, inspect the archive, restore into a separate database, reconcile roles, compare historical data, and verify a write through the restored application. Use `tests/browser/` fixtures and `scripts/verify_phase2.sh` for repeatable checks.
3. Update CI with test-only Playwright and nginx, the browser and restore tests, and rendered Compose validation. Docker daemon access was denied on the initial check. Continue using standalone PostgreSQL and nginx. Record Docker image build, fresh/upgrade Compose startup, and the actual developer-volume rollout as pending wherever they cannot be executed. Use synthetic fixtures and local-only ports.
4. Review session transitions, authorization and tenant isolation, safe DOM rendering, server origin boundaries, audit atomicity, write duplication, and browser usability. Record results and any gaps in `wp7-report.md`, update the milestone documents, and write `phase2-handoff.md` with the approved fresh/upgrade and restore paths. Operational acceptance needs actual deployment evidence.

The work runs in the supplied workspace because the accepted WP4 and WP5 baseline includes uncommitted files. Keep Git history, actual environment, database, and volumes untouched.
