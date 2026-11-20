# Backend (Phase 1)

This API package is a deliberately small starting point. It does not perform actual MDL/QTA/CRT operations yet.

## Read the code in this order

1. `src/aq_uai_api/main.py` — creates FastAPI and includes the system router.
2. `src/aq_uai_api/api/v1/system.py` — contains three Phase-1 HTTP endpoints.
3. `src/aq_uai_api/core/config.py` — reads environment variables and constructs the database connection URL (no credentials in code).
4. `src/aq_uai_api/db/session.py` — creates SQLAlchemy database connections and sessions.
5. `src/aq_uai_api/db/models.py` — defines the tiny `app_metadata` diagnostic table.
6. `migrations/versions/0001_phase1_metadata.py` — creates the table and inserts two seed rows when `alembic upgrade head` is executed.
7. `tests/unit/` and `tests/integration/` — proves API behavior and database readiness.

## One request from start to finish

`GET /api/v1/system/info` → FastAPI router → database session → `SELECT` of `app_metadata` (via SQLAlchemy) → PostgreSQL → JSON response. Try it from the [development connectivity page](../web/dev/phase1.html) when the Compose stack is running.

## Design boundary

Only one diagnostic table exists. Later `identity`, `mdl`, `qta`, `crt` and `audit` packages will be added in their relevant phases, not in this Phase-1 skeleton. Do not prematurely use the diagnostic `app_metadata` table to store model credentials or business transactions.

## Testing without Docker

With Python dependencies installed: `python -m pytest -q apps/api/tests/unit` from the repository root. Database-backed tests require a disposable real PostgreSQL database and `AQ_UAI_RUN_DB_TESTS=1`.
