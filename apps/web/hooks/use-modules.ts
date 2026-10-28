"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"

import { api } from "@/lib/api-client"
import {
  billingSchema, breakdownRowSchema, compareSchema, datasetSchema, evalRunSchema, memorySchema, memoryScopeSchema,
  pageOf, runSchema, statementSchema, TERMINAL_STATUSES, timeseriesRowSchema, validationSchema, workflowSchema,
  workflowVersionSchema,
  type EvalCase, type Plan, type ScorerType, type WorkflowDefinition,
} from "@/lib/schemas"

// ----- workflows -----
export function useWorkflows(ws: string | null) {
  return useQuery({ queryKey: ["workflows", ws], queryFn: () => api.get("/workflows", pageOf(workflowSchema), { query: { limit: 200 } }), enabled: !!ws })
}

export function useWorkflow(ws: string | null, id: string) {
  return useQuery({ queryKey: ["workflow", ws, id], queryFn: () => api.get(`/workflows/${id}`, workflowSchema), enabled: !!ws && !!id })
}

export function useWorkflowVersions(ws: string | null, id: string) {
  return useQuery({ queryKey: ["workflow-versions", ws, id], queryFn: () => api.get(`/workflows/${id}/versions`, z.array(workflowVersionSchema)), enabled: !!ws && !!id })
}

export function useWorkflowValidation(ws: string | null, id: string, revision?: number) {
  return useQuery({ queryKey: ["workflow-validate", ws, id, revision], queryFn: () => api.get(`/workflows/${id}/validate`, validationSchema), enabled: !!ws && !!id })
}

export function useWorkflowRuns(ws: string | null, id: string, limit = 50) {
  return useQuery({
    queryKey: ["runs", ws, { workflow_id: id, limit }],
    queryFn: () => api.get(`/workflows/${id}/runs`, pageOf(runSchema), { query: { limit } }),
    enabled: !!ws && !!id,
    refetchInterval: (q) => (q.state.data?.items.some((r) => !TERMINAL_STATUSES.includes(r.status)) ? 2000 : false),
  })
}

export interface WorkflowInput {
  name: string
  description: string
  definition: WorkflowDefinition
}

export function useWorkflowMutations(ws: string | null) {
  const qc = useQueryClient()
  const inv = (id?: string) => {
    qc.invalidateQueries({ queryKey: ["workflows", ws] })
    if (id) {
      qc.invalidateQueries({ queryKey: ["workflow", ws, id] })
      qc.invalidateQueries({ queryKey: ["workflow-versions", ws, id] })
      qc.invalidateQueries({ queryKey: ["workflow-validate", ws, id] })
    }
  }
  return {
    create: useMutation({ mutationFn: (body: WorkflowInput) => api.post("/workflows", workflowSchema, body), onSuccess: (w) => inv(w.id) }),
    update: useMutation({
      mutationFn: ({ id, ...body }: Partial<WorkflowInput> & { id: string; revision: number }) => api.patch(`/workflows/${id}`, workflowSchema, body),
      onSuccess: (w) => inv(w.id),
    }),
    remove: useMutation({ mutationFn: (id: string) => api.delete(`/workflows/${id}`), onSuccess: () => inv() }),
    publish: useMutation({ mutationFn: ({ id, note }: { id: string; note: string }) => api.post(`/workflows/${id}/publish`, workflowSchema, { note }), onSuccess: (w) => inv(w.id) }),
    archive: useMutation({
      mutationFn: ({ id, archived }: { id: string; archived: boolean }) => api.post(`/workflows/${id}/${archived ? "archive" : "restore"}`, workflowSchema),
      onSuccess: (w) => inv(w.id),
    }),
    run: useMutation({
      mutationFn: ({ id, ...body }: { id: string; input: Record<string, unknown>; source: "published" | "draft" }) => api.post(`/workflows/${id}/runs`, runSchema, body),
      onSuccess: () => qc.invalidateQueries({ queryKey: ["runs", ws] }),
    }),
  }
}

// ----- evaluations -----
export function useDatasets(ws: string | null) {
  return useQuery({ queryKey: ["datasets", ws], queryFn: () => api.get("/eval-datasets", z.array(datasetSchema)), enabled: !!ws })
}

export function useEvalRuns(ws: string | null, datasetId?: string) {
  return useQuery({
    queryKey: ["eval-runs", ws, datasetId ?? "all"],
    queryFn: () => api.get("/eval-runs", z.array(evalRunSchema), { query: { dataset_id: datasetId } }),
    enabled: !!ws,
    refetchInterval: (q) => (q.state.data?.some((e) => e.status === "running") ? 2000 : false),
  })
}

