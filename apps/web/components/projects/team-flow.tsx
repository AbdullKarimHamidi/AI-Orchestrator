"use client"

import "@xyflow/react/dist/style.css"

import { useQuery } from "@tanstack/react-query"
import { Background, BackgroundVariant, Controls, Handle, MarkerType, Position, ReactFlow, ReactFlowProvider, type Edge, type Node, type NodeProps } from "@xyflow/react"
import { cn } from "cn"
import { CheckCircle2, Crown, Loader2, ShieldCheck, Users, XCircle } from "lucide-react"
import Link from "next/link"
import { useMemo, useState } from "react"
import { z } from "zod"

import { END_NODE, START, toGraph } from "@/components/workflows/canvas/graph"
import { useWorkflow } from "@/hooks/use-modules"
import { api } from "@/lib/api-client"
import { runEventSchema, type RunEvent, type WorkflowStep } from "@/lib/schemas"
import type { Project } from "@/lib/schemas/projects"

type Status = "idle" | "working" | "planning" | "done" | "failed"
export type NodeActivity = { status: Status; tasks: number; done: number; failed: number; lastTask?: string; lastResult?: string; error?: string; thoughts?: string }
type LiveData = { step: WorkflowStep; agentName: string; activity: NodeActivity; isReviewer: boolean; isDirector: boolean }
type LiveNode = Node<LiveData, "live">
type EndNode = Node<{ label: string; active: boolean }, "terminal">

const ACTIVE = ["queued", "running", "waiting_for_approval"]

/** Per-step activity from a workflow run's events: who is working, on what, and with what result. */
export function activityFromEvents(events: RunEvent[]): Record<string, NodeActivity> {
  const act: Record<string, NodeActivity> = {}
  const get = (id: string) => (act[id] ??= { status: "idle", tasks: 0, done: 0, failed: 0 })
  for (const e of events) {
    const d = e.data as Record<string, unknown>
    const step = typeof d.step === "string" ? d.step : ""
    const member = typeof d.member === "string" ? d.member : ""
    switch (e.type) {
      case "workflow.step.started": get(step).status = "working"; break
      case "workflow.step.completed": Object.assign(get(step), { status: "done", lastResult: String(d.preview ?? "") }); break
      case "workflow.step.failed": Object.assign(get(step), { status: "failed", error: String(d.error ?? "") }); break
      case "team.plan": Object.assign(get(step), { status: "planning", thoughts: String(d.thoughts ?? "") }); break
      case "team.task.started": { const a = get(member); a.tasks++; a.status = "working"; a.lastTask = String(d.task ?? ""); if (get(step).status === "planning") get(step).status = "working"; break }
      case "team.task.completed": { const a = get(member); a.done++; a.lastResult = String(d.preview ?? ""); if (a.done + a.failed >= a.tasks) a.status = "done"; break }
      case "team.task.failed": { const a = get(member); a.failed++; a.error = String(d.error ?? ""); if (a.done + a.failed >= a.tasks) a.status = "failed"; break }
      case "team.completed": get(step).status = "done"; break
    }
  }
  return act
}

const ring: Record<Status, string> = {
  idle: "border-border",
  working: "border-sky-500 shadow-[0_0_0_4px_rgba(14,165,233,0.15)]",
  planning: "border-violet-500 shadow-[0_0_0_4px_rgba(139,92,246,0.15)]",
  done: "border-emerald-500",
  failed: "border-destructive",
}
const label: Record<Status, string> = { idle: "Waiting", working: "Working", planning: "Assigning tasks", done: "Done", failed: "Failed" }

