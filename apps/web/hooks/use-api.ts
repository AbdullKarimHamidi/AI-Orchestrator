"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"

import { api } from "@/lib/api-client"
import {
  agentSchema, agentVersionSchema, apiKeyCreatedSchema, apiKeySchema, auditEntrySchema, authConfigSchema,
  connectionTestSchema, dashboardSchema, documentSchema, invitationCreatedSchema, invitationSchema, knowledgeBaseSchema,
  mcpRemoteToolSchema, meSchema, searchHitSchema, toolSchema, toolTestSchema,
  memberSchema, pageOf, presetSchema, providerSchema, rolesSchema, runEventSchema, runSchema, TERMINAL_STATUSES,
  starterPackSchema, usageRowSchema, versionDiffSchema, workspaceSchema,
  type Agent, type AgentConfig, type Role, type Run,
} from "@/lib/schemas"

export const qk = {
  me: ["me"] as const,
  dashboard: (ws: string | null, days: number) => ["dashboard", ws, days] as const,
  agents: (ws: string | null, params?: object) => ["agents", ws, params ?? {}] as const,
  agent: (ws: string | null, id: string) => ["agent", ws, id] as const,
  versions: (ws: string | null, id: string) => ["agent-versions", ws, id] as const,
  providers: (ws: string | null) => ["providers", ws] as const,
  runs: (ws: string | null, params?: object) => ["runs", ws, params ?? {}] as const,
  run: (ws: string | null, id: string) => ["run", ws, id] as const,
}

export function useMe() {
  return useQuery({ queryKey: qk.me, queryFn: () => api.get("/auth/me", meSchema), retry: false, staleTime: 60_000 })
}

export function useDashboard(ws: string | null, days: number) {
  return useQuery({ queryKey: qk.dashboard(ws, days), queryFn: () => api.get("/dashboard", dashboardSchema, { query: { days } }), enabled: !!ws, refetchInterval: 15_000 })
}

export function useAgents(ws: string | null, params: { q?: string; status?: string } = {}) {
  return useQuery({ queryKey: qk.agents(ws, params), queryFn: () => api.get("/agents", pageOf(agentSchema), { query: { ...params, limit: 200 } }), enabled: !!ws })
}

export function useAgent(ws: string | null, id: string) {
  return useQuery({ queryKey: qk.agent(ws, id), queryFn: () => api.get(`/agents/${id}`, agentSchema), enabled: !!ws && !!id })
}

export function useAgentVersions(ws: string | null, id: string) {
  return useQuery({ queryKey: qk.versions(ws, id), queryFn: () => api.get(`/agents/${id}/versions`, z.array(agentVersionSchema)), enabled: !!ws })
}

export function useVersionDiff(ws: string | null, id: string, a?: number, b?: number) {
  return useQuery({
    queryKey: ["agent-diff", ws, id, a, b],
    queryFn: () => api.get(`/agents/${id}/versions/compare`, versionDiffSchema, { query: { a, b } }),
    enabled: !!ws && !!a && !!b && a !== b,
  })
}

export function useProviders(ws: string | null) {
  return useQuery({ queryKey: qk.providers(ws), queryFn: () => api.get("/model-providers", z.array(providerSchema)), enabled: !!ws })
}

export function usePresets(ws: string | null) {
  return useQuery({ queryKey: ["presets", ws], queryFn: () => api.get("/model-providers/presets", z.array(presetSchema)), enabled: !!ws })
}

export function useProviderUsage(ws: string | null, days = 30) {
  return useQuery({ queryKey: ["provider-usage", ws, days], queryFn: () => api.get("/model-providers/usage", z.array(usageRowSchema), { query: { days } }), enabled: !!ws })
}

export function useRuns(ws: string | null, params: { status?: string; agent_id?: string; limit?: number } = {}) {
  return useQuery({
    queryKey: qk.runs(ws, params),
    queryFn: () => api.get("/runs", pageOf(runSchema), { query: { limit: 50, ...params } }),
    enabled: !!ws,
    // Poll only while something is still in flight.
    refetchInterval: (q) => (q.state.data?.items.some((r) => !TERMINAL_STATUSES.includes(r.status)) ? 2000 : false),
  })
}

export function useRun(ws: string | null, id: string) {
  return useQuery({
    queryKey: qk.run(ws, id),
    queryFn: () => api.get(`/runs/${id}`, runSchema),
    enabled: !!ws && !!id,
    refetchInterval: (q) => (q.state.data && !TERMINAL_STATUSES.includes(q.state.data.status) ? 2000 : false),
  })
}

