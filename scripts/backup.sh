#!/usr/bin/env bash
# Consistent MongoDB backup from the running compose stack into ./backups/<timestamp>.archive.gz
#
#   ./scripts/backup.sh                 # keep the newest 14 backups
#   KEEP=30 ./scripts/backup.sh
#
# Schedule daily with cron, e.g.:  0 3 * * *  cd /opt/orchestrator && ./scripts/backup.sh >> backups/backup.log 2>&1
# IMPORTANT: also back up .env (ENCRYPTION_KEYS). Without it, stored provider API keys cannot be decrypted.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p backups
DB="$(grep -E '^MONGODB_DB=' .env 2>/dev/null | cut -d= -f2 || true)"; DB="${DB:-orchestrator}"
out="backups/$(date -u +%Y%m%dT%H%M%SZ).archive.gz"
docker compose exec -T mongo mongodump --quiet --db "$DB" --archive --gzip > "$out"
echo "Wrote $out ($(du -h "$out" | cut -f1))"
ls -1t backups/*.archive.gz | tail -n +$(( ${KEEP:-14} + 1 )) | xargs -r rm --
