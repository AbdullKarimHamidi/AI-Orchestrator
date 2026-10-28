#!/usr/bin/env bash
# Restores a backup made by backup.sh, REPLACING the current database contents.
#
#   ./scripts/restore.sh backups/20260101T030000Z.archive.gz
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
file="${1:?usage: restore.sh <backup.archive.gz>}"
DB="$(grep -E '^MONGODB_DB=' .env 2>/dev/null | cut -d= -f2 || true)"; DB="${DB:-orchestrator}"
read -r -p "This replaces database '$DB' with $file. Type the database name to continue: " answer
[[ "$answer" == "$DB" ]] || { echo "Aborted."; exit 1; }
docker compose stop worker api
docker compose exec -T mongo mongorestore --quiet --drop --nsInclude "$DB.*" --archive --gzip < "$file"
docker compose start api worker
echo "Restored $file into $DB"