function LiveNodeView({ data, selected }: NodeProps<LiveNode>) {
  const { step, activity: a } = data
  const lead = step.type === "supervisor"
  const Icon = data.isDirector ? Crown : data.isReviewer ? ShieldCheck : lead ? Users : null
  return (
    <div className={cn("w-[230px] rounded-xl border-2 bg-card p-3 text-left shadow-sm transition-colors", ring[a.status], selected && "ring-2 ring-primary")}>
      <Handle type="target" position={Position.Top} id="lead" className="!size-2 !bg-violet-500" />
      <Handle type="target" position={Position.Left} id="in" className="!size-2 !bg-slate-400" />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 truncate text-sm font-semibold">{Icon && <Icon className={cn("size-3.5 shrink-0", data.isDirector ? "text-violet-500" : data.isReviewer ? "text-emerald-500" : "text-sky-500")} />}{step.name || step.id}</p>
          <p className="truncate text-xs text-muted-foreground">{data.agentName}{step.model ? ` · ${step.model.model}` : ""}</p>
        </div>
        {a.status === "working" || a.status === "planning" ? <Loader2 className="size-4 shrink-0 animate-spin text-sky-500" /> : a.status === "done" ? <CheckCircle2 className="size-4 shrink-0 text-emerald-500" /> : a.status === "failed" ? <XCircle className="size-4 shrink-0 text-destructive" /> : null}
      </div>
      <p className="mt-2 text-[11px] font-medium">{label[a.status]}{a.tasks ? ` · ${a.done}/${a.tasks} tasks` : ""}</p>
      {(a.thoughts || a.lastTask) && <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">{a.status === "planning" ? a.thoughts : a.lastTask}</p>}
      <Handle type="source" position={Position.Right} id="out" className="!size-2 !bg-slate-400" />
      {lead && <Handle type="source" position={Position.Bottom} id="team" className="!size-2 !bg-violet-500" />}
    </div>
  )
}

function TerminalView({ data }: NodeProps<EndNode>) {
  return (
    <div className={cn("rounded-full border-2 bg-card px-4 py-2 text-xs font-semibold", data.active ? "border-emerald-500 text-emerald-600" : "border-border text-muted-foreground")}>
      <Handle type="target" position={Position.Left} id="in" className="!size-2" />
      {data.label}
      <Handle type="source" position={Position.Right} id="out" className="!size-2" />
    </div>
  )
}

const nodeTypes = { live: LiveNodeView, terminal: TerminalView }

export function TeamFlow({ project, workspaceId, agentNames }: { project: Project; workspaceId: string | null; agentNames: Record<string, string> }) {
  return <ReactFlowProvider><TeamFlowInner project={project} workspaceId={workspaceId} agentNames={agentNames} /></ReactFlowProvider>
}

function TeamFlowInner({ project, workspaceId, agentNames }: { project: Project; workspaceId: string | null; agentNames: Record<string, string> }) {
  const [round, setRound] = useState<string>("")
  const [picked, setPicked] = useState<string | null>(null)
  const runs = project.build_runs
  const run = runs.find((r) => r.run_id === round) ?? runs[runs.length - 1]
  const workflow = useWorkflow(workspaceId, project.build_workflow_id ?? "")
  const events = useQuery({
    queryKey: ["run-events", workspaceId, run?.run_id],
    queryFn: () => api.get(`/runs/${run!.run_id}/events`, z.array(runEventSchema)),
    enabled: !!workspaceId && !!run,
    refetchInterval: run && ACTIVE.includes(run.status) ? 2000 : false,
  })
  const def = workflow.data?.draft
  const activity = useMemo(() => activityFromEvents(events.data ?? []), [events.data])
  const finished = run?.status === "completed"

  const graph = useMemo(() => {
    if (!def) return { nodes: [] as Node[], edges: [] as Edge[] }
    const g = toGraph(def)
    const nodes: Node[] = g.nodes.map((n) => {
      if (n.id === START || n.id === END_NODE) return { id: n.id, type: "terminal", position: n.position, data: { label: n.id === START ? "Plan" : "Project", active: n.id === START || finished }, draggable: true } satisfies EndNode
      const step = (n.data as { step: WorkflowStep }).step
      return {
        id: n.id, type: "live", position: n.position,
        data: { step, agentName: agentNames[step.agent_id ?? ""] ?? "Agent", activity: activity[step.id] ?? { status: "idle", tasks: 0, done: 0, failed: 0 }, isReviewer: !!step.role?.startsWith("Plan compliance reviewer"), isDirector: step.id === "director" },
      } satisfies LiveNode
    })
    const busy = (id: string) => ["working", "planning"].includes(activity[id]?.status ?? "")
    const edges: Edge[] = g.edges.map((e) => ({
      id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle, type: "smoothstep",
      animated: busy(e.target) || (e.data?.kind === "flow" && busy(e.source)),
      style: { stroke: e.data?.kind === "team" ? "#8b5cf6" : "#94a3b8", strokeWidth: 1.6, strokeDasharray: e.data?.kind === "team" ? "5 4" : undefined },
      markerEnd: { type: MarkerType.ArrowClosed, color: e.data?.kind === "team" ? "#8b5cf6" : "#94a3b8" },
    }))
    return { nodes, edges }
  }, [def, activity, agentNames, finished])

  if (!project.build_workflow_id) return <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">Start a build to see the agents as nodes. Each node shows what that agent is doing, live.</p>
  const pickedStep = def?.steps.find((s) => s.id === picked)
  const pickedAct = picked ? activity[picked] : undefined
  const log = (events.data ?? []).filter((e) => picked && ((e.data as Record<string, unknown>).member === picked || (e.data as Record<string, unknown>).step === picked)).slice(-30)

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">Purple dashed lines show who hands tasks to whom. Blue nodes are working now. Click a node to see its tasks.</p>
        <div className="flex items-center gap-2">
          {runs.length > 1 && <select aria-label="Build round" className="h-8 rounded-md border bg-background px-2 text-sm" value={run?.run_id ?? ""} onChange={(e) => setRound(e.target.value)}>{runs.map((r) => <option key={r.run_id} value={r.run_id}>Round {r.round}</option>)}</select>}
          {project.build_workflow_id && <Link href={`/workflows/${project.build_workflow_id}/edit`} className="text-sm underline">Edit on the canvas</Link>}
          {run && <Link href={`/runs/${run.run_id}`} className="text-sm underline">Full run log</Link>}
        </div>
      </div>
      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="h-[620px] overflow-hidden rounded-xl border bg-muted/20" data-testid="team-flow">
          <ReactFlow nodes={graph.nodes} edges={graph.edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.08, minZoom: 0.55, maxZoom: 1 }} minZoom={0.2} nodesConnectable={false} nodesDraggable onNodeClick={(_, n) => setPicked(n.type === "live" ? n.id : null)} proOptions={{ hideAttribution: true }}>
            <Background variant={BackgroundVariant.Dots} gap={18} size={1} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
        <div className="space-y-3 rounded-xl border p-4 text-sm 2xl:max-h-[620px] 2xl:overflow-auto">
          {!pickedStep ? <p className="text-muted-foreground">Select an agent node to see its role, tasks and results.</p> : <>
            <div><p className="font-semibold">{pickedStep.name || pickedStep.id}</p><p className="text-xs text-muted-foreground">{agentNames[pickedStep.agent_id ?? ""] ?? "Agent"}{pickedStep.model ? ` · ${pickedStep.model.model}` : ""}</p></div>
            {pickedStep.role && <p className="text-xs">{pickedStep.role}</p>}
            <p className="text-xs font-medium">{label[pickedAct?.status ?? "idle"]}{pickedAct?.tasks ? ` · ${pickedAct.done}/${pickedAct.tasks} tasks` : ""}</p>
            {pickedAct?.error && <p className="text-xs text-destructive">{pickedAct.error}</p>}
            <div className="max-h-[440px] space-y-2 overflow-auto">
              {log.length === 0 && <p className="text-xs text-muted-foreground">No activity in this round yet.</p>}
              {log.map((e) => { const d = e.data as Record<string, unknown>; const text = String(d.task ?? d.preview ?? d.thoughts ?? d.error ?? ""); return text ? <div key={e.seq} className="rounded-md border p-2"><p className="text-[11px] font-medium text-muted-foreground">{e.type.replace("team.", "").replace("workflow.", "").replaceAll(".", " ")}</p><p className="mt-0.5 line-clamp-6 whitespace-pre-wrap text-xs">{text}</p></div> : null })}
            </div>
          </>}
        </div>
      </div>
    </div>
  )
}
