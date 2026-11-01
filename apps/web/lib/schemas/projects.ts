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
  kind: z.enum(["ui", "backend", "database", "other"]).default("other"),
  lead_agent_id: z.string().nullable().default(null),
})
export const projectPlanningRunSchema = z.object({
  run_id: z.string(),
  agent_id: z.string(),
  agent_name: z.string(),
  purpose: z.string(),
  status: z.enum(["queued", "running", "waiting_for_approval", "completed", "failed", "cancelled", "timed_out"]),
  document_id: z.string().nullable(),
  error: z.unknown().nullable(),
  model: z.string().optional(),
  created_at: z.string(),
  updated_at: z.string(),
})
export const projectFileSchema = z.object({
  path: z.string(),
  content: z.string(),
  updated_at: z.string(),
  updated_by: z.string(),
  round: z.number().nullable().optional(),
})
export const projectBuildRunSchema = z.object({
  run_id: z.string(),
  workflow_id: z.string(),
  round: z.number(),
  status: z.enum(["queued", "running", "waiting_for_approval", "completed", "failed", "cancelled", "timed_out"]),
  instructions: z.string().default(""),
  files_written: z.array(z.string()).default([]),
  summary: z.string().default(""),
  review: z.string().default(""),
  verdict: z.enum(["complete", "incomplete"]).nullable().default(null),
  error: z.unknown().nullable().optional(),
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
  director_agent_id: z.string().nullable().default(null),
  reviewer_agent_ids: z.array(z.string()).default([]),
  files: z.array(projectFileSchema).default([]),
  build_runs: z.array(projectBuildRunSchema).default([]),
  build_workflow_id: z.string().nullable().default(null),
  planning_model: z.object({ provider_id: z.string(), model: z.string(), provider_name: z.string().optional() }).nullable().optional(),
  revision: z.number(),
  created_by: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type Project = z.infer<typeof projectSchema>
export type ProjectDocument = z.infer<typeof projectDocumentSchema>
export type ProjectFile = z.infer<typeof projectFileSchema>
export type ProjectBuildRun = z.infer<typeof projectBuildRunSchema>
export type ProjectTeam = z.infer<typeof projectTeamSchema>
