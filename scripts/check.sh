#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 scripts/verify_frontend_assets.py
for source in apps/web/shared/*.js apps/web/module*/*.js; do
  if command -v node >/dev/null 2>&1; then node --check "$source"; fi
done
python3 -m pytest -q apps/api/tests/unit
printf '\nSource and Phase-1 unit checks passed.\n'
