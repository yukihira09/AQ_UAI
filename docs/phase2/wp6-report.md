# WP6 browser administration report

The browser application lives under `apps/admin/` and uses native JavaScript modules. nginx serves it from a read-only root on `admin.localhost`. The existing prototype remains on `localhost` with only its three diagnostic API routes. The admin host serves its own index at `/` and its own assets under `/assets/`. A restrictive content security policy limits app scripts, styles, and requests to that origin.

`app.mjs` restores sessions, routes hash URLs, and updates the persistent shell. `api.mjs` centralizes requests and Vietnamese error messages. `pages.mjs` builds directory screens with `ui.mjs` dialogs, filter controls, paginated lookups, and tables. Lists use the server's scoped count. Memberships and unit references come from authorized search endpoints. The API remains the authority on writes.

Sign-in expects `204`, then reads `/auth/me`. A temporary password opens the restricted change form and a successful change returns to sign-in. A rejected current password leaves the form usable when the session still exists. The browser owns the HTTP-only cookie and sends its own Origin. CSRF proof stays in memory. On navigation or return to a tab, the UI checks the current session identity, including when another tab switched accounts. Protected page loading resolves current capabilities and aborts stale reads. Uncertain mutations show a recovery message and are never retried automatically.

## Coverage of all 33 WP5 operations

The endpoints below are relative to `/api/v1`. `G` means institution-wide. `D` is `directory.read`, `M` is `directory.manage`, `P` is `directory.profile.update`, `A` is `authorization.manage`, and `H` is `audit.read`. `K` is global A for authorization groups and global M for system and specialist groups. Target lookups apply WP5 visibility rules.

| Operation | UI workflow | Permission | Chromium evidence |
| --- | --- | --- | --- |
| `GET /users` | Account list and reference searches | Scoped D | Accounts, scopes |
| `GET /users/{user_id}` | Account detail | Scoped D | Accounts, scopes |
| `POST /users` | Create with or without temporary password | G M | Accounts, groups |
| `PATCH /users/{user_id}/profile` | Edit display name | Scoped D and P | Accounts, scopes |
| `PATCH /users/{user_id}/identity` | Edit login and institutional code | G M | Accounts |
| `POST /users/{user_id}/activate` | Activate or provision initial credentials | G M | Accounts |
| `POST /users/{user_id}/disable` | Confirm disablement | G M | Accounts |
| `POST /users/{user_id}/transfer` | Select an active destination | G M | Accounts |
| `GET /units` | Unit list and reference searches | Scoped D | Accounts, scopes |
| `GET /units/{unit_id}` | Unit detail | Scoped D | Accounts |
| `POST /units` | Create unit | G M | Accounts |
| `PATCH /units/{unit_id}` | Edit unit code or name | G M | Accounts |
| `POST /units/{unit_id}/activate` | Confirm activation | G M | Accounts |
| `POST /units/{unit_id}/deactivate` | Confirm deactivation | G M | Accounts |
| `GET /groups` | Group list and filters | G D | Groups |
| `GET /groups/{group_id}` | Group detail | G D | Groups |
| `POST /groups` | Create one of the permitted kinds | K | Groups |
| `PATCH /groups/{group_id}` | Rename group | K | Groups |
| `POST /groups/{group_id}/activate` | Confirm activation | K | Groups |
| `POST /groups/{group_id}/deactivate` | Confirm deactivation | K | Groups |
| `GET /groups/{group_id}/members` | List participating or removed members | G D | Groups |
| `PUT /groups/{group_id}/members/{user_id}` | Add or reactivate membership | K | Groups |
| `DELETE /groups/{group_id}/members/{user_id}` | Confirm removal | K | Groups |
| `GET /roles` | Browse role permissions and choose a role | G A | Groups |
| `GET /users/{user_id}/role-assignments` | Direct grants on account detail | G A | Accounts, groups |
| `POST /users/{user_id}/role-assignments` | Create direct grant | G A | Groups |
| `DELETE /users/{user_id}/role-assignments/{grant_id}` | Confirm direct grant revocation | G A | Accounts, groups |
| `GET /groups/{group_id}/role-assignments` | Group grants on group detail | G A | Groups |
| `POST /groups/{group_id}/role-assignments` | Grant a role to an active authorization group | G A | Groups |
| `DELETE /groups/{group_id}/role-assignments/{grant_id}` | Confirm group grant revocation | G A | Groups |
| `GET /audit-events` | Filter and paginate events | G H | Groups |
| `GET /audit-events/{event_id}` | Inspect event fields and text changes | G H | Groups |
| `GET /directory/capabilities` | Overview, navigation, and control visibility | Unrestricted session | All |

Evidence labels map to `test_account_unit_workflows_and_conflicts` (Accounts), `test_groups_assignments_and_audit` (Groups), and `test_scoped_roles_filters_navigation_and_safe_text` (Scopes). All approved operations have a UI path. Group assignment creation is unavailable for ordinary groups and inactive authorization groups. Profile edits depend on the profile permission's own scope. Hard deletion, credentials recovery, catalog writes, and audit deletion have no UI controls.

## Verification and fixes

Tests use real Chrome through nginx and FastAPI with a restricted PostgreSQL runtime role. `tests/browser/test_admin.py` covers credentials and session restoration, throttling, expiry and cross-tab identity, origin and CSRF checks, storage isolation, all directory workflows, scoped visibility, hostile-looking text, pagination, history, and mobile keyboard navigation. During review, tests reproduced a password-change `401` being treated as logout, identity mismatches after switching accounts in another tab, and a narrow viewport expanding to the table width. The browser app now rechecks the session on ambiguous password errors and tab changes, and scrolls wide tables within their own region.

Seven Chromium scenarios passed at the WP6 gate. WP7 added two administration cases for uncertain write responses and selecting units across reference pages. The final OpenAPI comparison found a matching row for each of the 33 operations.

Files added for WP6 are `apps/admin/index.html`, `apps/admin/assets/{admin.css,api.mjs,app.mjs,pages.mjs,ui.mjs}`, and `tests/browser/{__init__.py,conftest.py,test_admin.py}`. WP6 changed `infra/nginx/default.conf` and `infra/compose.yaml`. The WP5 API and original demo sources were carried forward.

Live application testing with the developer's existing database and volume remains pending. Chromium is the tested browser engine. [WP7 validation and operational acceptance](wp7-report.md)
