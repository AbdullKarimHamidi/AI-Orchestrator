import type { Edge, Node } from "@xyflow/react"

import type { WorkflowDefinition, WorkflowStep } from "@/lib/schemas"

import { membersOf, newStep } from "../steps"

/**
 * Converts between a workflow definition (an ordered list of steps with routes) and the node
 * graph shown on the canvas.
 *
 * - Flow edges leave a step's right side ("out", or "true"/"false" for conditions) and enter
 *   another step's left side ("in"). They become `next` / `on_true` / `on_false`.
 * - Team edges leave a supervisor's bottom ("team") and enter a member's top ("lead"). They
 *   become the supervisor's `delegates`; members run only when their supervisor delegates.
 * - Start and End are canvas-only nodes. Start's edge picks the first step; a route that is not
 *   connected ends the run.
 */

export const START = "__start"
export const END_NODE = "__end"

export type StepNodeData = { step: WorkflowStep; problems?: string[] }
export type StepNode = Node<StepNodeData, "step">
export type TerminalNode = Node<Record<string, never>, "start" | "end">
export type CanvasNode = StepNode | TerminalNode

export const COL = 300
export const ROW = 190

export function isStepNode(n: CanvasNode): n is StepNode {
  return n.type === "step"
}

export function flowEdge(source: string, handle: string, target: string): Edge {
  const label = handle === "true" || handle === "false" ? handle : undefined
  return {
    id: `flow:${source}:${handle}`, source, sourceHandle: handle, target, targetHandle: "in", type: "flow",
    data: { kind: "flow" }, label,
  }
}

export function teamEdge(source: string, target: string): Edge {
  return { id: `team:${source}->${target}`, source, sourceHandle: "team", target, targetHandle: "lead", type: "team", data: { kind: "team" } }
}

/** Main-flow order of steps, skipping team members (they never run in the main flow). */
function mainSteps(def: WorkflowDefinition): WorkflowStep[] {
  const lead = membersOf(def)
  return def.steps.filter((s) => !lead.has(s.id))
}

/** Positions for steps that have none: the main flow left to right, each team as a tree below its lead. */
export function autoLayout(def: WorkflowDefinition, force = false): Record<string, { x: number; y: number }> {
  const pos: Record<string, { x: number; y: number }> = {}
  const byId = new Map(def.steps.map((s) => [s.id, s]))
  let col = 0
  const place = (s: WorkflowStep, x: number, y: number) => {
    pos[s.id] = !force && s.position ? s.position : { x, y }
  }
  // width (in columns) of a subtree, so siblings do not overlap
  const width = (id: string, seen = new Set<string>()): number => {
    const s = byId.get(id)
    if (!s || seen.has(id) || s.delegates.length === 0) return 1
    seen.add(id)
    return Math.max(1, s.delegates.reduce((n, d) => n + width(d, seen), 0))
  }
  const layoutTeam = (s: WorkflowStep, left: number, depth: number, seen: Set<string>) => {
    let x = left
    for (const d of s.delegates) {
      const m = byId.get(d)
      if (!m || seen.has(d)) continue
      seen.add(d)
      const w = width(d)
      place(m, (x + (w - 1) / 2) * COL, depth * ROW)
      layoutTeam(m, x, depth + 1, seen)
      x += w
    }
  }
  for (const s of mainSteps(def)) {
    const w = width(s.id)
    place(s, (col + 1 + (w - 1) / 2) * COL, 0)
    layoutTeam(s, col + 1, 1, new Set([s.id]))
    col += w
  }
  // anything left over (e.g. a member of a missing supervisor)
  for (const s of def.steps) if (!pos[s.id]) place(s, (++col) * COL, 0)
  pos[START] = { x: 0, y: 0 }
  pos[END_NODE] = { x: (col + 1) * COL, y: 0 }
  return pos
}