export function useRunEventsSnapshot(ws: string | null, id: string) {
  return useQuery({ queryKey: ["run-events", ws, id], queryFn: () => api.get(`/runs/${id}/events`, z.array(runEventSchema)), enabled: !!ws && !!id })
}

export function useWorkspace(ws: string | null) {
  return useQuery({ queryKey: ["workspace", ws], queryFn: () => api.get("/workspace", workspaceSchema), enabled: !!ws })
}

export function useMembers(ws: string | null) {
  return useQuery({ queryKey: ["members", ws], queryFn: () => api.get("/workspace/members", z.array(memberSchema)), enabled: !!ws })
}

export function useRoles(ws: string | null) {
  return useQuery({ queryKey: ["roles", ws], queryFn: () => api.get("/rbac/roles", rolesSchema), enabled: !!ws, staleTime: Infinity })
}

export function useAuditLogs(ws: string | null, action?: string, offset = 0) {
  return useQuery({ queryKey: ["audit", ws, action, offset], queryFn: () => api.get("/audit-logs", pageOf(auditEntrySchema), { query: { action, offset, limit: 50 } }), enabled: !!ws })
}

export interface AgentInput {
  name: string
  description: string
  config: AgentConfig
}

export function useAgentMutations(ws: string | null) {
  const qc = useQueryClient()
  const invalidate = (id?: string) => {
    qc.invalidateQueries({ queryKey: ["agents", ws] })
    if (id) {
      qc.invalidateQueries({ queryKey: qk.agent(ws, id) })
      qc.invalidateQueries({ queryKey: qk.versions(ws, id) })
    }
  }
  return {
    create: useMutation({ mutationFn: (body: AgentInput) => api.post("/agents", agentSchema, body), onSuccess: (a) => invalidate(a.id) }),
    update: useMutation({
      mutationFn: ({ id, ...body }: Partial<AgentInput> & { id: string; revision: number }) => api.patch(`/agents/${id}`, agentSchema, body),
      onSuccess: (a) => invalidate(a.id),
    }),
    remove: useMutation({ mutationFn: (id: string) => api.delete(`/agents/${id}`), onSuccess: () => invalidate() }),
    clone: useMutation({ mutationFn: ({ id, name }: { id: string; name: string }) => api.post(`/agents/${id}/clone`, agentSchema, { name }), onSuccess: (a) => invalidate(a.id) }),
    publish: useMutation({ mutationFn: ({ id, note }: { id: string; note: string }) => api.post(`/agents/${id}/publish`, agentSchema, { note }), onSuccess: (a) => invalidate(a.id) }),
    transition: useMutation({
      mutationFn: ({ id, action }: { id: string; action: "pause" | "resume" | "retire" }) => api.post(`/agents/${id}/${action}`, agentSchema),
      onSuccess: (a: Agent) => invalidate(a.id),
    }),
    rollback: useMutation({ mutationFn: ({ id, version }: { id: string; version: number }) => api.post(`/agents/${id}/rollback`, agentSchema, { version }), onSuccess: (a) => invalidate(a.id) }),
    starterPack: useMutation({ mutationFn: () => api.post("/agents/starter-pack", starterPackSchema), onSuccess: () => invalidate() }),
  }
}

export function useRunMutations(ws: string | null) {
  const qc = useQueryClient()
  return {
    create: useMutation({
      mutationFn: (body: { agent_id: string; input: Record<string, unknown>; source: "published" | "draft"; idempotencyKey?: string }) => {
        const { idempotencyKey, ...rest } = body
        return api.post("/runs", runSchema, rest, idempotencyKey ? { headers: { "Idempotency-Key": idempotencyKey } } : undefined)
      },
      onSuccess: () => qc.invalidateQueries({ queryKey: ["runs", ws] }),
    }),
    cancel: useMutation({
      mutationFn: (id: string) => api.post(`/runs/${id}/cancel`, runSchema),
      onSuccess: (r: Run) => {
        qc.setQueryData(qk.run(ws, r.id), r)
        qc.invalidateQueries({ queryKey: ["runs", ws] })
      },
    }),
  }
}

