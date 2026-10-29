import { describe, expect, it } from "vitest"

import { projectSchema } from "@/lib/schemas/projects"

const project = {
  id: "prj_1",
  workspace_id: "ws_1",
  name: "Example",
  idea: "Build an application that helps a team plan projects",
  description: "",
  status: "planning",
  planning_agent_ids: ["agt_1"],
  supervisor_agent_ids: [],
  teams: [{ id: "ui", name: "UI/UX", responsibility: "Build interfaces", agent_ids: ["agt_2"], parallelism: 5 }],
  documents: [],
  planning_runs: [],
  revision: 1,
  created_by: "usr_1",
  created_at: "2026-10-29T00:00:00Z",
  updated_at: "2026-10-29T00:00:00Z",
}

describe("Project Creator contract", () => {
  it("accepts a persisted project with configurable specialist teams", () => {
    expect(projectSchema.safeParse(project).success).toBe(true)
  })

  it("rejects unknown project statuses and malformed teams", () => {
    expect(projectSchema.safeParse({ ...project, status: "magic" }).success).toBe(false)
    expect(projectSchema.safeParse({ ...project, teams: [{ ...project.teams[0], parallelism: "five" }] }).success).toBe(false)
  })
})
