# Implementation Architecture

This describes the code as it exists in `apps/`. The long-range design lives in
`enterprise-ai-orchestration-blueprint.md`; where this implementation deliberately differs
from it (queue engine, gateway), the reason is given below.

## Services

| Service | Process | Why it exists |
|---|---|---|
| `web` | Next.js 16 (App Router), standalone server | UI only. No business logic, no DB access, no API routes or Server Actions. All `/api/*` requests are proxied by a Next.js rewrite to FastAPI, so the browser sees one origin (cookies stay `SameSite=Lax`, no CORS needed). |
| `api` | FastAPI + Uvicorn | Control plane: auth, RBAC, workspaces, agents and versions, model providers, run creation/cancel, SSE event stream, audit, usage. Never executes a model call inside a request. |
| `worker` | `python -m app.workers.main` (same image as `api`) | Executes runs: claims from the MongoDB queue, calls providers, writes events, enforces timeout/cancel/budget. Horizontally scalable. |
| `mongo` | MongoDB 8.0, single-node replica set | The only datastore. Replica set is needed for transactions (registration) and majority writes. |

**Not added:** Redis, Celery, Temporal, a message broker.

### Durable execution: MongoDB lease queue (chosen) vs alternatives

Requirements: survive API restarts and worker crashes, real cancellation, timeouts, bounded retries,
idempotent submission, streaming progress, zero extra infrastructure for demo mode.

