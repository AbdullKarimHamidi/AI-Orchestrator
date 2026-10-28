#!/bin/sh
# API and worker in one container, for single-service hosts such as Render's free plan (render.yaml).
# docker compose runs them as separate services instead and does not use this script.
# The worker is restarted if it exits; runs it held are recovered by lease expiry.
(while true; do
  python -m app.workers.main
  echo "worker exited, restarting in 5s" >&2
  sleep 5
done) &
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
