"use client"

import "@xyflow/react/dist/style.css"

import {
  Background, BackgroundVariant, Controls, MarkerType, MiniMap, Panel, ReactFlow, ReactFlowProvider,
  applyEdgeChanges, applyNodeChanges, useReactFlow,
  type Connection, type Edge, type EdgeChange, type IsValidConnection, type NodeChange,
} from "@xyflow/react"
import { cn } from "cn"
import { LayoutGrid, Maximize2, Network, Trash2, X } from "lucide-react"
import { useTheme } from "next-themes"
import Link from "next/link"
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import type { Agent, KnowledgeBase, StepType, Tool, WorkflowDefinition, WorkflowStep } from "@/lib/schemas"

import { StepEditor } from "../step-editor"
import { newStep, STEP_META, STEP_TYPES } from "../steps"
import {
  autoLayout, createsLoop, END_NODE, flowEdge, fromGraph, isStepNode, START, teamEdge, teamTemplate, toGraph,
  type CanvasNode, type StepNode,
} from "./graph"
import { ACCENT, CanvasInfoContext, edgeTypes, nodeTypes, type CanvasInfo } from "./nodes"

const DND_TYPE = "application/x-workflow-step"

interface Props {
  definition: WorkflowDefinition
  onChange: (d: WorkflowDefinition) => void
  agents: Agent[]
  tools: Tool[]
  kbs: KnowledgeBase[]
  toolbar?: React.ReactNode
}

/** Node editor: agents and other steps are nodes; flow edges route the run, team edges make a
 * supervisor lead its members. The definition is re-derived from the graph on every change. */
export function AgentCanvas(props: Props) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  )
}

