#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ ! -f .env ]]; then
  echo 'Missing .env; create from .env.example first.' >&2
  exit 1
fi
docker compose --env-file .env -f infra/compose.yaml down
echo 'Stopped. The PostgreSQL named volume was intentionally preserved.'
