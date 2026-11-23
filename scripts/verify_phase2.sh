#!/usr/bin/env bash
# Verify Phase 2 with a private Unix socket and a new temporary PostgreSQL cluster.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
phase2_python=${AQ_PHASE2_PYTHON:-python3.12}
export AQ_PHASE2_PG_BIN=${AQ_PHASE2_PG_BIN:-$(pg_config --bindir)}
phase2_pg=$AQ_PHASE2_PG_BIN
for tool in initdb pg_ctl createdb pg_dump pg_restore; do
  test -x "$phase2_pg/$tool" || { printf 'Missing PostgreSQL tool: %s\n' "$tool" >&2; exit 1; }
done

"$phase2_python" scripts/verify_frontend_assets.py
node --test scripts/test_sidebar_navigation.cjs
for source in apps/web/shared/*.js apps/web/module*/*.js apps/admin/assets/*.mjs; do
  node --check "$source"
done
"$phase2_python" -m ruff check apps/api/src apps/api/tests apps/api/migrations/env.py scripts/verify_wp2_compose.py
"$phase2_python" -m ruff check --config apps/api/pyproject.toml tests/browser
if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then
  "$phase2_python" scripts/verify_wp2_compose.py --env-file .env.example --project-name aq-phase2-config-check
else
  printf 'SKIP: Compose plugin unavailable for rendering the example configuration.\n'
fi

umask 077
phase2_tmp=$(mktemp -d "${TMPDIR:-/tmp}/aq-phase2.XXXXXXXX")
phase2_started=false
phase2_api_pid=
phase2_browser_pid=
cleanup() {
  for suite_pid in "$phase2_api_pid" "$phase2_browser_pid"; do
    if [[ -n "$suite_pid" ]] && kill -0 "$suite_pid" 2>/dev/null; then
      kill "$suite_pid" 2>/dev/null || true
      wait "$suite_pid" 2>/dev/null || true
    fi
  done
  if "$phase2_started" && ! "$phase2_pg/pg_ctl" -D "$phase2_tmp/pgdata" -m fast -w stop >/dev/null; then
    printf 'Could not stop disposable PostgreSQL at %s\n' "$phase2_tmp" >&2
    return 1
  fi
  rm -rf -- "$phase2_tmp"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

export AQ_UAI_ENVIRONMENT=test AQ_UAI_RUN_DB_TESTS=1 PYTHONDONTWRITEBYTECODE=1
export AQ_UAI_DB_NAME=aq_phase2_test AQ_UAI_DB_USER=aq_phase2_test
export AQ_UAI_DB_HOST=$phase2_tmp AQ_UAI_DB_PORT=5432
AQ_UAI_DB_PASSWORD=$("$phase2_python" -c 'from secrets import token_hex; print(token_hex(24))')
export AQ_UAI_DB_PASSWORD
printf '%s\n' "$AQ_UAI_DB_PASSWORD" > "$phase2_tmp/bootstrap-password"
"$phase2_pg/initdb" -D "$phase2_tmp/pgdata" -U "$AQ_UAI_DB_USER" \
  --auth=scram-sha-256 --pwfile="$phase2_tmp/bootstrap-password" --locale=C.UTF-8 >/dev/null
"$phase2_pg/pg_ctl" -D "$phase2_tmp/pgdata" -l "$phase2_tmp/postgres.log" \
  -o "-c listen_addresses='' -k '$phase2_tmp' -p $AQ_UAI_DB_PORT" -w start >/dev/null
phase2_started=true
PGPASSWORD=$AQ_UAI_DB_PASSWORD "$phase2_pg/createdb" \
  -h "$AQ_UAI_DB_HOST" -p "$AQ_UAI_DB_PORT" -U "$AQ_UAI_DB_USER" "$AQ_UAI_DB_NAME"

"$phase2_python" -m alembic -c apps/api/alembic.ini upgrade head
"$phase2_python" -m alembic -c apps/api/alembic.ini check
# Each suite creates separate databases. Run both after preparing the control schema.
"$phase2_python" -m pytest -p no:cacheprovider -q --tb=short apps/api/tests > "$phase2_tmp/api-tests.log" 2>&1 &
phase2_api_pid=$!
"$phase2_python" -m pytest -p no:cacheprovider -q --tb=short tests/browser > "$phase2_tmp/browser-tests.log" 2>&1 &
phase2_browser_pid=$!

phase2_status=0
wait "$phase2_api_pid" || phase2_status=1
phase2_api_pid=
cat "$phase2_tmp/api-tests.log"
wait "$phase2_browser_pid" || phase2_status=1
phase2_browser_pid=
cat "$phase2_tmp/browser-tests.log"
exit "$phase2_status"
