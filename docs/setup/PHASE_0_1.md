# AQ EduUAI — Phase 0 & Phase 1: beginner-friendly setup

This guide records the Phase 0–1 baseline. For the current checkout, follow the [WP3 fresh setup or backup-first rollout](../phase2/wp3-operations.md#rollout-after-approval) for database credentials and startup.

## What is included?

- **Phase 0:** The old frontend was moved without rewriting it. Original JS/CSS/HTML and preview images are under `apps/web/`. The original frontend documentation/screenshots are in `docs/prototype/`.
- **Phase 1:** A *new* FastAPI backend, an Alembic database migration, PostgreSQL 18, and a local nginx web server that exposes both frontend and API on one origin.
- **Not included yet:** Login, users, permissions, real providers, model connection tests, monthly quotas or transactions. All three existing frontend modules still run on demo data in browser `localStorage`.

## A. Requirements

Install **Docker Engine + Docker Compose plugin** (or Docker Desktop), **Git**, and **VS Code**. Docker must be running. The default ports are:

| Local address | Service |
| --- | --- |
| http://localhost:8000 | Original AQ EduUAI frontend |
| http://localhost:8000/dev/phase1.html | New visual connectivity test |
| http://localhost:8000/api/v1/health | FastAPI liveness through nginx |
| http://localhost:8000/api/v1/ready | FastAPI + DB + migration check |
| http://localhost:8000/api/v1/system/info | A row returned from PostgreSQL |
| http://localhost:8001/docs | Interactive API documentation (FastAPI/Swagger) |
| localhost:55432 | PostgreSQL (local machine only) |

**Linux note:** if Docker says "permission denied", the current login may not have permission to talk to the Docker daemon. Follow the Docker Engine installation's post-install steps or use `sudo` as appropriate. Don't make the Docker socket publicly accessible.

## B. First run (from the `aq_uai` repository root)

1. Open the project directory in VS Code or a terminal (`code .`).
2. Make a local environment file:

   ```bash
   cp .env.example .env
   ```

3. Edit `.env` and replace the placeholder `POSTGRES_PASSWORD` with a new **local-only** password. Never commit `.env`.
4. Start all services:

   ```bash
   bash scripts/dev-up.sh
   ```

   Equivalent full command:

   ```bash
   docker compose --env-file .env -f infra/compose.yaml up --build -d
   ```

5. Inspect progress if required:

   ```bash
   docker compose --env-file .env -f infra/compose.yaml ps
   docker compose --env-file .env -f infra/compose.yaml logs --tail=100 migrate api
   ```

6. Open `http://localhost:8000/#module1` (existing frontend). Visit `http://localhost:8000/dev/phase1.html` and click **Run connectivity checks**.
7. Run the automated HTTP test (Python 3 is sufficient on your host):

   ```bash
   python3 scripts/phase1_smoke.py
   ```

   It verifies three URLs and a value read from PostgreSQL.

## C. What happened behind the scenes?

```text
1. Docker starts PostgreSQL (data persists in a named volume).
2. The "migrate" one-time container runs the Alembic migration.
3. The migration creates app_metadata and two harmless demo configuration rows.
4. FastAPI starts and exposes /api/v1/health, /api/v1/ready, /api/v1/system/info.
5. nginx serves the original frontend and forwards /api/... requests to FastAPI.
6. The Phase-1 diagnostic webpage asks FastAPI to read a row from PostgreSQL.
```

The existing Module 1/2/3 pages have not been connected to these APIs yet. That happens in subsequent phases.

## D. How to stop without losing PostgreSQL data

```bash
bash scripts/dev-down.sh
```

**Important:** `docker compose down` preserves the PostgreSQL named volume. Do **NOT** use `down -v` unless you consciously intend to permanently delete the local database volume. This setup contains no real users or secrets beyond your own local development credentials, but future phases will have data worth backing up.

## E. Quick developer checks

Install Python 3.12 and optional development tools if you want to run backend tests directly on your laptop:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e './apps/api[dev]'
python scripts/verify_frontend_baseline.py
python scripts/verify_original_archive.py
python scripts/verify_frontend_assets.py
python -m pytest -q apps/api/tests/unit
```

Or run JavaScript syntax checks if Node.js is already installed:

```bash
for f in apps/web/shared/*.js apps/web/module*/*.js; do node --check "$f"; done
```

The two archive SHA256 scripts are historical Phase-0 checks. After later authorized frontend changes, they will no longer pass by design; regular CI relies on asset validity and tests rather than forcing the UI to remain frozen forever.

Database integration tests require a live PostgreSQL test/dev database and correctly set `AQ_UAI_DB_*` fields, plus explicit `AQ_UAI_RUN_DB_TESTS=1`. They run automatically in the supplied GitHub Actions job. **Never run them against a production database.**

For migration commands in a running stack:

```bash
docker compose --env-file .env -f infra/compose.yaml run --rm migrate
```

For future migrations, use Alembic in `apps/api/migrations/`. Do not create a second independent database schema in `infra/` or hand-edit tables in pgAdmin without a migration.

## F. GitHub — preserve your existing remote

Your local Git repository already targets `https://github.com/yukihira09/AQ_UAI.git`. **Do not run `git init` again or add a second remote.** The uploaded ZIP did not include `.git/`, so this deliverable intentionally does not include one either.

Safest workflow:

1. Make sure your current repository is committed (`git status`). If you have uncommitted edits, commit or back them up first.
2. Put the files from this package into your **existing** clone of `AQ_UAI`. Remove/move the old root `index.html`, `shared/`, and `module1/2/3/` only after verifying the new `apps/web/` contains them. Don't delete unrecognized/untracked files.
3. Merge `.gitignore` rules with your existing file if you customized it (don't accidentally discard existing exclusions).
4. Run the static check script and locally start Docker.
5. Review changes and commit:

   ```bash
   git status
   git add -A
   git diff --cached --stat
   git commit -m "Phase 0-1: reorganize frontend and add FastAPI PostgreSQL foundation"
   git push origin main
   ```

If you want a safer review before pushing directly to `main`, create a branch first (`git switch -c phase0-phase1-foundation`) and open a pull request. Git will record moved files even if the server detects some as remove/add in the initial diff.

## G. Troubleshooting

- **Browser displays 502 Bad Gateway:** `api` container isn't ready; check `docker compose ... logs api migrate db`.
- **`/health` works but `/ready` is 503:** PostgreSQL connection or migration is missing; check `.env` and the `migrate` container logs.
- **Port in use:** adjust `WEB_HOST_PORT`, `API_HOST_PORT`, or `POSTGRES_HOST_PORT` in `.env` and restart. The documentation examples assume defaults.
- **Original demo shows old data:** `localStorage` is per browser origin. The new `http://localhost:8000` frontend will keep previous `aq_uai-demo-v1` data if that origin has been used. Clear only that key if you intentionally want demo defaults back.
- **Database password change after first initialization:** PostgreSQL's user/password is initialized on the **first** empty data directory. Changing `POSTGRES_PASSWORD` in `.env` later does not automatically alter an existing database user's password. Use SQL `ALTER ROLE` with care or intentionally recreate *a disposable* local volume after backing up any needed data.
- **`docker compose` isn't installed:** install the Compose v2 plugin; `docker-compose` v1 syntax isn't the supported setup.
- **Linux/macOS:** run the `.sh` scripts from Bash. For Windows, use WSL2 or the equivalent Docker Compose command shown above.
- **Avoid deploying this to the public internet:** Phase 2 authentication and authorization do not exist yet.

## H. Completion criteria

Phase 0: 14 original frontend files byte-identical, plus all 11 original documentation/screenshot files preserved; 10 referenced CSS/JS assets found; original screenshot assets preserved; original hash navigation/manual interactions unchanged.

Phase 1: `api` healthy; DB connects; migration produces `app_metadata`; `/api/v1/system/info` responds with source `postgresql`; the diagnostic HTML fetch succeeds; unit and database integration tests pass; no secrets committed.

**Runtime PostgreSQL and Docker checks must be run on a host with Docker installed.** Source-only validation is not equivalent to a successful deployment.
