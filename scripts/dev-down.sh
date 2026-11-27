#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ ! -f .env ]]; then
  echo 'Missing .env; create from .env.example first.' >&2
  exit 1
fi
# --remove-orphans also stops the optional synthetic demo-provider container (volumes are kept).
docker compose --env-file .env -f infra/compose.yaml down --remove-orphans
echo 'Stopped. The PostgreSQL named volume was intentionally preserved.'
