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
compose_files=(-f infra/compose.yaml)
if [[ "${1:-}" == "--demo-provider" ]]; then
  # Synthetic AI provider for demos (MDL decision D15); see infra/compose.demo-provider.yaml.
  if ! grep -Eq '^AQ_DEMO_PROVIDER_API_KEY=.{16,}' .env; then
    echo 'Set AQ_DEMO_PROVIDER_API_KEY (16+ characters) in .env to use --demo-provider.' >&2
    exit 1
  fi
  compose_files+=(-f infra/compose.demo-provider.yaml)
fi
docker compose --env-file .env "${compose_files[@]}" up --build -d
# nginx resolves "api" only when it starts. When "up" recreates api (new code or settings) but
# not web, nginx keeps the old address and answers 502; a graceful reload re-resolves it.
docker compose --env-file .env "${compose_files[@]}" exec -T web nginx -s reload >/dev/null 2>&1 || true
printf '\nAQ EduUAI UI: http://localhost:%s/#module1\n' "$(sed -n 's/^WEB_HOST_PORT=//p' .env | tail -1 | cut -d'#' -f1 | xargs || echo 8000)"
echo 'Health via proxy: http://localhost:8000/api/v1/health (use your configured WEB_HOST_PORT if changed)'
echo 'Read DB record:  http://localhost:8000/api/v1/system/info'
[[ "${1:-}" == "--demo-provider" ]] && echo 'Demo AI provider (synthetic): https://demo-provider:8443/v1 inside the stack; see docs/phase3/mdl-handoff.md'
echo 'OpenAPI:         http://localhost:8001/docs (use your configured API_HOST_PORT if changed)'