function CanvasInner({ definition, onChange, agents, tools, kbs, toolbar }: Props) {
  const initial = useMemo(() => toGraph(definition), []) // eslint-disable-line react-hooks/exhaustive-deps -- the canvas owns the graph after mount
  const [nodes, setNodes] = useState<CanvasNode[]>(initial.nodes)
  const [edges, setEdges] = useState<Edge[]>(initial.edges)
  const [selected, setSelectedRaw] = useState<string | null>(null)
  const [inspectorKey, setInspectorKey] = useState(0)
  const setSelected = useCallback((v: string | null | ((s: string | null) => string | null)) => {
    setSelectedRaw(v)
    setInspectorKey((k) => k + 1)
  }, [])
  const wrapper = useRef<HTMLDivElement>(null)
  const flow = useReactFlow()
  const { resolvedTheme } = useTheme()
  const base = useRef({ max_step_executions: definition.max_step_executions, max_delegations: definition.max_delegations })
  const emit = useRef(onChange)
  useLayoutEffect(() => {
    base.current = { max_step_executions: definition.max_step_executions, max_delegations: definition.max_delegations }
    emit.current = onChange
  })

  // Emit the definition whenever the graph changes (positions included, so layout is saved).
  useEffect(() => {
    emit.current(fromGraph(nodes, edges, base.current))
  }, [nodes, edges])

  const leads = useMemo(() => {
    const m = new Map<string, string>()
    for (const e of edges) if (e.sourceHandle === "team") m.set(e.target, e.source)
    return m
  }, [edges])
  const info: CanvasInfo = useMemo(() => {
    const teamSize = new Map<string, number>()
    for (const l of leads.values()) teamSize.set(l, (teamSize.get(l) ?? 0) + 1)
    return {
      agentNames: Object.fromEntries(agents.map((a) => [a.id, a.name])),
      agentModels: Object.fromEntries(agents.flatMap((a) => (a.draft.model ? [[a.id, a.draft.model.model]] : []))),
      toolNames: Object.fromEntries(tools.map((t) => [t.id, t.name])),
      kbNames: Object.fromEntries(kbs.map((k) => [k.id, k.name])),
      leads, teamSize,
    }
  }, [agents, tools, kbs, leads])

  const stepNodes = nodes.filter(isStepNode)
  const counts = {
    agents: stepNodes.filter((n) => n.data.step.type === "agent").length,
    supervisors: stepNodes.filter((n) => n.data.step.type === "supervisor").length,
    steps: stepNodes.length,
  }

  const onNodesChange = useCallback((changes: NodeChange<CanvasNode>[]) => {
    setNodes((ns) => applyNodeChanges(changes, ns))
    for (const c of changes) if (c.type === "remove") setSelected((s) => (s === c.id ? null : s))
  }, [setSelected])
  const onEdgesChange = useCallback((changes: EdgeChange[]) => setEdges((es) => applyEdgeChanges(changes, es)), [])

  const stepOf = useCallback((id: string) => {
    const n = nodes.find((x) => x.id === id)
    return n && isStepNode(n) ? n.data.step : undefined
  }, [nodes])

  const isValidConnection: IsValidConnection = useCallback((c) => {
    const { source, target, sourceHandle, targetHandle } = c
    if (!source || !target || source === target) return false
    if (sourceHandle === "team") {
      const t = stepOf(target)
      if (targetHandle !== "lead" || !t || (t.type !== "agent" && t.type !== "supervisor")) return false
      if (leads.has(target) && leads.get(target) !== source) return false // one supervisor per member
      if (edges.some((e) => e.sourceHandle !== "team" && (e.source === target || e.target === target))) return false
      return !createsLoop(edges, source, target)
    }
    if (targetHandle !== "in" || leads.has(target) || leads.has(source)) return false
    return true
  }, [edges, leads, stepOf])

  const onConnect = useCallback((c: Connection) => {
    if (!c.source || !c.target) return
    setEdges((es) => {
      if (c.sourceHandle === "team") {
        return es.some((e) => e.id === `team:${c.source}->${c.target}`) ? es : [...es, teamEdge(c.source!, c.target!)]
      }
      const handle = c.sourceHandle ?? "out"
      // one route per output handle: a new connection replaces the old one
      return [...es.filter((e) => !(e.source === c.source && (e.sourceHandle ?? "out") === handle)), flowEdge(c.source!, handle, c.target!)]
    })
  }, [])

  function centre(): { x: number; y: number } {
    const r = wrapper.current?.getBoundingClientRect()
    if (!r) return { x: 0, y: 0 }
    return flow.screenToFlowPosition({ x: r.left + r.width / 2 - 120, y: r.top + r.height / 2 - 60 })
  }

  function addStep(type: StepType, position = centre()) {
    const existing = stepNodes.map((n) => n.data.step)
    if (existing.length >= 50) return
    const s = { ...newStep(type, existing), position }
    setNodes((ns) => [...ns.map((n) => ({ ...n, selected: false })), { id: s.id, type: "step", position, data: { step: s }, selected: true } as StepNode])
    setSelected(s.id)
  }

  function addTeam(size = 4, origin = centre()) {
    const existing = stepNodes.map((n) => n.data.step)
    if (existing.length + size + 1 > 50) return
    const team = teamTemplate(existing, size, { x: origin.x, y: origin.y - 80 })
    setNodes((ns) => [...ns.map((n) => ({ ...n, selected: false })), ...team.map((s): StepNode => ({ id: s.id, type: "step", position: s.position!, data: { step: s } }))])
    setEdges((es) => [...es, ...team[0].delegates.map((d) => teamEdge(team[0].id, d))])
    setSelected(team[0].id)
  }

  function tidy() {
    const def = fromGraph(nodes, edges, base.current)
    const pos = autoLayout(def, true)
    setNodes((ns) => ns.map((n) => (pos[n.id] ? { ...n, position: pos[n.id] } : n)))
    window.requestAnimationFrame(() => flow.fitView({ padding: 0.2, duration: 400 }))
  }

  function updateStep(id: string, next: WorkflowStep) {
    let newId = next.id
    const taken = nodes.some((n) => n.id === newId && n.id !== id)
    if (!newId || taken || newId === START || newId === END_NODE) newId = id
    const step = { ...next, id: newId }
    setNodes((ns) => ns.map((n) => (n.id === id && isStepNode(n) ? { ...n, id: newId, data: { ...n.data, step } } : n)))
    if (newId !== id) {
      setEdges((es) => es.map((e) => {
        if (e.source !== id && e.target !== id) return e
        const source = e.source === id ? newId : e.source
        const target = e.target === id ? newId : e.target
        return e.sourceHandle === "team" ? teamEdge(source, target) : flowEdge(source, e.sourceHandle ?? "out", target)
      }))
      setSelectedRaw(newId) // keep the inspector mounted so typing in the id field keeps focus
    }
  }

  function removeStep(id: string) {
    flow.deleteElements({ nodes: [{ id }] })
    setSelected(null)
  }

  const current = selected ? nodes.find((n) => n.id === selected) : undefined
  const currentStep = current && isStepNode(current) ? current.data.step : undefined

  return (
    <CanvasInfoContext.Provider value={info}>
      <div ref={wrapper} className="workflow-canvas relative h-[74vh] min-h-[560px] overflow-hidden rounded-2xl border bg-gradient-to-br from-muted/40 via-background to-muted/30">
        <ReactFlow<CanvasNode, Edge>
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          isValidConnection={isValidConnection}
          onNodeClick={(_, n) => setSelected(isStepNode(n) ? n.id : null)}
          onPaneClick={() => setSelected(null)}
          onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move" }}
          onDrop={(e) => {
            e.preventDefault()
            const type = e.dataTransfer.getData(DND_TYPE) as StepType | "team" | ""
            if (!type) return
            const p = flow.screenToFlowPosition({ x: e.clientX - 120, y: e.clientY - 40 })
            if (type === "team") addTeam(4, p)
            else addStep(type, p)
          }}
          defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 } }}
          connectionLineStyle={{ strokeWidth: 2, stroke: "#8b5cf6" }}
          deleteKeyCode={["Backspace", "Delete"]}
          colorMode={resolvedTheme === "dark" ? "dark" : "light"}
          snapToGrid
          snapGrid={[10, 10]}
          minZoom={0.15}
          maxZoom={1.75}
          fitView
          fitViewOptions={{ padding: 0.2 }}
        >
          <Background variant={BackgroundVariant.Dots} gap={22} size={1.4} className="!bg-transparent" />
          <MiniMap pannable zoomable className="!rounded-xl !border !bg-card/90"
            nodeColor={(n) => (isStepNode(n as CanvasNode) ? ACCENT[(n as StepNode).data.step.type].hex : "#94a3b8")}
            nodeBorderRadius={8} />
          <Controls showInteractive={false} className="!overflow-hidden !rounded-xl !border !shadow-sm" />

          <Panel position="top-left" className="!m-3">
            <div className="w-[200px] space-y-0.5 rounded-2xl border bg-card/95 p-2 shadow-sm backdrop-blur">
              <p className="px-2 pt-1 pb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Add node</p>
              {STEP_TYPES.map((t) => (
                <button key={t.type} type="button" draggable title={t.help}
                  onDragStart={(e) => { e.dataTransfer.setData(DND_TYPE, t.type); e.dataTransfer.effectAllowed = "move" }}
                  onClick={() => addStep(t.type)}
                  className="flex w-full cursor-grab items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-accent active:cursor-grabbing">
                  <span className={cn("flex size-6 items-center justify-center rounded-md", ACCENT[t.type].chip)}><t.icon className="size-3.5" aria-hidden /></span>
                  {t.label}
                </button>
              ))}
              <div className="my-1 border-t" />
              <button type="button" draggable onClick={() => addTeam()} title="A supervisor with four agents, already connected"
                onDragStart={(e) => { e.dataTransfer.setData(DND_TYPE, "team"); e.dataTransfer.effectAllowed = "move" }}
                className="flex w-full items-center gap-2 rounded-lg bg-gradient-to-r from-violet-500/10 to-fuchsia-500/10 px-2 py-1.5 text-left text-sm font-medium hover:from-violet-500/20 hover:to-fuchsia-500/20">
                <span className="flex size-6 items-center justify-center rounded-md bg-violet-500 text-white"><Network className="size-3.5" aria-hidden /></span>
                Team template
              </button>
              <div className="my-1 border-t" />
              <p className="px-2 py-1 text-[11px] text-muted-foreground tabular-nums">
                {counts.supervisors} supervisor{counts.supervisors === 1 ? "" : "s"} · {counts.agents} agent{counts.agents === 1 ? "" : "s"} · {counts.steps}/50 nodes
              </p>
              <div className="flex gap-1">
                <Button type="button" variant="ghost" size="sm" className="h-7 flex-1" onClick={tidy}><LayoutGrid className="size-3.5" /> Tidy</Button>
                <Button type="button" variant="ghost" size="sm" className="h-7 flex-1" onClick={() => flow.fitView({ padding: 0.2, duration: 400 })}><Maximize2 className="size-3.5" /> Fit</Button>
              </div>
              {toolbar}
            </div>
          </Panel>

          {!selected && <Panel position="bottom-center" className="!mb-3">
            <div className="flex items-center gap-4 rounded-full border bg-card/95 px-4 py-1.5 text-[11px] whitespace-nowrap text-muted-foreground shadow-sm backdrop-blur max-lg:hidden">
              <span className="flex items-center gap-1.5"><svg width="26" height="6" aria-hidden><line x1="0" y1="3" x2="26" y2="3" stroke="currentColor" strokeWidth="2" /></svg> flow: runs left to right</span>
              <span className="flex items-center gap-1.5"><svg width="26" height="6" aria-hidden><line x1="0" y1="3" x2="26" y2="3" stroke="#8b5cf6" strokeWidth="2" strokeDasharray="5 4" /></svg> team: supervisor delegates to member</span>
              <span>Select a connection, then Delete to remove it</span>
            </div>
          </Panel>}
        </ReactFlow>

        {currentStep && current && (
          <aside className="absolute top-3 right-3 bottom-3 z-10 flex w-[380px] max-w-[calc(100%-1.5rem)] flex-col overflow-hidden rounded-2xl border bg-card shadow-xl" aria-label="Node settings">
            <div className="flex items-center gap-2 border-b px-4 py-3">
              {(() => { const M = STEP_META[currentStep.type]; return <span className={cn("flex size-8 items-center justify-center rounded-lg", ACCENT[currentStep.type].chip)}><M.icon className="size-4" aria-hidden /></span> })()}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{currentStep.name || STEP_META[currentStep.type].label}</p>
                <p className="truncate text-xs text-muted-foreground">{STEP_META[currentStep.type].help}</p>
              </div>
              <Button type="button" variant="ghost" size="icon" aria-label="Delete node" onClick={() => removeStep(current.id)}><Trash2 className="size-4" /></Button>
              <Button type="button" variant="ghost" size="icon" aria-label="Close" onClick={() => setSelected(null)}><X className="size-4" /></Button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <StepEditor key={inspectorKey} compact step={currentStep} index={0} count={1} ids={stepNodes.map((n) => n.id)}
                agents={agents} tools={tools} kbs={kbs} onChange={(s) => updateStep(current.id, s)} />
              {(currentStep.type === "agent" || currentStep.type === "supervisor") && agents.length === 0 && (
                <p className="mt-3 text-xs text-muted-foreground">No agents yet. <Link href="/agents/new" className="underline">Create one</Link> and publish it.</p>
              )}
              {leads.has(current.id) && (
                <p className="mt-3 rounded-lg bg-violet-500/10 p-2 text-xs text-violet-800 dark:text-violet-200">
                  Reports to <span className="font-mono">{leads.get(current.id)}</span>. It runs only when its supervisor delegates a task, so it has no flow connections.
                </p>
              )}
            </div>
          </aside>
        )}
      </div>
    </CanvasInfoContext.Provider>
  )
}
