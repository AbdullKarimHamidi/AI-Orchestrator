#!/usr/bin/env bash
# One-command startup for Linux and macOS (the Windows equivalent is scripts/dev.ps1).
#
#   ./scripts/dev.sh           # Docker: build and start mongo, api, worker, web
#   ./scripts/dev.sh --local   # run api, worker and web natively (needs uv, Node 20.9+, a Mongo replica set)
#   ./scripts/dev.sh --down    # stop the Docker stack
#   ./scripts/dev.sh --logs    # follow logs
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ensure_env() {
  if [[ ! -f .env ]]; then
    key="$("$ROOT/scripts/new-key.sh")"
    sed "s|^ENCRYPTION_KEYS=.*|ENCRYPTION_KEYS=$key|" .env.example > .env
    echo "Created .env with a new ENCRYPTION_KEYS value (keep it: stored provider keys depend on it)."
  fi
}

wait_url() {
  local url=$1 deadline=$((SECONDS + ${2:-180}))
  while (( SECONDS < deadline )); do
    code=$(curl -s -o /dev/null -w '%{http_code}' "$url" || true)
    [[ $code =~ ^[234] ]] && return 0
    sleep 2
  done
  return 1
}

case "${1:-}" in
  --down) docker compose down; exit ;;
  --logs) docker compose logs -f; exit ;;
  --local)
    ensure_env
    for c in uv npm; do command -v "$c" >/dev/null || { echo "$c is required for --local" >&2; exit 1; }; done
    set -a; # export every variable from .env to the three processes
    # shellcheck disable=SC1091
    source .env; set +a
    (cd apps/api && uv sync)
    (cd apps/web && [[ -d node_modules ]] || npm ci)
    trap 'kill 0' EXIT INT TERM
    (cd apps/api && uv run uvicorn app.main:app --port 8000 2>&1 | sed 's/^/[api]    /') &
    (cd apps/api && uv run python -m app.workers.main 2>&1 | sed 's/^/[worker] /') &
    (cd apps/web && npm run dev 2>&1 | sed 's/^/[web]    /') &
    wait_url http://localhost:3000/login && echo "Ready: http://localhost:3000  (API docs: http://localhost:8000/api/docs)"
    wait
    ;;
  "")
    ensure_env
    command -v docker >/dev/null || { echo "Docker is not installed (or use --local)" >&2; exit 1; }
    docker compose up --build -d
    echo "Waiting for http://localhost:3000 ..."
    if wait_url http://localhost:3000/login; then
      echo "Ready: http://localhost:3000  (API docs: http://localhost:8000/api/docs)"
    else
      echo "The web app did not respond in time. Check: docker compose logs -f" >&2; exit 1
    fi
    ;;
  *) sed -n '2,8p' "$0"; exit 1 ;;
esac