export function useProviderMutations(ws: string | null) {
  const qc = useQueryClient()
  const inv = () => {
    qc.invalidateQueries({ queryKey: qk.providers(ws) })
    qc.invalidateQueries({ queryKey: ["presets", ws] })
  }
  return {
    create: useMutation({ mutationFn: (body: Record<string, unknown>) => api.post("/model-providers", providerSchema, body), onSuccess: inv }),
    update: useMutation({ mutationFn: ({ id, ...body }: { id: string } & Record<string, unknown>) => api.patch(`/model-providers/${id}`, providerSchema, body), onSuccess: inv }),
    remove: useMutation({ mutationFn: (id: string) => api.delete(`/model-providers/${id}`), onSuccess: inv }),
    test: useMutation({ mutationFn: (id: string) => api.post(`/model-providers/${id}/test`, connectionTestSchema), onSuccess: inv }),
    addPreset: useMutation({
      mutationFn: ({ id, ...body }: { id: string; api_key?: string; base_url?: string }) => api.post(`/model-providers/presets/${id}`, providerSchema, body),
      onSuccess: inv,
    }),
  }
}

export function useWorkspaceMutations(ws: string | null) {
  const qc = useQueryClient()
  const invMembers = () => {
    qc.invalidateQueries({ queryKey: ["members", ws] })
    qc.invalidateQueries({ queryKey: ["audit", ws] })
  }
  return {
    update: useMutation({
      mutationFn: (body: { name?: string; monthly_budget_usd?: number | null }) => api.patch("/workspace", workspaceSchema, body),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["workspace", ws] })
        qc.invalidateQueries({ queryKey: ["me"] })
      },
    }),
    addMember: useMutation({ mutationFn: (body: { email: string; role: Role }) => api.post("/workspace/members", z.array(memberSchema), body), onSuccess: invMembers }),
    setRole: useMutation({
      mutationFn: ({ user_id, role }: { user_id: string; role: Role }) => api.patch(`/workspace/members/${user_id}`, z.array(memberSchema), { role }),
      onSuccess: invMembers,
    }),
    removeMember: useMutation({ mutationFn: (user_id: string) => api.delete(`/workspace/members/${user_id}`), onSuccess: invMembers }),
  }
}

export function useAuthConfig(enabled = true) {
  return useQuery({ queryKey: ["auth-config"], queryFn: () => api.get("/auth/config", authConfigSchema), staleTime: 60_000, enabled })
}

export function useInvitations(ws: string | null, enabled = true) {
  return useQuery({ queryKey: ["invitations", ws], queryFn: () => api.get("/workspace/invitations", z.array(invitationSchema)), enabled: !!ws && enabled })
}

export function useApiKeys(ws: string | null, enabled = true) {
  return useQuery({ queryKey: ["api-keys", ws], queryFn: () => api.get("/workspace/api-keys", z.array(apiKeySchema)), enabled: !!ws && enabled })
}

export function useTeamMutations(ws: string | null) {
  const qc = useQueryClient()
  const invInv = () => qc.invalidateQueries({ queryKey: ["invitations", ws] })
  const invKeys = () => qc.invalidateQueries({ queryKey: ["api-keys", ws] })
  return {
    invite: useMutation({ mutationFn: (body: { email: string; role: Role }) => api.post("/workspace/invitations", invitationCreatedSchema, body), onSuccess: invInv }),
    revokeInvite: useMutation({ mutationFn: (id: string) => api.delete(`/workspace/invitations/${id}`), onSuccess: invInv }),
    createKey: useMutation({
      mutationFn: (body: { name: string; role: Role; expires_in_days?: number | null }) => api.post("/workspace/api-keys", apiKeyCreatedSchema, body),
      onSuccess: invKeys,
    }),
    revokeKey: useMutation({ mutationFn: (id: string) => api.delete(`/workspace/api-keys/${id}`), onSuccess: invKeys }),
  }
}

export function useAccountMutations() {
  const qc = useQueryClient()
  return {
    changePassword: useMutation({ mutationFn: (body: { current_password: string; new_password: string }) => api.post("/auth/password", null, body) }),
    createWorkspace: useMutation({
      mutationFn: (name: string) => api.post("/auth/workspaces", meSchema, { name }),
      onSuccess: (me) => qc.setQueryData(qk.me, me),
    }),
  }
}

export function useTools(ws: string | null) {
  return useQuery({ queryKey: ["tools", ws], queryFn: () => api.get("/tools", z.array(toolSchema)), enabled: !!ws })
}

export function useTool(ws: string | null, id: string) {
  return useQuery({ queryKey: ["tool", ws, id], queryFn: () => api.get(`/tools/${id}`, toolSchema), enabled: !!ws && !!id })
}