export function useEvalCompare(ws: string | null, a?: string, b?: string) {
  return useQuery({ queryKey: ["eval-compare", ws, a, b], queryFn: () => api.get("/eval-runs/compare", compareSchema, { query: { a, b } }), enabled: !!ws && !!a && !!b && a !== b })
}

export function useEvalMutations(ws: string | null) {
  const qc = useQueryClient()
  const invDs = () => qc.invalidateQueries({ queryKey: ["datasets", ws] })
  const invRuns = () => qc.invalidateQueries({ queryKey: ["eval-runs", ws] })
  return {
    createDataset: useMutation({ mutationFn: (body: { name: string; description: string; cases: Partial<EvalCase>[] }) => api.post("/eval-datasets", datasetSchema, body), onSuccess: invDs }),
    updateDataset: useMutation({
      mutationFn: ({ id, ...body }: { id: string; name?: string; description?: string; cases?: Partial<EvalCase>[] }) => api.patch(`/eval-datasets/${id}`, datasetSchema, body),
      onSuccess: invDs,
    }),
    removeDataset: useMutation({ mutationFn: (id: string) => api.delete(`/eval-datasets/${id}`), onSuccess: invDs }),
    createRun: useMutation({
      mutationFn: (body: { dataset_id: string; agent_id: string; source: "published" | "draft"; scorer: { type: ScorerType; case_sensitive: boolean }; name: string }) =>
        api.post("/eval-runs", evalRunSchema, body),
      onSuccess: () => {
        invRuns()
        qc.invalidateQueries({ queryKey: ["runs", ws] })
      },
    }),
    removeRun: useMutation({ mutationFn: (id: string) => api.delete(`/eval-runs/${id}`), onSuccess: invRuns }),
  }
}

// ----- memory -----
export function useMemories(ws: string | null, params: { agent_id?: string; scope?: string; q?: string }) {
  return useQuery({ queryKey: ["memories", ws, params], queryFn: () => api.get("/memories", pageOf(memorySchema), { query: { ...params, limit: 200 } }), enabled: !!ws })
}

export function useMemoryScopes(ws: string | null, agentId?: string) {
  return useQuery({ queryKey: ["memory-scopes", ws, agentId ?? "all"], queryFn: () => api.get("/memories/scopes", z.array(memoryScopeSchema), { query: { agent_id: agentId } }), enabled: !!ws })
}

export function useMemoryMutations(ws: string | null) {
  const qc = useQueryClient()
  const inv = () => {
    qc.invalidateQueries({ queryKey: ["memories", ws] })
    qc.invalidateQueries({ queryKey: ["memory-scopes", ws] })
  }
  return {
    create: useMutation({
      mutationFn: (body: { agent_id: string; scope: string; content: string; tags: string[]; ttl_days: number | null }) => api.post("/memories", memorySchema, body),
      onSuccess: inv,
    }),
    update: useMutation({ mutationFn: ({ id, ...body }: { id: string; content?: string; tags?: string[] }) => api.patch(`/memories/${id}`, memorySchema, body), onSuccess: inv }),
    remove: useMutation({ mutationFn: (id: string) => api.delete(`/memories/${id}`), onSuccess: inv }),
    forget: useMutation({ mutationFn: (body: { agent_id: string; scope: string | null }) => api.post("/memories/forget", z.object({ deleted: z.number() }), body), onSuccess: inv }),
  }
}

// ----- billing and analytics -----
export function useBilling(ws: string | null) {
  return useQuery({ queryKey: ["billing", ws], queryFn: () => api.get("/billing", billingSchema), enabled: !!ws })
}

export function useStatements(ws: string | null, months = 6) {
  return useQuery({ queryKey: ["statements", ws, months], queryFn: () => api.get("/billing/statements", z.array(statementSchema), { query: { months } }), enabled: !!ws })
}

export function useBillingMutations(ws: string | null) {
  const qc = useQueryClient()
  return {
    changePlan: useMutation({
      mutationFn: (plan: Plan["id"]) => api.post("/billing/plan", billingSchema, { plan }),
      onSuccess: (b) => {
        qc.setQueryData(["billing", ws], b)
        qc.invalidateQueries({ queryKey: ["statements", ws] })
      },
    }),
  }
}

export function useTimeseries(ws: string | null, days: number) {
  return useQuery({ queryKey: ["timeseries", ws, days], queryFn: () => api.get("/analytics/timeseries", z.array(timeseriesRowSchema), { query: { days } }), enabled: !!ws })
}

export function useBreakdown(ws: string | null, days: number) {
  return useQuery({ queryKey: ["breakdown", ws, days], queryFn: () => api.get("/analytics/breakdown", z.array(breakdownRowSchema), { query: { days } }), enabled: !!ws })
}
