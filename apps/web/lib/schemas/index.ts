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
  memory: z.object({ enabled: z.boolean(), top_k: z.number(), save_conversations: z.boolean() }).default({ enabled: false, top_k: 10, save_conversations: false }),
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

export const providerKindSchema = z.enum(["openai", "anthropic", "gemini", "openai_compatible", "ollama", "demo"])
export type ProviderKind = z.infer<typeof providerKindSchema>

export const providerSchema = z.object({
  id: z.string(),
  kind: providerKindSchema,
  name: z.string(),
  base_url: z.string().nullable(),
  has_api_key: z.boolean(),
  api_key_last4: z.string().nullable(),
  preset: z.string().nullable().optional(),
  suggested_models: z.array(z.string()).default([]),
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

export const presetSchema = z.object({
  id: z.string(),
  name: z.string(),
  kind: providerKindSchema,
  base_url: z.string().nullable(),
  models: z.array(z.string()),
  signup_url: z.string(),
  free_tier: z.string(),
  needs_key: z.boolean(),
  env_var: z.string(),
  env_configured: z.boolean(),
  provider_id: z.string().nullable(),
})
export type Preset = z.infer<typeof presetSchema>

export const starterPackSchema = z.object({
  created: z.array(z.string()),
  updated: z.array(z.string()),
  skipped: z.array(z.string()),
})

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
  kind: z.enum(["agent", "workflow"]),
  agent_id: z.string(),
  agent_name: z.string(),
  agent_version: z.number().nullable(),
  workflow_id: z.string().nullable().optional(),
  workflow_name: z.string().nullable().optional(),
  workflow_version: z.number().nullable().optional(),
  eval_run_id: z.string().nullable().optional(),
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

// ----- workflows -----
export const stepTypeSchema = z.enum(["agent", "supervisor", "tool", "knowledge", "transform", "condition"])
export type StepType = z.infer<typeof stepTypeSchema>
export const conditionOpSchema = z.enum(["equals", "not_equals", "contains", "not_contains", "regex", "is_empty", "not_empty", "greater_than", "less_than"])
export type ConditionOp = z.infer<typeof conditionOpSchema>

export const workflowStepSchema = z.object({
  id: z.string(),
  type: stepTypeSchema,
  name: z.string(),
  agent_id: z.string().nullable(),
  // optional model override for agent/supervisor steps (null = the agent's own published model)
  model: z.object({ provider_id: z.string(), model: z.string() }).nullable().optional(),
  message: z.string(),
  tool_id: z.string().nullable(),
  arguments: z.record(z.string(), z.unknown()),
  knowledge_base_ids: z.array(z.string()),
  query: z.string(),
  top_k: z.number(),
  template: z.string(),
  condition: z.object({ left: z.string(), op: conditionOpSchema, right: z.string(), case_sensitive: z.boolean() }).nullable(),
  on_true: z.string().nullable(),
  on_false: z.string().nullable(),
  next: z.string().nullable(),
  // supervisor teams (older definitions omit these, so they default)
  role: z.string().default(""),
  delegates: z.array(z.string()).default([]),
  max_rounds: z.number().default(3),
  parallelism: z.number().default(8),
  position: z.object({ x: z.number(), y: z.number() }).nullable().default(null),
})
export type WorkflowStep = z.infer<typeof workflowStepSchema>

export const workflowDefinitionSchema = z.object({
  steps: z.array(workflowStepSchema),
  max_step_executions: z.number(),
  max_delegations: z.number().default(200),
})
export type WorkflowDefinition = z.infer<typeof workflowDefinitionSchema>

export const workflowSchema = z.object({
  id: z.string(),
  workspace_id: z.string(),
  name: z.string(),
  description: z.string(),
  status: z.enum(["draft", "published", "archived"]),
  draft: workflowDefinitionSchema,
  revision: z.number(),
  published_version: z.number().nullable(),
  latest_version: z.number().nullable(),
  draft_dirty: z.boolean(),
  created_by: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type Workflow = z.infer<typeof workflowSchema>

export const workflowVersionSchema = z.object({
  id: z.string(),
  workflow_id: z.string(),
  version: z.number(),
  definition: workflowDefinitionSchema,
  note: z.string(),
  created_by: z.string(),
  created_at: z.string(),
})
export type WorkflowVersion = z.infer<typeof workflowVersionSchema>

export const validationSchema = z.object({ valid: z.boolean(), problems: z.array(z.string()) })

// ----- evaluations -----
export const evalCaseSchema = z.object({ id: z.string(), input: z.string(), expected: z.string(), variables: z.record(z.string(), z.unknown()) })
export type EvalCase = z.infer<typeof evalCaseSchema>

export const datasetSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  cases: z.array(evalCaseSchema),
  case_count: z.number(),
  created_by: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type Dataset = z.infer<typeof datasetSchema>

export const scorerTypeSchema = z.enum(["exact", "contains", "not_contains", "regex", "json_valid", "not_empty"])
export type ScorerType = z.infer<typeof scorerTypeSchema>

export const evalResultSchema = z.object({
  case_id: z.string(),
  input: z.string(),
  expected: z.string(),
  run_id: z.string(),
  status: z.string(),
  output: z.string().nullable(),
  passed: z.boolean().nullable(),
  reason: z.string(),
  latency_ms: z.number().nullable(),
  cost_usd: z.number(),
})
export type EvalResult = z.infer<typeof evalResultSchema>

export const evalRunSchema = z.object({
  id: z.string(),
  name: z.string(),
  dataset_id: z.string(),
  dataset_name: z.string(),
  agent_id: z.string(),
  agent_name: z.string(),
  agent_version: z.number().nullable(),
  source: z.enum(["published", "draft"]),
  scorer: z.object({ type: scorerTypeSchema, case_sensitive: z.boolean() }),
  status: z.enum(["running", "completed"]),
  summary: z.object({
    total: z.number(), finished: z.number(), passed: z.number(), failed: z.number(), errors: z.number(),
    pass_rate: z.number().nullable(), avg_latency_ms: z.number().nullable(), cost_usd: z.number(),
  }),
  results: z.array(evalResultSchema),
  created_by: z.string(),
  created_at: z.string(),
  finished_at: z.string().nullable(),
})
export type EvalRun = z.infer<typeof evalRunSchema>

export const compareSchema = z.object({
  a: evalRunSchema,
  b: evalRunSchema,
  rows: z.array(z.object({
    case_id: z.string(), input: z.string(), expected: z.string(), a: evalResultSchema.nullable(), b: evalResultSchema.nullable(),
    change: z.enum(["fixed", "regressed", "same_pass", "same_fail", "missing"]),
  })),
  fixed: z.number(),
  regressed: z.number(),
})
export type Compare = z.infer<typeof compareSchema>

// ----- memory -----
export const memorySchema = z.object({
  id: z.string(),
  agent_id: z.string(),
  scope: z.string(),
  content: z.string(),
  tags: z.array(z.string()),
  source: z.enum(["manual", "run"]),
  run_id: z.string().nullable(),
  created_by: z.string(),
  created_at: z.string(),
  expires_at: z.string().nullable(),
})
export type Memory = z.infer<typeof memorySchema>
export const memoryScopeSchema = z.object({ agent_id: z.string(), scope: z.string(), count: z.number(), last_at: z.string() })

// ----- billing and analytics -----
export const planSchema = z.object({
  id: z.enum(["self_hosted", "starter", "team", "business"]),
  name: z.string(),
  price_usd: z.number(),
  seats: z.number().nullable(),
  runs_per_month: z.number().nullable(),
  description: z.string(),
})
export type Plan = z.infer<typeof planSchema>

export const billingSchema = z.object({
  plan: planSchema,
  plans: z.array(planSchema),
  period_start: z.string(),
  period_end: z.string(),
  runs_used: z.number(),
  seats_used: z.number(),
  model_cost_usd: z.number(),
  monthly_budget_usd: z.number().nullable(),
  plan_changed_at: z.string().nullable(),
})

export const statementSchema = z.object({
  period: z.string(),
  period_start: z.string(),
  period_end: z.string(),
  current: z.boolean(),
  runs: z.number(),
  model_calls: z.number(),
  input_tokens: z.number(),
  output_tokens: z.number(),
  model_cost_usd: z.number(),
  plan_fee_usd: z.number(),
  total_usd: z.number(),
})
export type Statement = z.infer<typeof statementSchema>

export const timeseriesRowSchema = z.object({ date: z.string(), runs: z.number(), completed: z.number(), failed: z.number(), other: z.number(), tokens: z.number(), cost_usd: z.number() })
export type TimeseriesRow = z.infer<typeof timeseriesRowSchema>

export const breakdownRowSchema = z.object({
  kind: z.enum(["agent", "workflow"]),
  id: z.string(),
  name: z.string(),
  runs: z.number(),
  completed: z.number(),
  failed: z.number(),
  success_rate: z.number().nullable(),
  avg_latency_ms: z.number().nullable(),
  tokens: z.number(),
  cost_usd: z.number(),
})
export type BreakdownRow = z.infer<typeof breakdownRowSchema>
