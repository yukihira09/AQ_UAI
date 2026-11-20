#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ ! -f .env ]]; then
  echo 'Missing .env. Copy .env.example to .env and set the database passwords and authentication throttle key.' >&2
  exit 1
fi
if grep -Eq '^(POSTGRES_PASSWORD|AQ_UAI_MIGRATION_PASSWORD|AQ_UAI_RUNTIME_PASSWORD|AQ_UAI_AUTH_THROTTLE_KEY)=CHANGE_THIS_' .env; then
  echo 'Replace the password and throttle-key placeholders before starting.' >&2
  exit 1
fi
docker compose --env-file .env -f infra/compose.yaml up --build -d
printf '\nAQ EduUAI UI: http://localhost:%s/#module1\n' "$(sed -n 's/^WEB_HOST_PORT=//p' .env | tail -1 | cut -d'#' -f1 | xargs || echo 8000)"
echo 'Health via proxy: http://localhost:8000/api/v1/health (use your configured WEB_HOST_PORT if changed)'
echo 'Read DB record:  http://localhost:8000/api/v1/system/info'
echo 'OpenAPI:         http://localhost:8001/docs (use your configured API_HOST_PORT if changed)'
