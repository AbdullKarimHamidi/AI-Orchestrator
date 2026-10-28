/**
 * Zod schemas mirroring the FastAPI response contract (apps/api/app/schemas).
 * Responses are parsed at the boundary so contract drift fails loudly in one place.
 */
import { z } from "zod"

export const roleSchema = z.enum(["owner", "administrator", "developer", "operator", "viewer"])
export type Role = z.infer<typeof roleSchema>

export const meSchema = z.object({
  user: z.object({ id: z.string(), email: z.string(), name: z.string(), created_at: z.string() }),
  memberships: z.array(z.object({ workspace_id: z.string(), workspace_name: z.string(), role: roleSchema })),
  demo_mode: z.boolean(),
})
export type Me = z.infer<typeof meSchema>

export const pageOf = <T extends z.ZodTypeAny>(item: T) =>
  z.object({ items: z.array(item), total: z.number(), limit: z.number(), offset: z.number() })

export const modelRefSchema = z.object({ provider_id: z.string().min(1), model: z.string().min(1) })

export const agentConfigSchema = z.object({
  system_prompt: z.string(),
  model: modelRefSchema.nullable(),
  fallbacks: z.array(modelRefSchema),
  params: z.object({
    temperature: z.number().nullable(),
    top_p: z.number().nullable(),
    max_output_tokens: z.number(),
  }),
  tool_ids: z.array(z.string()),
  knowledge_base_ids: z.array(z.string()),
  knowledge_top_k: z.number().default(5),
  input_schema: z.record(z.string(), z.unknown()).nullable(),
  output_schema: z.record(z.string(), z.unknown()).nullable(),
  limits: z.object({ timeout_seconds: z.number(), max_cost_usd_per_run: z.number().nullable(), max_tool_calls: z.number().default(8) }),
})
export type AgentConfig = z.infer<typeof agentConfigSchema>

export const agentStatusSchema = z.enum(["draft", "published", "paused", "retired"])
export type AgentStatus = z.infer<typeof agentStatusSchema>

