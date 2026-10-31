import { Bot, Crown, GitFork, Library, Wand2, Wrench, type LucideIcon } from "lucide-react"

import type { StepType, WorkflowDefinition, WorkflowStep } from "@/lib/schemas"

export const STEP_TYPES: { type: StepType; label: string; icon: LucideIcon; help: string }[] = [
  { type: "agent", label: "Agent", icon: Bot, help: "Runs a published agent. Connected under a supervisor, it works on the tasks it is given." },
  { type: "supervisor", label: "Supervisor", icon: Crown, help: "Leads a team: plans, delegates tasks to its members in parallel, reviews and delivers." },
  { type: "tool", label: "Tool", icon: Wrench, help: "Calls an HTTP or MCP tool with templated arguments." },
  { type: "knowledge", label: "Knowledge", icon: Library, help: "Retrieves the top passages from knowledge bases." },
  { type: "transform", label: "Transform", icon: Wand2, help: "Builds text from a template (no model call)." },
  { type: "condition", label: "Condition", icon: GitFork, help: "Routes to one step or another." },
]

export const STEP_META = Object.fromEntries(STEP_TYPES.map((s) => [s.type, s])) as Record<StepType, (typeof STEP_TYPES)[number]>

export const OPS = [
  ["contains", "contains"], ["not_contains", "does not contain"], ["equals", "equals"], ["not_equals", "does not equal"],
  ["regex", "matches regex"], ["is_empty", "is empty"], ["not_empty", "is not empty"], ["greater_than", ">"], ["less_than", "<"],
] as const

export function newStep(type: StepType, existing: WorkflowStep[]): WorkflowStep {
  let n = existing.length + 1
  while (existing.some((s) => s.id === `${type}_${n}`)) n++
  return {
    id: `${type}_${n}`, type, name: "", agent_id: null, message: "{{ input.message }}", tool_id: null, arguments: {},
    knowledge_base_ids: [], query: "{{ input.message }}", top_k: 5,
    template: type === "transform" ? "{{ last.text }}" : "",
    condition: type === "condition" ? { left: "{{ last.text }}", op: "contains", right: "", case_sensitive: false } : null,
    on_true: null, on_false: null, next: null,
    role: "", delegates: [], max_rounds: 3, parallelism: 8, position: null,
  }
}

/** Steps that report to a supervisor. They run only when delegated to, never in the main flow. */
export function membersOf(def: WorkflowDefinition): Map<string, string> {
  const lead = new Map<string, string>()
  for (const s of def.steps) for (const d of s.delegates) if (!lead.has(d)) lead.set(d, s.id)
  return lead
}

/** Client-side mirror of the server's structural checks, so problems show before saving. */
export function problemsOf(def: WorkflowDefinition): string[] {
  const out: string[] = []
  const ids = def.steps.map((s) => s.id)
  const lead = membersOf(def)
  if (def.steps.length === 0) out.push("Add at least one step.")
  for (const s of def.steps) {
    if (!/^[a-z][a-z0-9_]{0,39}$/.test(s.id)) out.push(`"${s.id}": ids use lowercase letters, digits and _ and start with a letter.`)
    if (ids.filter((i) => i === s.id).length > 1) out.push(`"${s.id}" is used by more than one step.`)
    if ((s.type === "agent" || s.type === "supervisor") && !s.agent_id) out.push(`"${s.id}": choose an agent.`)
    if (s.type === "supervisor" && s.delegates.length === 0) out.push(`"${s.id}": connect at least one team member to this supervisor.`)
    for (const d of s.delegates) {
      const m = def.steps.find((x) => x.id === d)
      if (!m) out.push(`"${s.id}": team member "${d}" is missing.`)
      else if (m.type !== "agent" && m.type !== "supervisor") out.push(`"${s.id}": team member "${d}" must be an agent or a supervisor.`)
      else if (d === s.id) out.push(`"${s.id}": a supervisor cannot lead itself.`)
    }
    if (s.type === "tool" && !s.tool_id) out.push(`"${s.id}": choose a tool.`)
    if (s.type === "knowledge" && s.knowledge_base_ids.length === 0) out.push(`"${s.id}": choose a knowledge base.`)
    if (s.type === "transform" && !s.template.trim()) out.push(`"${s.id}": the template is empty.`)
    for (const k of ["next", "on_true", "on_false"] as const) {
      const t = s[k]
      if (t && t !== "end" && !ids.includes(t)) out.push(`"${s.id}": ${k} points to a missing step "${t}".`)
      if (t && lead.has(t)) out.push(`"${s.id}": ${k} points to "${t}", which only runs when its supervisor delegates to it.`)
    }
  }
  const counts = new Map<string, number>()
  for (const s of def.steps) for (const d of s.delegates) counts.set(d, (counts.get(d) ?? 0) + 1)
  for (const [d, n] of counts) if (n > 1) out.push(`"${d}" reports to more than one supervisor.`)
  for (const start of lead.keys()) {
    const seen = new Set([start])
    let cur = start
    while (lead.has(cur)) {
      cur = lead.get(cur)!
      if (seen.has(cur)) { out.push(`Supervisors "${start}" and "${cur}" lead each other in a loop.`); break }
      seen.add(cur)
    }
  }
  if (def.steps.length > 0 && lead.size === def.steps.length) out.push("At least one step must run in the main flow.")
  return Array.from(new Set(out))
}

/** Where execution goes after a step, as labelled edges (for the diagram). */
export function edgesOf(def: WorkflowDefinition, i: number): { label: string; target: string }[] {
  const s = def.steps[i]
  const lead = membersOf(def)
  if (lead.has(s.id)) return [{ label: "reports to", target: lead.get(s.id)! }]
  let j = i + 1
  while (j < def.steps.length && lead.has(def.steps[j].id)) j++
  const following = def.steps[j]?.id ?? "end"
  if (s.type === "condition") return [{ label: "true", target: s.on_true ?? following }, { label: "false", target: s.on_false ?? following }]
  const team = s.type === "supervisor" ? s.delegates.map((d) => ({ label: "delegates", target: d })) : []
  return [...team, { label: "next", target: s.next ?? following }]
}
