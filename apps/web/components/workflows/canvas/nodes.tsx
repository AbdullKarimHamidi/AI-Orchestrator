"use client"

import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, Handle, Position, useReactFlow, type EdgeProps, type NodeProps } from "@xyflow/react"
import { cn } from "cn"
import { AlertTriangle, CircleStop, Play, Users, X } from "lucide-react"
import { createContext, useContext } from "react"

import type { StepType } from "@/lib/schemas"

import { STEP_META } from "../steps"
import type { StepNode } from "./graph"

export interface CanvasInfo {
  agentNames: Record<string, string>
  agentModels: Record<string, string>
  toolNames: Record<string, string>
  kbNames: Record<string, string>
  /** member id -> supervisor id */
  leads: Map<string, string>
  teamSize: Map<string, number>
}

export const CanvasInfoContext = createContext<CanvasInfo>({
  agentNames: {}, agentModels: {}, toolNames: {}, kbNames: {}, leads: new Map(), teamSize: new Map(),
})

/** Accent per step type: icon chip, top bar and minimap colour. */
export const ACCENT: Record<StepType, { chip: string; bar: string; hex: string }> = {
  supervisor: { chip: "bg-violet-500/15 text-violet-600 dark:text-violet-300", bar: "from-violet-500 to-fuchsia-500", hex: "#8b5cf6" },
  agent: { chip: "bg-sky-500/15 text-sky-600 dark:text-sky-300", bar: "from-sky-500 to-cyan-400", hex: "#0ea5e9" },
  tool: { chip: "bg-amber-500/15 text-amber-600 dark:text-amber-300", bar: "from-amber-500 to-orange-400", hex: "#f59e0b" },
  knowledge: { chip: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300", bar: "from-emerald-500 to-teal-400", hex: "#10b981" },
  transform: { chip: "bg-slate-500/15 text-slate-600 dark:text-slate-300", bar: "from-slate-500 to-slate-400", hex: "#64748b" },
  condition: { chip: "bg-rose-500/15 text-rose-600 dark:text-rose-300", bar: "from-rose-500 to-pink-400", hex: "#f43f5e" },
}

const handleBase = "!size-3 !border-2 !border-background transition-transform hover:!scale-125"

function subtitle(node: StepNode["data"]["step"], info: CanvasInfo): { text: string; missing: boolean } {
  switch (node.type) {
    case "agent":
    case "supervisor":
      return node.agent_id ? { text: info.agentNames[node.agent_id] ?? node.agent_id, missing: false } : { text: "Choose an agent", missing: true }
    case "tool":
      return node.tool_id ? { text: info.toolNames[node.tool_id] ?? node.tool_id, missing: false } : { text: "Choose a tool", missing: true }
    case "knowledge":
      return node.knowledge_base_ids.length
        ? { text: node.knowledge_base_ids.map((k) => info.kbNames[k] ?? k).join(", "), missing: false }
        : { text: "Choose a knowledge base", missing: true }
    case "transform":
      return { text: node.template || "Empty template", missing: !node.template.trim() }
    case "condition":
      return node.condition ? { text: `${node.condition.left} ${node.condition.op.replaceAll("_", " ")} ${node.condition.right}`, missing: false } : { text: "", missing: true }
  }
}

export function StepNodeView({ id, data, selected }: NodeProps<StepNode>) {
  const info = useContext(CanvasInfoContext)
  const s = data.step
  const meta = STEP_META[s.type]
  const accent = ACCENT[s.type]
  const lead = info.leads.get(id)
  const isMember = !!lead
  const sub = subtitle(s, info)
  const agentLike = s.type === "agent" || s.type === "supervisor"
  const model = agentLike && s.agent_id ? info.agentModels[s.agent_id] : undefined
  const team = info.teamSize.get(id) ?? 0
  return (
    <div className={cn(
      "group w-[248px] rounded-2xl border bg-card/95 text-card-foreground shadow-sm backdrop-blur transition-all",
      "hover:shadow-md", selected ? "border-primary/60 shadow-lg ring-2 ring-primary/30" : "border-border",
      s.type === "supervisor" && "w-[268px]",
    )}>
      <div className={cn("h-1.5 rounded-t-2xl bg-gradient-to-r", accent.bar)} />
      <div className="flex items-start gap-2.5 p-3 pb-2">
        <div className={cn("flex size-9 shrink-0 items-center justify-center rounded-xl", accent.chip)}>
          <meta.icon className="size-[18px]" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm leading-tight font-semibold">{s.name || (agentLike && s.agent_id ? info.agentNames[s.agent_id] : "") || meta.label}</div>
          <div className={cn("mt-0.5 flex items-center gap-1 truncate text-xs", sub.missing ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground")}>
            {sub.missing && <AlertTriangle className="size-3 shrink-0" aria-hidden />}
            <span className="truncate">{sub.text}</span>
          </div>
        </div>
        <span className="rounded-md border px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">{meta.label}</span>
      </div>
      {s.role && <p className="line-clamp-2 px-3 pb-2 text-xs text-muted-foreground">{s.role}</p>}
      <div className="flex flex-wrap items-center gap-1.5 border-t px-3 py-2 text-[11px] text-muted-foreground">
        <span className="font-mono">{id}</span>
        {model && <span className="truncate rounded bg-muted px-1.5 py-0.5 font-mono">{model}</span>}
        {s.type === "supervisor" && (
          <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-violet-500/10 px-2 py-0.5 font-medium text-violet-700 dark:text-violet-300">
            <Users className="size-3" aria-hidden /> {team} · {s.max_rounds} rounds
          </span>
        )}
        {isMember && s.type !== "supervisor" && <span className="ml-auto rounded-full bg-sky-500/10 px-2 py-0.5 text-sky-700 dark:text-sky-300">reports to {lead}</span>}
      </div>

      {agentLike && (
        <Handle type="target" position={Position.Top} id="lead" className={cn(handleBase, "!bg-violet-500")} title="Connect a supervisor here" />
      )}
      {s.type === "supervisor" && (
        <Handle type="source" position={Position.Bottom} id="team" className={cn(handleBase, "!size-3.5 !bg-violet-500")} title="Drag to an agent to add it to this team" />
      )}
      {!isMember && <Handle type="target" position={Position.Left} id="in" className={cn(handleBase, "!bg-slate-400")} />}
      {!isMember && (s.type === "condition" ? (
        <>
          <Handle type="source" position={Position.Right} id="true" style={{ top: "38%" }} className={cn(handleBase, "!bg-emerald-500")} title="If true" />
          <Handle type="source" position={Position.Right} id="false" style={{ top: "72%" }} className={cn(handleBase, "!bg-rose-500")} title="If false" />
          <span className="pointer-events-none absolute top-[38%] -right-9 -translate-y-1/2 text-[10px] font-medium text-emerald-600">true</span>
          <span className="pointer-events-none absolute top-[72%] -right-9 -translate-y-1/2 text-[10px] font-medium text-rose-600">false</span>
        </>
      ) : (
        <Handle type="source" position={Position.Right} id="out" className={cn(handleBase, "!bg-slate-400")} />
      ))}
    </div>
  )
}

export function StartNodeView() {
  return (
    <div className="flex items-center gap-2 rounded-full border bg-card px-4 py-2 text-sm font-medium shadow-sm">
      <span className="flex size-6 items-center justify-center rounded-full bg-emerald-500 text-white"><Play className="size-3 fill-current" aria-hidden /></span>
      Start
      <span className="text-xs font-normal text-muted-foreground">input.message</span>
      <Handle type="source" position={Position.Right} id="out" className={cn(handleBase, "!bg-emerald-500")} />
    </div>
  )
}

export function EndNodeView() {
  return (
    <div className="flex items-center gap-2 rounded-full border bg-card px-4 py-2 text-sm font-medium shadow-sm">
      <Handle type="target" position={Position.Left} id="in" className={cn(handleBase, "!bg-slate-400")} />
      <span className="flex size-6 items-center justify-center rounded-full bg-slate-700 text-white dark:bg-slate-300 dark:text-slate-900"><CircleStop className="size-3.5" aria-hidden /></span>
      End
    </div>
  )
}

function RemoveButton({ id, x, y }: { id: string; x: number; y: number }) {
  const { deleteElements } = useReactFlow()
  return (
    <EdgeLabelRenderer>
      <button type="button" aria-label="Remove connection"
        className="nodrag nopan pointer-events-auto absolute flex size-5 items-center justify-center rounded-full border bg-background text-muted-foreground shadow hover:text-destructive"
        style={{ transform: `translate(-50%, -50%) translate(${x}px, ${y}px)` }}
        onClick={() => deleteElements({ edges: [{ id }] })}>
        <X className="size-3" />
      </button>
    </EdgeLabelRenderer>
  )
}

export function FlowEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, markerEnd, selected, label }: EdgeProps) {
  const [path, x, y] = getSmoothStepPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, borderRadius: 14 })
  const color = label === "true" ? "#10b981" : label === "false" ? "#f43f5e" : "var(--color-muted-foreground)"
  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={{ stroke: color, strokeWidth: selected ? 2.5 : 1.75, opacity: selected ? 1 : 0.8 }} />
      {selected && <RemoveButton id={id} x={x} y={y} />}
    </>
  )
}

export function TeamEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, selected }: EdgeProps) {
  const [path, x, y] = getSmoothStepPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, borderRadius: 18 })
  return (
    <>
      <BaseEdge id={id} path={path} className="team-edge" style={{ stroke: "#8b5cf6", strokeWidth: selected ? 2.5 : 1.75, strokeDasharray: "6 5" }} />
      {selected && <RemoveButton id={id} x={x} y={y} />}
    </>
  )
}

export const nodeTypes = { step: StepNodeView, start: StartNodeView, end: EndNodeView }
export const edgeTypes = { flow: FlowEdge, team: TeamEdge }