export const agentSchema = z.object({
  id: z.string(),
  workspace_id: z.string(),
  name: z.string(),
  description: z.string(),
  status: agentStatusSchema,
  draft: agentConfigSchema,
  revision: z.number(),
  published_version: z.number().nullable(),
  latest_version: z.number().nullable(),
  draft_dirty: z.boolean(),
  created_by: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type Agent = z.infer<typeof agentSchema>

export const agentVersionSchema = z.object({
  id: z.string(),
  agent_id: z.string(),
  version: z.number(),
  config: agentConfigSchema,
  config_hash: z.string(),
  note: z.string(),
  created_by: z.string(),
  created_at: z.string(),
})
export type AgentVersion = z.infer<typeof agentVersionSchema>

export const versionDiffSchema = z.object({
  from_version: z.number(),
  to_version: z.number(),
  changes: z.array(z.object({ path: z.string(), from: z.unknown(), to: z.unknown() })),
})

export const providerKindSchema = z.enum(["openai", "anthropic", "gemini", "openai_compatible", "demo"])
export type ProviderKind = z.infer<typeof providerKindSchema>

export const providerSchema = z.object({
  id: z.string(),
  kind: providerKindSchema,
  name: z.string(),
  base_url: z.string().nullable(),
  has_api_key: z.boolean(),
  api_key_last4: z.string().nullable(),
  allowed_models: z.array(z.string()),
  timeout_seconds: z.number(),
  enabled: z.boolean(),
  pricing: z.record(z.string(), z.object({ input_per_mtok_usd: z.number(), output_per_mtok_usd: z.number() })),
  health: z.object({
    status: z.enum(["unknown", "healthy", "unhealthy"]),
    checked_at: z.string().nullable().optional(),
    latency_ms: z.number().nullable().optional(),
    error: z.string().nullable().optional(),
  }),
  created_at: z.string(),
  updated_at: z.string(),
})
export type Provider = z.infer<typeof providerSchema>

export const connectionTestSchema = z.object({
  ok: z.boolean(),
  latency_ms: z.number(),
  models: z.array(z.string()),
  error: z.string().nullable(),
})

export const usageRowSchema = z.object({
  provider_id: z.string(),
  model: z.string(),
  calls: z.number(),
  errors: z.number(),
  input_tokens: z.number(),
  output_tokens: z.number(),
  cost_usd: z.number(),
  avg_latency_ms: z.number().nullable(),
  unpriced: z.number(),
})

export const runStatusSchema = z.enum([
  "queued", "running", "waiting_for_approval", "completed", "failed", "cancelled", "timed_out",
])
export type RunStatus = z.infer<typeof runStatusSchema>
export const TERMINAL_STATUSES: RunStatus[] = ["completed", "failed", "cancelled", "timed_out"]

export const runSchema = z.object({
  id: z.string(),
  workspace_id: z.string(),
  kind: z.literal("agent"),
  agent_id: z.string(),
  agent_name: z.string(),
  agent_version: z.number().nullable(),
  source: z.enum(["published", "draft"]),
  status: runStatusSchema,
  demo: z.boolean(),
  input: z.record(z.string(), z.unknown()),
  output: z.record(z.string(), z.unknown()).nullable(),
  error: z.object({ code: z.string(), message: z.string() }).nullable(),
  usage: z.object({ input_tokens: z.number(), output_tokens: z.number(), cost_usd: z.number() }),
  attempt: z.number(),
  max_attempts: z.number(),
  cancel_requested: z.boolean(),
  timeout_seconds: z.number(),
  created_by: z.string(),
  created_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  duration_ms: z.number().nullable(),
  config: z.record(z.string(), z.unknown()),
})
export type Run = z.infer<typeof runSchema>

export const runEventSchema = z.object({
  seq: z.number(),
  type: z.string(),
  ts: z.string(),
  data: z.record(z.string(), z.unknown()),
})
export type RunEvent = z.infer<typeof runEventSchema>

export const dashboardSchema = z.object({
  window_days: z.number(),
  agents_total: z.number(),
  agents_published: z.number(),
  runs_total: z.number(),
  runs_by_status: z.record(z.string(), z.number()),
  success_rate: z.number().nullable(),
  p50_latency_ms: z.number().nullable(),
  p95_latency_ms: z.number().nullable(),
  cost_usd: z.number(),
  input_tokens: z.number(),
  output_tokens: z.number(),
  demo_runs: z.number(),
  monthly_budget_usd: z.number().nullable(),
  month_to_date_cost_usd: z.number(),
  recent_runs: z.array(runSchema),
  providers_total: z.number(),
  providers_unhealthy: z.number(),
})
export type Dashboard = z.infer<typeof dashboardSchema>

export const workspaceSchema = z.object({
  id: z.string(),
  name: z.string(),
  role: roleSchema,
  monthly_budget_usd: z.number().nullable(),
  created_at: z.string(),
})

export const memberSchema = z.object({
  user_id: z.string(),
  email: z.string(),
  name: z.string(),
  role: roleSchema,
  joined_at: z.string(),
})
export type Member = z.infer<typeof memberSchema>

export const auditEntrySchema = z.object({
  id: z.string(),
  action: z.string(),
  actor_id: z.string().nullable(),
  target_type: z.string().nullable(),
  target_id: z.string().nullable(),
  details: z.record(z.string(), z.unknown()),
  ip: z.string().nullable(),
  ts: z.string(),
})

export const rolesSchema = z.array(z.object({ role: roleSchema, permissions: z.array(z.string()) }))

export const authConfigSchema = z.object({ registration_open: z.boolean(), demo_mode: z.boolean() })

export const invitationSchema = z.object({
  id: z.string(),
  email: z.string(),
  role: roleSchema,
  invited_by: z.string(),
  created_at: z.string(),
  expires_at: z.string(),
})
export type Invitation = z.infer<typeof invitationSchema>
export const invitationCreatedSchema = invitationSchema.extend({ token: z.string(), url: z.string() })

export const invitationInfoSchema = z.object({
  email: z.string(),
  role: roleSchema,
  workspace_name: z.string(),
  expires_at: z.string(),
  has_account: z.boolean(),
})
export type InvitationInfo = z.infer<typeof invitationInfoSchema>

export const apiKeySchema = z.object({
  id: z.string(),
  name: z.string(),
  role: roleSchema,
  prefix: z.string(),
  created_by: z.string(),
  created_at: z.string(),
  last_used_at: z.string().nullable(),
  expires_at: z.string().nullable(),
})
export type ApiKey = z.infer<typeof apiKeySchema>
export const apiKeyCreatedSchema = apiKeySchema.extend({ key: z.string() })

export const toolSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  kind: z.enum(["http", "mcp"]),
  input_schema: z.record(z.string(), z.unknown()),
  http: z.object({ method: z.enum(["GET", "POST", "PUT", "PATCH", "DELETE"]), url: z.string(), timeout_seconds: z.number().nullable() }).nullable(),
  mcp: z.object({ server_url: z.string(), tool_name: z.string() }).nullable(),
  headers: z.record(z.string(), z.string()),
  secret_header_names: z.array(z.string()),
  enabled: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type Tool = z.infer<typeof toolSchema>

export const toolTestSchema = z.object({ ok: z.boolean(), output: z.string().nullable(), error: z.string().nullable(), latency_ms: z.number() })

export const mcpRemoteToolSchema = z.object({ name: z.string(), description: z.string(), input_schema: z.record(z.string(), z.unknown()) })
export type McpRemoteTool = z.infer<typeof mcpRemoteToolSchema>

export const knowledgeBaseSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  embedding: z.object({ provider_id: z.string(), model: z.string() }).nullable(),
  doc_count: z.number(),
  chunk_count: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type KnowledgeBase = z.infer<typeof knowledgeBaseSchema>

export const documentStatusSchema = z.enum(["queued", "processing", "ready", "failed"])
export const documentSchema = z.object({
  id: z.string(),
  kb_id: z.string(),
  title: z.string(),
  filename: z.string().nullable(),
  source: z.enum(["upload", "text"]),
  bytes: z.number(),
  status: documentStatusSchema,
  error: z.string().nullable(),
  chunk_count: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type KnowledgeDocument = z.infer<typeof documentSchema>

export const searchHitSchema = z.object({ kb_id: z.string(), doc_id: z.string(), title: z.string(), chunk: z.number(), text: z.string(), score: z.number() })
export type SearchHit = z.infer<typeof searchHitSchema>
