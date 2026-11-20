# AQ EduUAI — independent development workspace

**Current milestone: Phase 2 WP3 authentication under review.** The three frontend modules remain browser-only demonstrations. The API supports diagnostics and local authentication. RBAC administration and the module APIs require later packages.

> **New to backend development?** Begin with [Phase 0–1 setup guide](docs/setup/PHASE_0_1.md). It explains every command and the frontend → API → PostgreSQL flow.

## Start in three commands

For an existing Phase 1 or WP1 volume, follow the [consolidated WP3 rollout](docs/phase2/wp3-operations.md#rollout-after-approval). For a fresh install, run from this repository root with Docker and Docker Compose running:

```bash
cp .env.example .env
# Edit .env and set distinct database passwords plus the authentication throttle key.
bash scripts/dev-up.sh
```

- Frontend: http://localhost:8000/#module1
- Authenticated admin API: http://admin.localhost:8000/api/v1/auth/me
- Visual API/database connection demo: http://localhost:8000/dev/phase1.html
- Database-backed JSON response: http://localhost:8000/api/v1/system/info
- FastAPI interactive documentation: http://localhost:8001/docs

Stop without deleting database data:

```bash
bash scripts/dev-down.sh
```

## Top-level layout

```text
aq_uai/
  apps/web/                Original frontend (moved unchanged) and new diagnostic page
    index.html
    shared/                Existing demo state, actions, dialogs, CSS
    module1/ module2/ module3/
    dev/phase1.html        Real backend/database connectivity demo
  apps/api/                FastAPI application, tests and Alembic migrations
    src/aq_uai_api/        Python API package
    migrations/            The one source of truth for database schema changes
    tests/                 Unit tests + opt-in PostgreSQL integration test
  infra/                   Development Docker Compose + nginx routing
  docs/frd/                The exact three FRD Markdown sources
  docs/prototype/          Preserved original frontend README, notes and screenshots
  docs/architecture/       Architecture blueprint + frontend source audit
  docs/setup/              Beginner-friendly setup / verification instructions
  docs/decisions/          Documented engineering decisions
  scripts/                 Start, stop and verification helpers
  .github/workflows/ci.yml Automated checks on GitHub
```

## Independent checks

```bash
python3 scripts/verify_frontend_assets.py
python3 scripts/verify_frontend_baseline.py   # Phase-0 historical check only
python3 scripts/verify_original_archive.py     # Phase-0 historical check only
for f in apps/web/shared/*.js apps/web/module*/*.js; do node --check "$f"; done
```

Backend tests (requires Python 3.12 and dependencies installed):

```bash
python3 -m pip install -e './apps/api[dev]'
python3 -m pytest -q apps/api/tests/unit
```

Backend API endpoints now available:

| Path | Behavior |
| --- | --- |
| `GET /api/v1/health` | API liveness; no database required |
| `GET /api/v1/ready` | Database connectivity and migration readiness |
| `GET /api/v1/system/info` | Reads a marker from the *real* PostgreSQL `app_metadata` table |

No user-management, provider, quota, or ledger endpoints exist yet. These will be added under server-enforced permissions in later phases; existing frontend demo interactions are not backed by these APIs.

## Before modifying or pushing to GitHub

The uploaded source ZIP did not contain its `.git/` directory, so this package deliberately does not include or reinitialize Git. **Use your existing `AQ_UAI` repository** and merge new files there. See the [Git instructions](docs/setup/PHASE_0_1.md#f-github--preserve-your-existing-remote).

**Coding agent instructions:** `AGENTS.md` lists the rules and checks future Codex contributions should follow.

**Security:** This is a localhost development stack, not a production deployment. Never publish API/DB ports or real credentials until Phase 2 authentication, authorization, and security reviews are complete.
