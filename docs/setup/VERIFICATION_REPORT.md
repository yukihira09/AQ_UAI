# Phase 0–1 verification evidence (2026-11-19)

## Verified in the build environment

| Verification | Result | Method |
| --- | --- | --- |
| Preserve all originally uploaded ZIP files | PASS — 25/25 files byte-identical | SHA256 against `aq_uai.zip` |
| Preserve original frontend sources and assets | PASS — 14/14 files byte-identical | Source frontend manifest |
| Original HTML linked asset resolution | PASS — 10/10 links | HTML parser/relative files |
| Original classic JS load order | PASS — 6 scripts in original order | Static HTML check |
| Original JavaScript syntax | PASS — 6/6 `.js` files | `node --check` |
| FastAPI pure unit tests | PASS — 8/8 | `pytest` |
| Live FastAPI health endpoint (localhost without DB) | PASS | `uvicorn` process + Python HTTP client |
| Alembic PostgreSQL SQL generation | PASS | `alembic upgrade head --sql` |
| Docker Compose YAML parsed | PASS | YAML parser; services `db`, `migrate`, `api`, `web` |
| PostgreSQL integration test on live database | NOT RUN HERE | No Docker/PostgreSQL server in build environment |
| Docker Compose container startup and nginx proxy | NOT RUN HERE | Docker executable unavailable |
| New visual diagnostic webpage interaction | NOT RUN IN BROWSER HERE | Chromium localhost navigation blocked by environment policy |
| GitHub Actions CI workflow | NOT RUN HERE | Executes on user's GitHub after push |
| Ruff static linter | NOT RUN HERE | Ruff not locally installed; CI installs it |

**Important:** The Phase-1 implementation is packaged and unit-tested, but the live Docker/PostgreSQL verification must be completed in the user's own development environment or CI. No claim of a fully validated database deployment is made.

## Phase-1 startup acceptance checklist (user machine)

- [ ] Copy `.env.example` to `.env` and choose a private local password.
- [ ] `docker compose --env-file .env -f infra/compose.yaml up --build -d` exits successfully.
- [ ] `docker compose --env-file .env -f infra/compose.yaml ps` reports `db` and `api` healthy; `migrate` exited successfully; `web` running.
- [ ] `http://localhost:8000/#module1` shows the original demo, and the other two module tabs still work.
- [ ] `http://localhost:8000/dev/phase1.html` shows HTTP 200 for all three checks.
- [ ] `python scripts/phase1_smoke.py` passes.
- [ ] `http://localhost:8001/docs` shows three documented endpoints.
- [ ] GitHub Actions checks pass after pushing the repository.

## Baseline policy for future phases

`docs/prototype/*_manifest.json` is immutable historical evidence of the original uploaded ZIP. The parity scripts are expected to fail **after an authorized later frontend change**; they are not run in normal CI. Future tests must validate behavior of the new frontend, not require its original files to remain byte-identical indefinitely.
