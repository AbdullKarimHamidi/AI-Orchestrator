# AI Orchestration Platform

Self-hosted platform for building, versioning and running AI agents with your team: Next.js frontend,
FastAPI control plane, a separate background worker for durable execution, and MongoDB. It runs fully in
**demo mode** without any paid service (a clearly labeled synthetic provider returns `[DEMO]` output at $0),
and with real OpenAI, Anthropic, Gemini or any OpenAI-compatible endpoint once you add a key.

User guide (PDF): [`docs/user-guide.pdf`](docs/user-guide.pdf) · Architecture: [`docs/architecture.md`](docs/architecture.md) · Production: [`docs/deployment.md`](docs/deployment.md)
· Long-range design: [`enterprise-ai-orchestration-blueprint.md`](enterprise-ai-orchestration-blueprint.md)

## What works today

| Area | Status |
|---|---|
| Auth: register, sign in/out, change password, Argon2id, HttpOnly session cookie, CSRF, rate limits | Implemented |
| Teams: workspaces (several per user), five roles, RBAC enforced in FastAPI, invitation links, closed registration, operator CLI | Implemented (no SSO/MFA or outbound email) |
| API keys: workspace-scoped, role-capped, expiring, revocable; `POST /runs?wait_seconds=` for synchronous calls | Implemented |
| Agents: CRUD, clone, draft → publish (immutable versions) → pause/resume/retire, compare, rollback, model + fallbacks, params, I/O schemas, limits/budgets, test console | Implemented |
| Runs: queued in MongoDB, executed by the worker, SSE live events, cancellation, timeouts, crash recovery, idempotency | Implemented |
| Model gateway: OpenAI, Anthropic, Gemini, OpenAI-compatible adapters, encrypted keys, test connection, allowlists, health, usage and cost | Implemented |
| Dashboard, analytics, audit log, workspace settings and budget | Implemented |
| Production: HTTPS via Caddy, health checks, backups/restore, CI (lint, tests, build, browser E2E) | Implemented |
| Tools: HTTP API tools and tools imported from remote MCP servers (Streamable HTTP), encrypted credentials, schema-validated calls, SSRF guard, test console, per-agent allowlist, tool calling on OpenAI, Anthropic and Gemini | Implemented |
| Knowledge (RAG): knowledge bases, upload PDF/DOCX/Markdown/HTML/CSV/JSON/text or paste text, background ingestion in the worker, OpenAI/Gemini/compatible embeddings or a built-in lexical index, search test, retrieved passages cited in run output | Implemented (in-process vector search; fine up to ~100k chunks per knowledge base) |
| Workflows: step editor (agent, tool, knowledge search, transform, condition with true/false routes), strict `{{ templates }}`, loop guard, draft → publish immutable versions, archive, runs in the worker with per-step events, `POST /workflows/{id}/runs` | Implemented (linear steps with routing; no parallel branches or human approval yet) |
| Evaluations: datasets of cases (editor + bulk import), evaluation runs of a published or draft agent, scorers (contains, exact, regex, JSON valid, not empty), live pass rate, case-by-case comparison of two runs | Implemented |
| Memory: per-agent memories in a global or per-end-user scope, optional TTL, injection into the prompt, automatic saving of conversations, "forget this scope" deletion requests | Implemented |
| Billing: plans with seat and monthly run quotas enforced by the API, monthly usage statements (plan fee + model spend) with CSV export | Implemented (internal chargeback; no payment processor) |
| Analytics: runs per day by outcome, per agent / workflow breakdown, per provider / model usage and cost | Implemented |

## Quick start

Prerequisite: Docker (Docker Desktop on Windows/macOS).

```bash
# Linux / macOS
./scripts/dev.sh             # creates .env with a fresh ENCRYPTION_KEYS, builds, starts all 4 services
./scripts/dev.sh --down      # stop
```

```powershell
# Windows (PowerShell)
./scripts/dev.ps1            # same as above
./scripts/dev.ps1 -Down
```

Open <http://localhost:3000>, register, then **Agents → New agent → provider "Demo" → Test console**.
API docs (Swagger) are at <http://localhost:8000/api/docs>.

Database: the project uses MongoDB Atlas. Set `MONGODB_URI` (and `MONGODB_DB=AI`) in `.env`; with Docker, set
`COMPOSE_MONGODB_URI` to the same value so the containers use Atlas instead of the bundled `mongo` service.
Atlas must allow connections from your IP (Network Access in the Atlas console).

Manual equivalent: `cp .env.example .env`, put the output of `./scripts/new-key.sh` into `ENCRYPTION_KEYS`,
then `docker compose up --build -d`.

### Without Docker (`--local` / `-Local`)

