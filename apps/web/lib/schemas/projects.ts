import { z } from "zod"

export const projectStatusSchema = z.enum(["planning", "ready", "in_progress", "blocked", "completed", "archived"])
export const projectDocumentSchema = z.object({
  id: z.string(),
  title: z.string(),
  kind: z.string(),
  content: z.string(),
  feedback: z.string(),
  status: z.enum(["draft", "in_review", "approved", "superseded"]),
  revision: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
})
export const projectTeamSchema = z.object({
  id: z.string(),
  name: z.string(),
  responsibility: z.string(),
  agent_ids: z.array(z.string()),
  parallelism: z.number(),
})
export const projectPlanningRunSchema = z.object({
  run_id: z.string(),
  agent_id: z.string(),
  agent_name: z.string(),
  purpose: z.string(),
  status: z.enum(["queued", "running", "waiting_for_approval", "completed", "failed", "cancelled", "timed_out"]),
  document_id: z.string().nullable(),
  error: z.unknown().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
})
export const projectSchema = z.object({
  id: z.string(),
  workspace_id: z.string(),
  name: z.string(),
  idea: z.string(),
  description: z.string(),
  status: projectStatusSchema,
  planning_agent_ids: z.array(z.string()),
  supervisor_agent_ids: z.array(z.string()),
  teams: z.array(projectTeamSchema),
  documents: z.array(projectDocumentSchema),
  planning_runs: z.array(projectPlanningRunSchema),
  revision: z.number(),
  created_by: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type Project = z.infer<typeof projectSchema>
export type ProjectDocument = z.infer<typeof projectDocumentSchema>
