# Production deployment

A single Linux server (2 vCPU / 4 GB RAM is plenty to start) running Docker. Caddy terminates HTTPS with an
automatic Let's Encrypt certificate; only ports 80 and 443 are exposed.

## 1. Prepare the server

```bash
# Ubuntu/Debian: install Docker Engine + compose plugin (https://docs.docker.com/engine/install/)
sudo mkdir -p /opt/orchestrator && sudo chown $USER /opt/orchestrator
cd /opt/orchestrator   # copy or git clone the project here
```

Point a DNS record (e.g. `ai.example.com`) at the server's public IP and open ports 80 and 443.

## 2. Configure `.env`

```bash
cp .env.example .env
./scripts/new-key.sh            # paste the output into ENCRYPTION_KEYS
```

Set at least:

| Variable | Value |
|---|---|
| `ENCRYPTION_KEYS` | the generated key. **Back it up**: stored provider API keys cannot be decrypted without it. |
| `DOMAIN` | `ai.example.com` |
| `ACME_EMAIL` | an address for certificate expiry notices |
| `ALLOW_REGISTRATION` | `false` once your account exists; teammates then join by invitation |
| `DEMO_MODE` | `false` if you do not want the synthetic Demo provider in workspaces |

`ENVIRONMENT=production`, `COOKIE_SECURE=true`, `PUBLIC_URL` and `CORS_ORIGINS` are set for you by
`docker-compose.prod.yml`. The API refuses to start in production without HTTPS cookies and an encryption key.

## 3. Start

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose ps        # all services healthy
```

Open `https://ai.example.com`, register (the first account is always allowed, even with registration
closed), then **Models → Add provider** with your OpenAI / Anthropic / Gemini key.

Tip: `alias dc='docker compose -f docker-compose.yml -f docker-compose.prod.yml'`.

## 4. Team

- **Invite:** Security → Users → *Invite a teammate*. Copy the link and send it. It works once, for that
  email, for 7 days (`INVITATION_TTL_DAYS`).
- **Roles:** owner > administrator > developer > operator > viewer. Nobody can grant a role above their own.
- **Forgotten password** (no email service needed):
  `docker compose exec api python -m app.cli reset-password person@example.com`
- **Create an account from the shell:** `docker compose exec api python -m app.cli create-user EMAIL "Name" --workspace "Team"`

## 5. Backups

```bash
./scripts/backup.sh                      # -> backups/<timestamp>.archive.gz, keeps the newest 14
crontab -e                               # daily at 03:00:
0 3 * * * cd /opt/orchestrator && ./scripts/backup.sh >> backups/backup.log 2>&1
./scripts/restore.sh backups/<file>      # replaces the database (asks for confirmation)
```

Copy `backups/` and `.env` off the server (object storage, another machine). A backup without the matching
`ENCRYPTION_KEYS` restores everything except stored provider keys.

## 6. Updating

```bash
./scripts/backup.sh
git pull                                  # or copy the new release over the old one, keeping .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Schema changes (indexes, validators) are applied automatically at API startup. Workers finish or release
in-flight runs on shutdown (30 s grace), so updates do not lose runs.

## 7. Scaling and operations

- **Workers:** `WORKER_REPLICAS` (default 2 in production) and `WORKER_CONCURRENCY` (runs per worker).
  Runs are claimed with atomic leases, so any number of workers is safe.
- **Health:** `GET /api/v1/health/ready` (API + MongoDB); `docker compose ps` shows worker health from its
  heartbeat.
- **Logs:** JSON on stdout with a `correlation_id` per request/run: `docker compose logs -f api worker`.
  Secrets are redacted before logging.
- **Rotate the encryption key:** prepend a new key (`ENCRYPTION_KEYS=new,old`), restart api and worker, then
  re-save each provider key in the UI; remove the old key afterwards.
- **MongoDB** is reachable only on the internal Docker network. If you expose it or use a managed cluster
  (Atlas), use authentication and TLS, and set `COMPOSE_MONGODB_URI=mongodb+srv://…` in `.env`; the bundled
  `mongo` service can then be left idle or removed.
