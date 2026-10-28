#!/usr/bin/env bash
# Runs every check: backend lint + tests, frontend typecheck + lint + unit tests + build.
#
#   ./scripts/test.sh          # needs a MongoDB replica set at MONGODB_URI (default 127.0.0.1:27017, rs0)
#   ./scripts/test.sh --e2e    # also runs the Playwright journey against http://localhost:3000
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
failed=()
step() { local name=$1 dir=$2; shift 2; echo; echo "=== $name ==="; (cd "$dir" && "$@") || failed+=("$name"); }

step "backend lint (ruff)"   "$ROOT/apps/api" uv run ruff check app tests
step "backend tests (pytest)" "$ROOT/apps/api" uv run pytest -q
step "frontend typecheck"    "$ROOT/apps/web" npm run typecheck
step "frontend lint"         "$ROOT/apps/web" npm run lint
step "frontend unit tests"   "$ROOT/apps/web" npm test
step "frontend build"        "$ROOT/apps/web" npm run build
if [[ "${1:-}" == "--e2e" ]]; then
  step "e2e (playwright)" "$ROOT/apps/web" sh -c 'npx playwright install chromium && npx playwright test'
fi

if (( ${#failed[@]} )); then echo; echo "FAILED: ${failed[*]}"; exit 1; fi
echo; echo "All checks passed."