export function useToolMutations(ws: string | null) {
  const qc = useQueryClient()
  const inv = () => {
    qc.invalidateQueries({ queryKey: ["tools", ws] })
    qc.invalidateQueries({ queryKey: ["tool", ws] })
  }
  return {
    create: useMutation({ mutationFn: (body: Record<string, unknown>) => api.post("/tools", toolSchema, body), onSuccess: inv }),
    update: useMutation({ mutationFn: ({ id, ...body }: { id: string } & Record<string, unknown>) => api.patch(`/tools/${id}`, toolSchema, body), onSuccess: inv }),
    remove: useMutation({ mutationFn: (id: string) => api.delete(`/tools/${id}`), onSuccess: inv }),
    test: useMutation({ mutationFn: ({ id, args }: { id: string; args: Record<string, unknown> }) => api.post(`/tools/${id}/test`, toolTestSchema, { arguments: args }) }),
    discoverMcp: useMutation({
      mutationFn: (body: { server_url: string; secret_headers: Record<string, string> }) => api.post("/tools/mcp/discover", z.array(mcpRemoteToolSchema), body),
    }),
    importMcp: useMutation({
      mutationFn: (body: { server_url: string; secret_headers: Record<string, string>; tools: string[]; name_prefix: string }) => api.post("/tools/mcp/import", z.array(toolSchema), body),
      onSuccess: inv,
    }),
  }
}

export function useKnowledgeBases(ws: string | null) {
  return useQuery({ queryKey: ["kbs", ws], queryFn: () => api.get("/knowledge-bases", z.array(knowledgeBaseSchema)), enabled: !!ws })
}

export function useKnowledgeBase(ws: string | null, id: string) {
  return useQuery({ queryKey: ["kb", ws, id], queryFn: () => api.get(`/knowledge-bases/${id}`, knowledgeBaseSchema), enabled: !!ws && !!id })
}

export function useDocuments(ws: string | null, kbId?: string) {
  const qc = useQueryClient()
  return useQuery({
    queryKey: ["documents", ws, kbId ?? "all"],
    queryFn: async () => {
      const page = await api.get("/documents", pageOf(documentSchema), { query: { kb_id: kbId, limit: 500 } })
      // Ingestion changes the knowledge base's document and chunk counts too.
      qc.invalidateQueries({ queryKey: ["kb", ws] })
      qc.invalidateQueries({ queryKey: ["kbs", ws] })
      return page
    },
    enabled: !!ws,
    // Poll while ingestion is in progress.
    refetchInterval: (q) => (q.state.data?.items.some((d) => d.status === "queued" || d.status === "processing") ? 2000 : false),
  })
}

export function useKnowledgeMutations(ws: string | null) {
  const qc = useQueryClient()
  const inv = () => {
    qc.invalidateQueries({ queryKey: ["kbs", ws] })
    qc.invalidateQueries({ queryKey: ["kb", ws] })
    qc.invalidateQueries({ queryKey: ["documents", ws] })
  }
  return {
    create: useMutation({ mutationFn: (body: { name: string; description: string; embedding: { provider_id: string; model: string } | null }) => api.post("/knowledge-bases", knowledgeBaseSchema, body), onSuccess: inv }),
    update: useMutation({ mutationFn: ({ id, ...body }: { id: string; name?: string; description?: string }) => api.patch(`/knowledge-bases/${id}`, knowledgeBaseSchema, body), onSuccess: inv }),
    remove: useMutation({ mutationFn: (id: string) => api.delete(`/knowledge-bases/${id}`), onSuccess: inv }),
    upload: useMutation({
      mutationFn: ({ kbId, file }: { kbId: string; file: File }) => {
        const form = new FormData()
        form.append("file", file)
        return api.upload(`/knowledge-bases/${kbId}/documents/upload`, documentSchema, form)
      },
      onSuccess: inv,
    }),
    addText: useMutation({ mutationFn: ({ kbId, title, text }: { kbId: string; title: string; text: string }) => api.post(`/knowledge-bases/${kbId}/documents/text`, documentSchema, { title, text }), onSuccess: inv }),
    removeDoc: useMutation({ mutationFn: (id: string) => api.delete(`/documents/${id}`), onSuccess: inv }),
    reindex: useMutation({ mutationFn: (id: string) => api.post(`/documents/${id}/reindex`, documentSchema), onSuccess: inv }),
    search: useMutation({ mutationFn: ({ kbId, query }: { kbId: string; query: string }) => api.post(`/knowledge-bases/${kbId}/search`, z.array(searchHitSchema), { query, top_k: 5 }) }),
  }
}
