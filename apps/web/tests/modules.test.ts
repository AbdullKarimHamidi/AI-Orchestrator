import { describe, expect, it } from "vitest"

import { parseCases } from "@/components/evaluations/parse-cases"
import { edgesOf, newStep, problemsOf } from "@/components/workflows/steps"
import { workflowDefinitionSchema } from "@/lib/schemas"

describe("workflow steps", () => {
  it("flags missing references before saving", () => {
    const agent = newStep("agent", [])
    const def = { steps: [agent, { ...newStep("transform", [agent]), next: "nowhere" }], max_step_executions: 50 }
    const problems = problemsOf(def)
    expect(problems.some((p) => p.includes("choose an agent"))).toBe(true)
    expect(problems.some((p) => p.includes('missing step "nowhere"'))).toBe(true)
    expect(problemsOf({ ...def, steps: [{ ...agent, agent_id: "agt_1" }] })).toEqual([])
  })

  it("describes routes, including condition branches and the implicit next step", () => {
    const c = { ...newStep("condition", []), id: "check", on_true: "end" }
    const t = { ...newStep("transform", [c]), id: "fmt" }
    const def = { steps: [c, t], max_step_executions: 50 }
    expect(edgesOf(def, 0)).toEqual([{ label: "true", target: "end" }, { label: "false", target: "fmt" }])
    expect(edgesOf(def, 1)).toEqual([{ label: "next", target: "end" }])
    expect(workflowDefinitionSchema.safeParse(def).success).toBe(true)
  })
})

describe("dataset import", () => {
  it("parses pipes, JSON Lines and JSON arrays", () => {
    expect(parseCases("2+2? | 4\nCapital | Paris | France")).toEqual([
      { id: "case_1", input: "2+2?", expected: "4" },
      { id: "case_2", input: "Capital", expected: "Paris | France" },
    ])
    expect(parseCases('{"input": "a", "expected": "b"}\n{"question": "c", "answer": "d"}')[1]).toEqual({ id: "case_2", input: "c", expected: "d" })
    expect(parseCases('[{"id": "x", "input": "a"}]')).toEqual([{ id: "x", input: "a", expected: "" }])
  })
})