export function toGraph(def: WorkflowDefinition): { nodes: CanvasNode[]; edges: Edge[] } {
  const pos = autoLayout(def)
  const lead = membersOf(def)
  const main = mainSteps(def)
  const nodes: CanvasNode[] = [
    { id: START, type: "start", position: pos[START], data: {}, deletable: false },
    ...def.steps.map((s): StepNode => ({ id: s.id, type: "step", position: pos[s.id], data: { step: s } })),
    { id: END_NODE, type: "end", position: pos[END_NODE], data: {}, deletable: false },
  ]
  const ids = new Set(def.steps.map((s) => s.id))
  const target = (t: string | null, fallback: string) => {
    const v = t ?? fallback
    return v === "end" || !ids.has(v) ? END_NODE : v
  }
  const edges: Edge[] = []
  if (main[0]) edges.push(flowEdge(START, "out", main[0].id))
  main.forEach((s, i) => {
    const following = main[i + 1]?.id ?? "end"
    if (s.type === "condition") {
      edges.push(flowEdge(s.id, "true", target(s.on_true, following)), flowEdge(s.id, "false", target(s.on_false, following)))
    } else {
      edges.push(flowEdge(s.id, "out", target(s.next, following)))
    }
  })
  for (const s of def.steps) for (const d of s.delegates) if (ids.has(d) && lead.get(d) === s.id) edges.push(teamEdge(s.id, d))
  return { nodes, edges }
}

/** The definition a graph describes. Steps are ordered by the main flow from Start, then the rest. */
export function fromGraph(nodes: CanvasNode[], edges: Edge[], base: Pick<WorkflowDefinition, "max_step_executions" | "max_delegations">): WorkflowDefinition {
  const stepNodes = nodes.filter(isStepNode)
  const byId = new Map(stepNodes.map((n) => [n.id, n]))
  const out = new Map<string, string>() // `${source}:${handle}` -> target
  const team = new Map<string, string[]>()
  for (const e of edges) {
    if (e.sourceHandle === "team") {
      if (byId.has(e.source) && byId.has(e.target)) team.set(e.source, [...(team.get(e.source) ?? []), e.target])
    } else {
      out.set(`${e.source}:${e.sourceHandle ?? "out"}`, e.target)
    }
  }
  const route = (id: string, handle: string): string => {
    const t = out.get(`${id}:${handle}`)
    return !t || t === END_NODE || !byId.has(t) ? "end" : t
  }
  // order: walk the main flow from Start (breadth first), then unreachable steps, then team members
  const order: string[] = []
  const seen = new Set<string>()
  const queue = [out.get(`${START}:out`)]
  while (queue.length) {
    const id = queue.shift()
    if (!id || seen.has(id) || !byId.has(id)) continue
    seen.add(id)
    order.push(id)
    const s = byId.get(id)!.data.step
    queue.push(...(s.type === "condition" ? [out.get(`${id}:true`), out.get(`${id}:false`)] : [out.get(`${id}:out`)]))
  }
  const members = new Set([...team.values()].flat())
  const rest = stepNodes.filter((n) => !seen.has(n.id)).sort((a, b) => a.position.x - b.position.x || a.position.y - b.position.y)
  for (const n of rest) if (!members.has(n.id)) order.push(n.id)
  for (const n of rest) if (members.has(n.id)) order.push(n.id)

  const steps = order.map((id): WorkflowStep => {
    const n = byId.get(id)!
    const s = n.data.step
    const position = { x: Math.round(n.position.x), y: Math.round(n.position.y) }
    const delegates = s.type === "supervisor"
      ? (team.get(id) ?? []).slice().sort((a, b) => byId.get(a)!.position.x - byId.get(b)!.position.x)
      : []
    if (members.has(id)) return { ...s, id, position, delegates, next: null, on_true: null, on_false: null }
    if (s.type === "condition") return { ...s, id, position, delegates, next: null, on_true: route(id, "true"), on_false: route(id, "false") }
    return { ...s, id, position, delegates, next: route(id, "out"), on_true: null, on_false: null }
  })
  return { ...base, steps }
}

/** Would a team edge from `lead` to `member` create a loop of supervisors? */
export function createsLoop(edges: Edge[], lead: string, member: string): boolean {
  const parent = new Map<string, string>()
  for (const e of edges) if (e.sourceHandle === "team") parent.set(e.target, e.source)
  parent.set(member, lead)
  let cur: string | undefined = lead
  const seen = new Set([member])
  while (cur) {
    if (seen.has(cur)) return true
    seen.add(cur)
    cur = parent.get(cur)
  }
  return false
}

