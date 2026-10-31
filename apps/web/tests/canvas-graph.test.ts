import { describe, expect, it } from "vitest"

import { createsLoop, END_NODE, fromGraph, projectTeamDefinition, START, teamEdge, teamTemplate, toGraph } from "@/components/workflows/canvas/graph"
import { edgesOf, newStep, problemsOf } from "@/components/workflows/steps"
import type { WorkflowDefinition, WorkflowStep } from "@/lib/schemas"

const base = { max_step_executions: 50, max_delegations: 200 }

function teamDef(): WorkflowDefinition {
  const steps: WorkflowStep[] = []
  const lead = { ...newStep("supervisor", steps), id: "lead", agent_id: "agt_1" }
  steps.push(lead)
  const a = { ...newStep("agent", steps), id: "dev", agent_id: "agt_2" }
  const b = { ...newStep("agent", steps), id: "qa", agent_id: "agt_3" }
  lead.delegates = ["dev", "qa"]
  const wrap = { ...newStep("transform", steps), id: "wrap", template: "{{ last.text }}" }
  return { ...base, steps: [lead, a, b, wrap] }
}

describe("canvas graph", () => {
  it("draws the main flow and team edges, skipping members in the flow", () => {
    const { nodes, edges } = toGraph(teamDef())
    expect(nodes.map((n) => n.id)).toEqual([START, "lead", "dev", "qa", "wrap", END_NODE])
    const ids = edges.map((e) => e.id).sort()
    expect(ids).toEqual(["flow:__start:out", "flow:lead:out", "flow:wrap:out", "team:lead->dev", "team:lead->qa"].sort())
    expect(edges.find((e) => e.id === "flow:lead:out")!.target).toBe("wrap")
    // members sit below their supervisor
    const pos = Object.fromEntries(nodes.map((n) => [n.id, n.position]))
    expect(pos.dev.y).toBeGreaterThan(pos.lead.y)
  })

  it("round-trips a definition with explicit routes and positions", () => {
    const def = teamDef()
    const { nodes, edges } = toGraph(def)
    const back = fromGraph(nodes, edges, base)
    expect(back.steps.map((s) => s.id)).toEqual(["lead", "wrap", "dev", "qa"])
    const lead = back.steps.find((s) => s.id === "lead")!
    expect(lead.delegates).toEqual(["dev", "qa"])
    expect(lead.next).toBe("wrap")
    expect(back.steps.find((s) => s.id === "wrap")!.next).toBe("end")
    expect(back.steps.find((s) => s.id === "dev")!.next).toBeNull()
    expect(back.steps.every((s) => s.position)).toBe(true)
    expect(problemsOf(back)).toEqual([])
  })

  it("maps condition handles to on_true / on_false", () => {
    const c = { ...newStep("condition", []), id: "check" }
    const t = { ...newStep("transform", [c]), id: "fmt", template: "x" }
    const { nodes, edges } = toGraph({ ...base, steps: [c, t] })
    const back = fromGraph(nodes, edges.map((e) => (e.id === "flow:check:true" ? { ...e, target: END_NODE } : e)), base)
    const check = back.steps.find((s) => s.id === "check")!
    expect([check.on_true, check.on_false]).toEqual(["end", "fmt"])
  })

  it("detects supervisor loops", () => {
    const edges = [teamEdge("a", "b"), teamEdge("b", "c")]
    expect(createsLoop(edges, "c", "a")).toBe(true)
    expect(createsLoop(edges, "a", "d")).toBe(false)
  })

  it("builds a wired team template with unique ids", () => {
    const team = teamTemplate([], 8, { x: 0, y: 0 })
    expect(team).toHaveLength(9)
    expect(team[0].type).toBe("supervisor")
    expect(team[0].delegates).toHaveLength(8)
    expect(new Set(team.map((s) => s.id)).size).toBe(9)
  })

  it("reports team problems and lists delegation in the diagram", () => {
    const def = teamDef()
    expect(edgesOf(def, 0)).toEqual([{ label: "delegates", target: "dev" }, { label: "delegates", target: "qa" }, { label: "next", target: "wrap" }])
    expect(edgesOf(def, 1)).toEqual([{ label: "reports to", target: "lead" }])
    const bad = { ...def, steps: def.steps.map((s) => (s.id === "wrap" ? { ...s, next: "dev" } : s)) }
    expect(problemsOf(bad).join(" ")).toContain("only runs when its supervisor delegates")
    const loop = { ...def, steps: def.steps.map((s) => (s.id === "dev" ? { ...s, type: "supervisor" as const, delegates: ["lead"] } : s)) }
    expect(problemsOf(loop).join(" ")).toContain("loop")
  })
})

describe("project team workflow", () => {
  it("builds director → team leads → agents from a project", () => {
    const def = projectTeamDefinition({
      name: "Shop", idea: "An online {{ shop }}", supervisor_agent_ids: ["sup1", "sup2"], planning_agent_ids: ["p1"],
      teams: [
        { id: "be", name: "Backend", responsibility: "APIs", agent_ids: ["a1", "a2", "a3"], parallelism: 3 },
        { id: "doc", name: "Docs", responsibility: "Docs", agent_ids: ["a4"], parallelism: 1 },
      ],
      documents: [{ title: "Plan", content: "use {{ postgres }}", status: "approved" }],
    })!
    expect(problemsOf(def)).toEqual([])
    const director = def.steps[0]
    expect(director.agent_id).toBe("sup1")
    expect(director.message).not.toContain("{{ shop }}")
    expect(director.message).toContain("{{ input.message }}")
    const lead = def.steps.find((s) => s.id === director.delegates[0])!
    expect([lead.type, lead.agent_id, lead.delegates.length, lead.parallelism]).toEqual(["supervisor", "sup2", 3, 3])
    expect(def.steps.find((s) => s.id === director.delegates[1])!.agent_id).toBe("a4")
  })
})