| Option | Verdict |
|---|---|
| Temporal | Best long-term fit for multi-step workflows with human approval and long sleeps (the blueprint's target). Adds a server + its own database. Deferred until the workflow engine lands; the run/event model maps onto it. |
| Celery / RQ / ARQ | Need Redis or RabbitMQ; cancellation of in-flight async I/O is weak (revoke/terminate kills processes); state would be split between broker and MongoDB. |
| **MongoDB leases (implemented)** | Run documents are the queue. A worker atomically claims (`find_one_and_update` queued→running with `lease_owner` + `lease_expires_at`), renews the lease every second, and the same read checks `cancel_requested` and the deadline. One source of truth, no new service. Throughput ceiling is far above what single-step agent runs need at this stage. |

### Run lifecycle

`queued → running → (waiting_for_approval, reserved for workflows) → completed | failed | cancelled | timed_out`

- **Submission:** `POST /api/v1/runs` validates, checks budgets, snapshots the exact config
  (published version or draft), inserts `queued`, returns `202`. Optional `Idempotency-Key`
  header (unique per workspace) returns the existing run on retry.
- **Cancellation:** `POST /runs/{id}/cancel` sets `cancel_requested`. The worker's supervisor sees it
  within ~1 s, cancels the executing coroutine (closing the HTTP request to the provider), and writes
  `cancelled`. Queued runs are cancelled immediately. Verified end-to-end: 0.6 s from request to `cancelled`.
- **Timeout:** per-run `timeout_seconds` (capped by `MAX_RUN_TIMEOUT_SECONDS`) is a deadline enforced by
  the supervisor, which also cancels the provider call → `timed_out`. Provider adapters additionally have
  their own HTTP timeout.
- **Retries:** adapters never retry (project rule: no hidden retries for budgeted calls). The explicit
  fallback chain is tried once per entry. Whole-run re-execution happens only on lease expiry
  (worker crash), bounded by `max_attempts = 2`.

### Failure modes

| Event | Behavior |
|---|---|
| API restart | No effect on running work (runs live in the worker). SSE clients reconnect with `Last-Event-ID` and resume from the next `seq`. |
| Worker crash | Lease expires (30 s). Any worker re-queues the run with backoff if `attempt < max_attempts`, else marks it `failed` (`WORKER_LOST`). A `run.lease_expired` event is recorded. |
| Worker SIGTERM | Stops claiming, cancels in-flight runs and releases them to `queued` without consuming an attempt. |
| MongoDB down | API returns `503` with the error envelope; `/health/ready` reports it. Worker claim/heartbeat fail and back off; in-flight runs whose lease cannot be renewed are recovered after Mongo returns. |
| Provider timeout/error | Recorded as `model.error` (redacted), a usage record is written, next fallback is tried; if the chain is exhausted the run is `failed` with `PROVIDER_UNAVAILABLE`. |

## Security

- Passwords: Argon2id. Sessions: random 256-bit token in an `HttpOnly` cookie; only its SHA-256 is stored
  (TTL index). CSRF: double-submit cookie (`orch_csrf` + `X-CSRF-Token`) on all mutating requests.
- Workspace isolation: the client sends `X-Workspace-Id`, but it is never trusted. Each request verifies
  membership and every repository query is scoped by `workspace_id` (`ScopedRepository`). Non-members
  get `404 WORKSPACE_NOT_FOUND` (no existence oracle). Covered by `tests/test_isolation_rbac.py`.
- RBAC: owner, administrator, developer, operator, viewer; permission matrix in `app/services/rbac.py`,
  enforced by `require(perm)` on every protected route. The UI mirror (`lib/workspace-context.tsx`) only
  hides controls.
- Provider keys: encrypted with `MultiFernet` (`ENCRYPTION_KEYS`, rotation by prepending a new key),
  write-only in the API, responses expose `has_api_key` and `api_key_last4` only. Logs, events, and run
  errors pass through redaction (a test reproduces a provider echoing the key).
- Rate limits: login and register per IP (MongoDB TTL counters). Request body size limit. Security headers
  set by Next.js.
- Team onboarding: single-use invitation links (token stored as SHA-256, 7-day expiry, bound to one email,
  role capped at the inviter's). `ALLOW_REGISTRATION=false` closes self-service sign-up except for the very
  first account and invitation holders. Password change revokes the user's other sessions. Operators can
  `python -m app.cli create-user|reset-password|list-users` without an email service.
- API keys: workspace-scoped bearer tokens (`orch_…`, only the SHA-256 stored), role capped at the creator's,
  optional expiry, revocable, `last_used_at` tracked. A key is pinned to its workspace (`X-Workspace-Id` for
  another workspace gets 404) and cannot mint further keys. Requests with a bearer key carry no cookies, so
  CSRF does not apply to them.
- Not done: SSO/MFA, outbound email, tool sandbox (no tool execution exists yet), external security review.

## Model gateway

Direct `httpx` adapters per provider (`app/providers/`) instead of LiteLLM: each provider's native request
format (OpenAI Chat Completions, Anthropic Messages with `anthropic-version`, Gemini `generateContent`
with `x-goog-api-key`, any OpenAI-compatible base URL) with explicit error classification
(auth / rate_limit / timeout / bad_request / server) and no internal retries. That keeps the
"no hidden retries" and redaction guarantees auditable. Demo provider: deterministic, $0, labeled.

## MongoDB collections

IDs are prefixed ULIDs (`usr_`, `ws_`, `agt_`, `run_`...). All tenant data carries `workspace_id`.
Validators (`$jsonSchema`, `validationLevel: moderate`) enforce required fields and enums; Pydantic models
enforce full validation before writes. Defined in `apps/api/app/db/indexes.py`, applied idempotently at startup.

| Collection | Key fields | Indexes | Retention / growth | Sensitive |
|---|---|---|---|---|
| `users` | `_id`, `email`, `name`, `password_hash`, `created_at` | `email` unique | Permanent; small | `password_hash` (Argon2id, never returned) |
| `sessions` | `_id` (= token SHA-256), `user_id`, `expires_at` | TTL on `expires_at`, `user_id` | Auto-deleted at expiry | Token hash |
| `workspaces` | `_id`, `name`, `owner_id`, `monthly_budget_usd` | `_id` | Permanent; small | — |
| `workspace_members` | `workspace_id`, `user_id`, `role`, `joined_at` | (`workspace_id`,`user_id`) unique; `user_id` | Permanent | — |
| `agents` | `_id`, `workspace_id`, `name`, `name_lower`, `status`, `draft` (config), `revision` (optimistic lock), `published_version`, `deleted` | (`workspace_id`,`updated_at`); (`workspace_id`,`name_lower`) unique where not deleted | Soft delete | System prompts may contain business data |
| `agent_versions` | `agent_id`, `workspace_id`, `version`, immutable `config`, `config_hash` (SHA-256 of canonical JSON), `note`, `created_by` | (`agent_id`,`version`) unique; `workspace_id` | Permanent, append-only; grows per publish | As agents |
| `model_providers` | `workspace_id`, `kind`, `name`, `base_url`, `api_key_enc`, `api_key_last4`, `allowed_models`, `timeout_seconds`, `pricing`, `health`, `enabled` | (`workspace_id`,`name`) unique | Hard delete | `api_key_enc` (Fernet, never returned) |
| `runs` | `workspace_id`, `agent_id`, `agent_version`/`source`, `config` snapshot, `input`, `status`, `attempt`, `max_attempts`, lease fields, `cancel_requested`, `deadline_at`, `output`, `error`, `usage`, `event_seq`, `idempotency_key`, `demo` | (`workspace_id`,`created_at`); (`workspace_id`,`status`,`created_at`); (`status`,`available_at`) claim; (`status`,`lease_expires_at`) recovery; (`workspace_id`,`idempotency_key`) unique partial | Grows per run; archival policy not implemented | User inputs/outputs |
| `run_events` | `run_id`, `workspace_id`, `seq`, `type`, `ts`, `data` (redacted) | (`run_id`,`seq`) unique; TTL on `ts` (`RUN_EVENTS_RETENTION_DAYS`, 90) | Highest growth; TTL-bounded | Redacted at write |
| `audit_logs` | `workspace_id`, `actor_id`, `action`, `target_type`, `target_id`, `details`, `ts` | (`workspace_id`,`ts`); TTL (`AUDIT_RETENTION_DAYS`, 365) | Append-only, TTL-bounded | No secret values recorded |
| `usage_records` | `workspace_id`, `run_id`, `provider_id`, `model`, tokens, `cost_usd`, `priced`, `latency_ms`, `ok`, `ts` | (`workspace_id`,`ts`); `run_id` | One per provider attempt; no TTL (billing) | — |
| `rate_limits` | `_id` (key+window), `count`, `expires_at` | TTL | Ephemeral | Client IP inside the key (expires within minutes) |
| `invitations` | `workspace_id`, `email`, `role`, `token_hash`, `status` (pending/accepted/revoked/superseded), `expires_at` | `token_hash` unique; (`workspace_id`,`status`) | Small; kept for audit | Token hash only |
| `api_keys` | `workspace_id`, `name`, `role`, `key_hash`, `prefix`, `revoked`, `last_used_at`, `expires_at` | `key_hash` unique; (`workspace_id`,`revoked`) | Small; revoked keys kept for audit | Key hash only |

| `tools` | `workspace_id`, `name`, `name_lower`, `description`, `kind` (http/mcp), `input_schema`, `http` (method, url, timeout), `mcp` (server_url, tool_name), `headers`, `secret_headers_enc`, `secret_header_names`, `enabled`, `deleted` | (`workspace_id`,`name_lower`) unique where not deleted | Soft delete | `secret_headers_enc` (Fernet, never returned or sent to models) |
| `knowledge_bases` | `workspace_id`, `name`, `embedding` (provider_id, model) or null for lexical, `doc_count`, `chunk_count`, `version` | (`workspace_id`,`name_lower`) unique | Hard delete with its documents and chunks | — |
| `documents` | `workspace_id`, `kb_id`, `title`, `filename`, `source`, `bytes`, `blob_id` (GridFS `document_blobs`), `status` (queued/processing/ready/failed), lease fields, `error`, `chunk_count` | (`workspace_id`,`kb_id`,`created_at`); (`status`,`available_at`) claim | Grows per upload | Document content |
| `chunks` | `workspace_id`, `kb_id`, `doc_id`, `n`, `text`, `vector` (float32 binary) | (`workspace_id`,`kb_id`); `doc_id` | Rebuilt on reindex | Document content |

Retrieval: the worker extracts text, splits it into overlapping paragraph-aware chunks
(`KNOWLEDGE_CHUNK_CHARS`/`KNOWLEDGE_CHUNK_OVERLAP`) and embeds them with the knowledge base's provider,
or with a built-in feature-hashing lexical vector when none is configured. Search is cosine similarity
in the API/worker process over a per-knowledge-base matrix cached until the knowledge base changes.
This needs no Atlas Vector Search and works on any MongoDB; past roughly 100k chunks per knowledge base,
move to Atlas Vector Search or a dedicated vector store.

Tools: the executor offers only the agent's allowlisted, enabled tools; each call is validated
against the tool's JSON Schema, executed with a timeout and response-size cap, and recorded as
`tool.call`/`tool.result` events (arguments redacted). Outbound tool and MCP requests resolve the host
first and refuse private, loopback and link-local addresses unless `TOOLS_ALLOW_PRIVATE_NETWORKS=true`.

Workflows: `workflows` (draft definition + `revision`, soft delete) and append-only `workflow_versions`
mirror agents. A workflow run is an ordinary `runs` document with `kind="workflow"`, so the worker's
leases, heartbeat, cancellation, timeouts and SSE apply unchanged; `WorkflowExecutor` walks the steps,
runs agent steps through `AgentExecutor` with the workflow run as parent (usage and events land on it),
and bounds loops with `max_step_executions`. Templates are dotted-path lookups only (no expressions).

Evaluations: `eval_datasets` hold up to 500 cases; an `eval_runs` document queues one agent run per case
(tagged `eval_run_id`) and is scored on read until every case run is terminal, then frozen.

Memory: `memories` (`agent_id`, `scope`, `content`, optional `expires_at` with a TTL index). When an
agent's `config.memory.enabled` is set, the newest `top_k` memories of scopes `global` + `input.memory_scope`
are added to the system prompt (`memory.loaded` event); `save_conversations` stores each exchange.

Billing: the plan lives in `workspaces.settings.plan` (default `self_hosted`, unlimited). Run quotas are
checked when any run is queued and seat limits when members or invitations are added. Statements are
aggregated from `usage_records` and `runs` per UTC month.

Transactions are used only where atomicity across collections matters: registration (user + workspace +
owner membership). Publishing uses the agent `revision` for optimistic concurrency plus the unique
(`agent_id`,`version`) index instead of a transaction.

## Frontend

Next.js 16 App Router with `cacheComponents` (Partial Prerendering). Pages are client components fed by
TanStack Query through one typed client (`lib/api-client.ts`), which validates every response with Zod
and attaches workspace and CSRF headers; components never call `fetch` directly. Forms use
React Hook Form + Zod. UI primitives: shadcn/ui (Base UI flavor). Zustand is not used: server state lives
in TanStack Query, and the only client state (current workspace) is a small context. Navigation entries
carry a status (`available`, `partial`, `in_development`); every module is now `available`. The
`InDevelopment` component remains for future modules that are routed before they are built.

## Dependency versions

Pinned exactly in `apps/api/pyproject.toml` + `uv.lock` (exported to `requirements.txt`) and
`apps/web/package.json` + `package-lock.json`.

- Python 3.12+ (developed and tested on 3.14): FastAPI 0.162.0, Uvicorn 0.54.0, Pydantic 2.14.1,
  pydantic-settings 2.16.1, PyMongo 4.19.0 (native async API), httpx 0.28.1, argon2-cffi 25.1.0,
  cryptography 50.0.2, jsonschema 4.26.0. Dev: pytest 9.1.1, pytest-asyncio 1.4.1, ruff 0.17.3.
- Node 20.9+ (tested on 20.20; Docker image uses 22): Next 16.4.3, React 19.3.0, TanStack Query 5.105.0,
  Zod 4.6.7, React Hook Form 7.91.0, Tailwind 4.3.3, TypeScript 5.9.3, Base UI 1.9.0, sonner 2.0.8.
  Tests: Vitest 3.2.7 (current Vitest 5 requires Node 22.12+; 3.2 keeps Node 20 LTS working, upgrade path is 4.x then 5.x), jsdom 26.1.0,
  Testing Library, axe-core 4.14.0, Playwright 1.59.1.
- `@xyflow/react` (React Flow) is not installed yet: it arrives with the workflow editor.