/** A supervisor with `count` workers, wired as a team, ready to drop on the canvas. */
export function teamTemplate(existing: WorkflowStep[], count: number, origin: { x: number; y: number }): WorkflowStep[] {
  const all = [...existing]
  const lead = { ...newStep("supervisor", all), name: "Project lead", position: origin }
  all.push(lead)
  const roles = [
    ["Architect", "Designs the overall structure, data model and interfaces."],
    ["Backend developer", "Implements server-side logic and APIs."],
    ["Frontend developer", "Implements the user interface."],
    ["QA engineer", "Reviews the work, writes tests and reports defects."],
    ["Technical writer", "Writes documentation and usage instructions."],
    ["Researcher", "Investigates options and gathers facts."],
  ]
  const workers: WorkflowStep[] = []
  for (let i = 0; i < count; i++) {
    const [name, role] = roles[i % roles.length]
    const w = {
      ...newStep("agent", all), name: i < roles.length ? name : `${name} ${Math.floor(i / roles.length) + 1}`, role,
      position: { x: origin.x + (i - (count - 1) / 2) * COL, y: origin.y + ROW },
    }
    all.push(w)
    workers.push(w)
  }
  lead.delegates = workers.map((w) => w.id)
  return [lead, ...workers]
}

interface ProjectLike {
  name: string
  idea: string
  supervisor_agent_ids: string[]
  planning_agent_ids: string[]
  teams: { id: string; name: string; responsibility: string; agent_ids: string[]; parallelism: number }[]
  documents: { title: string; content: string; status: string }[]
  planning_model?: { provider_id: string; model: string } | null
}

/** A team workflow for a Project Creator project: the first supervisor directs one lead per team
 * (the second supervisor when there is one), and each lead delegates to that team's agents. */
export function projectTeamDefinition(p: ProjectLike): WorkflowDefinition | null {
  const leads = p.supervisor_agent_ids.length ? p.supervisor_agent_ids : p.planning_agent_ids.slice(0, 1)
  if (!leads.length) return null
  const steps: WorkflowStep[] = []
  const slug = (v: string) => v.toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^[^a-z]+/, "").slice(0, 30) || "team"
  const unique = (v: string) => {
    let id = slug(v)
    let n = 2
    while (steps.some((s) => s.id === id)) id = `${slug(v).slice(0, 27)}_${n++}`
    return id
  }
  const safe = (t: string) => t.replaceAll("{{", "{ {").replaceAll("}}", "} }")
  const approved = p.documents.filter((d) => d.status === "approved")
  const plan = (approved.length ? approved : p.documents).map((d) => `## ${safe(d.title)}\n${safe(d.content)}`).join("\n\n").slice(0, 12000)
  const brief = [`Project: ${safe(p.name)}`, safe(p.idea).slice(0, 4000), plan && `Plan:\n${plan}`, "Additional instructions: {{ input.message }}"].filter(Boolean).join("\n\n")
  const director: WorkflowStep = { ...newStep("supervisor", steps), id: "director", name: "Project director", agent_id: leads[0], message: brief, role: "Owns the project and delivers the final result.", next: "end" }
  steps.push(director)
  const teams = p.teams.filter((t) => t.agent_ids.length)
  const groups = teams.length ? teams : [{ id: "planners", name: "Planners", responsibility: "Plan and design the project.", agent_ids: p.planning_agent_ids, parallelism: 5 }]
  for (const t of groups) {
    if (steps.length >= 50) break
    const agentStep = (agentId: string, name: string, role: string): WorkflowStep => ({ ...newStep("agent", steps), id: unique(name), name, agent_id: agentId, role })
    if (t.agent_ids.length === 1) {
      const a = agentStep(t.agent_ids[0], t.name, t.responsibility)
      steps.push(a)
      director.delegates.push(a.id)
      continue
    }
    const lead: WorkflowStep = { ...newStep("supervisor", steps), id: unique(`${t.name}_lead`), name: `${t.name} lead`, agent_id: leads[1] ?? leads[0], role: t.responsibility, parallelism: Math.min(50, Math.max(1, t.parallelism)), max_rounds: 2 }
    steps.push(lead)
    director.delegates.push(lead.id)
    t.agent_ids.forEach((agentId, i) => {
      if (steps.length >= 50) return
      const a = agentStep(agentId, `${t.name} ${i + 1}`, `${t.name}: ${t.responsibility}`)
      steps.push(a)
      lead.delegates.push(a.id)
    })
    if (!lead.delegates.length) lead.type = "agent"
  }
  if (!director.delegates.length) return null
  // The model chosen for the project (e.g. OpenRouter) runs every agent in the team, so the team
  // does not fall back to whatever model each agent was last published with.
  const pm = p.planning_model
  if (pm?.provider_id) for (const s of steps) if (s.type === "agent" || s.type === "supervisor") s.model = { provider_id: pm.provider_id, model: pm.model }
  return { steps, max_step_executions: 50, max_delegations: 200 }
}
