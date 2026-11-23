# AQ EduUAI Phase 2 handoff

Phase 2 adds a real administration website for users, units, groups, role assignments, and audit history. The three AI module screens remain browser simulations. An origin is the combination of scheme, hostname, and port. The two hostnames keep their browser data and sessions separate.

| Default address | What it opens |
| --- | --- |
| http://admin.localhost:8000 | Sign-in and the persistent administration directory |
| http://localhost:8000 | Original MDL, QTA, and CRT demo |
| http://localhost:8000/dev/phase1.html | Read-only connection diagnostics |
| http://localhost:8001/docs | Local FastAPI OpenAPI documentation |

## How a request works

~~~text
Admin browser → nginx at admin.localhost → FastAPI /api/v1 → PostgreSQL
Demo browser  → nginx at localhost       → preserved files and diagnostics
~~~

nginx serves web files and forwards API requests. FastAPI checks who is signed in, the requested permission, and its organizational scope. PostgreSQL saves the directory change and its audit event together. A request ID links an API response to the corresponding event or sanitized server log. Alembic applies versioned database changes. The schema-owner login applies those changes and the API uses a separate restricted database login for requests.

| Package | What it supplies |
| --- | --- |
| WP1 | Identity, membership, grant, session, and audit tables |
| WP2 | Separate database roles, transaction and audit rules, safe API errors |
| WP3 | Admin bootstrap, passwords, sessions, expiration, revocation, and throttling |
| WP4 | Role-based access control and exact-unit or institution-wide scope |
| WP5 | Protected directory, membership, role assignment, and audit APIs |
| WP6 | Vietnamese administration UI on a separate nginx origin |
| WP7 | Regression, browser, restart, upgrade, restore, and CI checks |

## Fresh local installation

Install Docker Engine with Compose, or Docker Desktop. Run from the repository root. For a new environment, copy the example environment file and set owner-only access. Choose three distinct database passwords and a 64-character hexadecimal authentication throttle key. Use a password manager or run `openssl rand -hex 32` in a private terminal. Keep the file out of Git.

~~~bash
cp -n .env.example .env
chmod 600 .env
# Edit .env locally and replace its placeholder values.
bash scripts/dev-up.sh
~~~

`POSTGRES_USER` and `POSTGRES_PASSWORD` are the original database bootstrap credentials. `AQ_UAI_MIGRATION_PASSWORD` is for `aq_uai_schema` and `AQ_UAI_RUNTIME_PASSWORD` is for `aq_uai_runtime`. All host-published ports bind to loopback. Compose derives the admin origin from `WEB_HOST_PORT`. An explicit `AQ_UAI_AUTH_ORIGIN` must be the exact admin origin without a trailing slash. Stop with `bash scripts/dev-down.sh` to retain the database volume.

### First administrator and demonstration users

Run the interactive bootstrap once on an empty institution directory. It asks for the institution, first unit, administrator username and staff code, and a hidden temporary password. Use 12–128 characters and keep it distinct from the database passwords.

~~~bash
docker compose --env-file .env -f infra/compose.yaml run --rm --no-deps migrate \
  python -m aq_uai_api.auth.operator bootstrap
~~~

Open the admin hostname. Sign in using the temporary password, change it on the restricted page, and sign in again. The password change revokes the old session. Create a second unit and a synthetic user in the directory. You can leave the password blank to create a pending account and provision it later under **Kích hoạt tài khoản**. Assign a **DIRECTORY_READER** grant limited to one unit. Sign in as that user in a separate browser profile because tabs at the same hostname share their session cookie. Test which records are visible. A **UNIT_DIRECTORY_MANAGER** can also edit display names within its granted unit.

To check delegation, create a **Phân quyền** group, assign an eligible reader role, and add a demonstration user. Removing membership or deactivating the group removes the inherited permission. Look under **Nhật ký** for the audit events. The last usable foundation administrator cannot be disabled or stripped of that role.

## Upgrade an existing installation after approval

Use the original Compose project and PostgreSQL volume, and keep the original database name, bootstrap username, and bootstrap password. Changing an environment variable alone cannot change a PostgreSQL login that already exists. Add or retain the restricted-role passwords and authentication settings. Stop writes during the maintenance window, then take and validate a backup. The `compose` Bash array uses the default project. Add `-p ORIGINAL_PROJECT` if the original installation used another name. Stop on any command failure.

~~~bash
compose=(docker compose --env-file .env -f infra/compose.yaml)
"${compose[@]}" stop web api
umask 077
backup=$(mktemp "$HOME/aq-uai-phase2.XXXXXXXX.dump")
"${compose[@]}" exec -T db sh -c \
  'export PGPASSWORD="$POSTGRES_PASSWORD"; exec pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$backup"
