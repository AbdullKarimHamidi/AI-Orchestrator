"""Container healthcheck for the worker: `python -m app.workers.health`.

Healthy when the worker loop touched its heartbeat file recently. The loop iterates at least
every 15 s even while MongoDB is down (it backs off), so a stale file means a hung process."""
import os
import sys
import time

from app.workers.main import HEARTBEAT_FILE

MAX_AGE_SECONDS = 60

if __name__ == "__main__":
    try:
        age = time.time() - os.path.getmtime(HEARTBEAT_FILE)
    except OSError:
        sys.exit(1)
    sys.exit(0 if age < MAX_AGE_SECONDS else 1)