Needs [uv](https://docs.astral.sh/uv/), Node.js 20.9+ and a MongoDB 8 **replica set** (transactions need one):

```bash
mongod --replSet rs0 --dbpath ./data --bind_ip 127.0.0.1 --port 27017
mongosh --eval "rs.initiate({_id:'rs0',members:[{_id:0,host:'127.0.0.1:27017'}]})"
./scripts/dev.sh --local     # API :8000, worker, web :3000 (Windows: ./scripts/dev.ps1 -Local)
```

## Using it with a team

1. Deploy once on a server: [`docs/deployment.md`](docs/deployment.md) (HTTPS, backups, updates).
2. Register the first account, add a real provider under **Models**, then set `ALLOW_REGISTRATION=false`.
3. Invite people from **Security → Users**. Each gets a single-use link for their email and a role
   (owner, administrator, developer, operator, viewer).
4. Developers build and publish agents; operators run them; viewers read results; every change is audited.

## Calling agents from your own code

Create a key under **Settings → API keys** (role `operator` is enough to run published agents), then:

```bash
curl -X POST "https://ai.example.com/api/v1/runs?wait_seconds=30" \
  -H "Authorization: Bearer orch_..." -H "Content-Type: application/json" \
  -d '{"agent_id": "agt_...", "input": {"message": "Summarize this ticket: ..."}}'
```

The response is the run. `status` is `completed` with `output.text` when it finished within the wait,
otherwise poll `GET /api/v1/runs/{id}` or stream `GET /api/v1/runs/{id}/stream` (Server-Sent Events).
Send an `Idempotency-Key` header to make retries safe.

```python
import httpx

r = httpx.post("https://ai.example.com/api/v1/runs", params={"wait_seconds": 30},
               headers={"Authorization": "Bearer orch_..."},
               json={"agent_id": "agt_...", "input": {"message": "Hello"}}, timeout=40)
run = r.json()
print(run["status"], (run["output"] or {}).get("text"))
```

## Tests and checks

```bash
./scripts/test.sh            # ruff + pytest (needs the replica set above), tsc, eslint, vitest, next build
./scripts/test.sh --e2e      # plus the Playwright browser journeys against http://localhost:3000
# Windows: ./scripts/test.ps1 [-E2E]
```

Backend tests create a throwaway database `orch_test_<random>` and drop it afterwards. GitHub Actions runs
all of it, including the browser journeys against the full Docker stack (`.github/workflows/ci.yml`).

## Configuration

All settings are environment variables, documented in [`.env.example`](.env.example) (never commit `.env`).
`ENCRYPTION_KEYS` must be identical for the API and the worker, and must be backed up. Real provider API keys
are entered in the UI, encrypted at rest, and never sent back to the browser.

## Repository layout

```
apps/api      FastAPI app (app/api/v1 thin routers -> services -> repositories), providers, worker, CLI, tests
apps/web      Next.js app (app/(auth), app/(platform)), components, lib/api-client.ts, hooks, tests, e2e
deploy/       Caddyfile for the production overlay (docker-compose.prod.yml)
docs/         architecture, deployment
companions/   OpenAPI reference contract, workflow DSL schema, fixtures (specification set, below)
scripts/      dev / test / new-key (.sh and .ps1), backup / restore, gen_openapi.py
```

---

## Specification set
Machine-validated specification set for an enterprise-grade AI orchestration
platform. This is the canonical working context for the Perplexity Project
"AI Orchestration Platform — Architecture & Specs"; future sessions should
treat these files as the source of truth and re-run the validation checks
after any change.

### Contents

| File | What it is |
|---|---|
| `enterprise-ai-orchestration-blueprint.md` | The 27-section architecture blueprint: product scope, cited research, competitive comparison, stack rationale, Mermaid architecture diagrams, control/execution planes, repository structure, ~60-route frontend inventory, screen-by-screen UI/UX, design system, agent lifecycle, multi-agent orchestration, workflow editor spec, model gateway, tools/MCP, memory/RAG, ~30-collection MongoDB model, REST/SSE contracts, run state machine and failure recovery, authn/authz, observability/eval/cost, testing, deployment, 11-phase roadmap, risks, and a prioritized checklist. |
| `companions/openapi.yaml` | Reference API contract — 118 paths, 171 operations, validated against the OpenAPI 3.1 spec. 147 operations return typed envelopes; deletes return 204; SSE endpoints declare Last-Event-ID; POST /runs declares Idempotency-Key. Its `WorkflowDef` is imported from the canonical workflow schema. |
| `companions/workflow-definition.schema.json` | Canonical workflow DSL (JSON Schema 2020-12): 17 node types, failure-outcome terminals, bounded loops with exhaustion policies, embedded machine-verified example. The OpenAPI contract imports this schema — do not redefine it. |
| `companions/examples/negative-fixtures.json` | 9 single-mutation rejection tests derived from the verified example, each machine-checked to be rejected with its expected error code. |
| `companions/eval-sample-report.md` | Illustrative release-gate evaluation report with a per-sample ledger (figures are illustrative, not measured results). |
| `scripts/gen_openapi.py` | Regenerates `companions/openapi.yaml` from the route inventory (run from the repo root: `python3 scripts/gen_openapi.py`). |

### Validation status

Executed and passing at publication time: OpenAPI 3.1 validator (118 paths /
171 operations); workflow example passes JSON Schema validation, graph rules,
JSON-Logic condition parsing, and Jinja StrictUndefined rendering, and
validates identically against both the schema and the OpenAPI contract; all
9 negative fixtures reject with their expected error codes; all 5 Mermaid
diagrams parse; the eval report's counts, intervals, and verdict derive from
one per-sample ledger.

This validates specification syntax and the documented examples — it does not
establish runtime correctness or production readiness, and no runtime
implementation exists yet.

### Architectural invariants (must hold in future work)

- MongoDB remains the primary application database.
- No long-running AI execution inside synchronous request handlers.
- No orchestration logic in Next.js.
- Gateway auto-retries/fallbacks stay disabled for budgeted calls (interpreter
  schedules explicit, separately budgeted attempts).
- Conditions are JSON-Logic; templates and input mappings are sandboxed Jinja.
- Every workflow cycle must pass through a bounded loop controller.