"${compose[@]}" exec -T db pg_restore --list < "$backup"
~~~

Rehearse restoration on a separate instance before relying on the archive. Then run provisioning and migrations in order. Leave the old volume intact.

~~~bash
"${compose[@]}" run --rm --no-deps --build provision
"${compose[@]}" run --rm --no-deps --build migrate
"${compose[@]}" up -d --no-deps --build api
"${compose[@]}" up -d --no-deps web
python3.12 scripts/phase1_smoke.py
~~~

Provisioning reconciles schema ownership and privileges. The migration job updates an earlier schema and reapplies current runtime grants. WP5 changed grants while keeping Alembic at `0002_identity_foundation`. After readiness passes, sign in, create a synthetic unit, and find its `unit.created` audit event. A successful directory write checks the effective runtime access. [Database role verification](wp2-operations.md#verify)

## Restore and verify a backup

A successful `pg_dump` creates an archive. `pg_restore --list` confirms that its table of contents can be read. A restore copies the archive into another database. Application recovery also requires checking the restored records and credentials, database privileges, audit history, and a successful new write.

Use an **empty separate PostgreSQL instance**, isolated Compose project, fresh data volume, and different loopback ports. Use a private, separate environment file. The database role names are fixed for each installation, so a separate server avoids conflicts with existing role names. Set `isolated_env` to your isolated environment file's absolute path and keep `backup` set to the archive path.

~~~bash
restore=(docker compose -p aq-phase2-restore --env-file "$isolated_env" -f infra/compose.yaml)
"${restore[@]}" up -d --wait db
"${restore[@]}" exec -T db sh -c \
  'export PGPASSWORD="$POSTGRES_PASSWORD"; exec pg_restore --no-owner --no-privileges --single-transaction --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$backup"
"${restore[@]}" run --rm --no-deps --build provision
"${restore[@]}" run --rm --no-deps --build migrate
"${restore[@]}" up -d --no-deps --build api
"${restore[@]}" up -d --no-deps web
~~~

Restoration uses the target bootstrap owner. Provisioning assigns existing objects to the schema owner and reapplies runtime privileges. Use a separate browser profile for the restore because a hostname's session cookie can persist across ports. Check the previous UUIDs, memberships, role assignments, and audit events. Then create a new synthetic unit and verify its event. Keep the source volume and archive until recovery is independently accepted. Treat archives as confidential because they contain user, credential, and session data.

## Automated tests

Install Python 3.12, Node.js, nginx, and PostgreSQL 18 binaries for standalone verification. Playwright is only a test dependency. The script runs a private PostgreSQL cluster on a temporary Unix socket, real Uvicorn servers, and standalone nginx with the repository's routing configuration. It runs API, browser, restart, upgrade, and restore checks, then stops the temporary cluster.

~~~bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e './apps/api[dev]' -r tests/browser/requirements.txt
python -m playwright install chromium
AQ_PHASE2_PYTHON=python AQ_PHASE2_PG_BIN=/usr/lib/postgresql/18/bin bash scripts/verify_phase2.sh
~~~

Set `AQ_NGINX` and `AQ_NGINX_MIME_TYPES` for a nonstandard nginx installation. Set `AQ_CHROME` to use an installed Chrome in place of Playwright Chromium. After an approved Compose rollout, run the Phase 1 smoke script with `--base-url` pointing at the demo address if the port differs. [Verification results and pending deployment checks](wp7-report.md)

## Troubleshooting and scope

- **Docker socket permission denied.** Use standalone tests or run Compose from an approved account with Docker access.
- **Sign-in returns 403.** Use the admin hostname and match the configured origin exactly. Reload a tab if another tab changed the session.
- **Sign-in returns 429.** Wait for the 15-minute throttle window and check the username before trying again.
- **Readiness returns 503.** Check migration and API logs for schema or connection issues. A green readiness check with failed writes calls for checking the runtime-grant step.
- **Old demo data remains.** It belongs to the browser profile on localhost. Directory records are in PostgreSQL.
- **Only one administrator exists.** Create another eligible direct global administrator before disabling or removing the grant from the original account.

The institution should confirm identity-code policy and audit readership and retention before onboarding real records. MDL still needs provider configuration and real quota-free connection tests. QTA still needs an approved group synchronization source and additive monthly entitlement. CRT still needs scoped credit operations and an append-only ledger, including a decision on historical visibility after transfers. Token-to-credit conversion remains undefined. [Open Product Owner decisions](plan.md#frd-requirements-and-product-owner-decisions)
