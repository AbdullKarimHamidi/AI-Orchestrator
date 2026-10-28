"use client"

import { ArrowDown, ArrowUp, Trash2 } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type { Agent, KnowledgeBase, Tool, WorkflowStep } from "@/lib/schemas"

import { OPS, STEP_META } from "./steps"

const selectCls = "h-9 w-full rounded-md border bg-background px-2 text-sm"

function RouteSelect({ id, label, value, onChange, ids, fallback }: { id: string; label: string; value: string | null; onChange: (v: string | null) => void; ids: string[]; fallback: string }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <select id={id} className={selectCls} value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">{fallback}</option>
        {ids.map((i) => <option key={i} value={i}>{i}</option>)}
        <option value="end">end (stop here)</option>
      </select>
    </div>
  )
}

function ArgumentsEditor({ id, value, onChange }: { id: string; value: Record<string, unknown>; onChange: (v: Record<string, unknown>) => void }) {
  const [text, setText] = useState(JSON.stringify(value, null, 2))
  const [error, setError] = useState<string | null>(null)
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>Arguments (JSON; string values may use templates)</Label>
      <Textarea id={id} rows={4} className="font-mono text-xs" value={text} aria-invalid={!!error}
        onChange={(e) => {
          setText(e.target.value)
          try {
            const v = JSON.parse(e.target.value || "{}")
            if (typeof v !== "object" || v === null || Array.isArray(v)) throw new Error("must be an object")
            setError(null)
            onChange(v as Record<string, unknown>)
          } catch (x) {
            setError(`Invalid JSON: ${(x as Error).message}`)
          }
        }} />
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

export function StepEditor({ step, index, count, ids, agents, tools, kbs, onChange, onMove, onRemove }: {
  step: WorkflowStep
  index: number
  count: number
  ids: string[]
  agents: Agent[]
  tools: Tool[]
  kbs: KnowledgeBase[]
  onChange: (s: WorkflowStep) => void
  onMove: (dir: -1 | 1) => void
  onRemove: () => void
}) {
  const Meta = STEP_META[step.type]
  const p = `step-${index}`
  const set = (patch: Partial<WorkflowStep>) => onChange({ ...step, ...patch })
  const others = ids.filter((i) => i !== step.id)
  return (
    <section className="rounded-xl border bg-card p-4" aria-label={`Step ${index + 1}: ${step.id}`}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="flex size-7 items-center justify-center rounded-md bg-muted text-xs font-semibold tabular-nums">{index + 1}</span>
        <Meta.icon className="size-4 text-muted-foreground" aria-hidden />
        <span className="font-medium">{Meta.label}</span>
        <span className="text-xs text-muted-foreground">{Meta.help}</span>
        <div className="ml-auto flex gap-1">
          <Button type="button" variant="ghost" size="icon" disabled={index === 0} onClick={() => onMove(-1)} aria-label="Move up"><ArrowUp className="size-4" /></Button>
          <Button type="button" variant="ghost" size="icon" disabled={index === count - 1} onClick={() => onMove(1)} aria-label="Move down"><ArrowDown className="size-4" /></Button>
          <Button type="button" variant="ghost" size="icon" onClick={onRemove} aria-label={`Remove step ${step.id}`}><Trash2 className="size-4" /></Button>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={`${p}-id`}>Step id</Label>
          <Input id={`${p}-id`} className="font-mono text-sm" value={step.id} onChange={(e) => set({ id: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${p}-name`}>Label</Label>
          <Input id={`${p}-name`} value={step.name} placeholder={Meta.label} onChange={(e) => set({ name: e.target.value })} />
        </div>

        {step.type === "agent" && (
          <>
            <div className="space-y-1.5">
              <Label htmlFor={`${p}-agent`}>Agent (published version runs)</Label>
              <select id={`${p}-agent`} className={selectCls} value={step.agent_id ?? ""} onChange={(e) => set({ agent_id: e.target.value || null })}>
                <option value="">Select an agent…</option>
                {agents.map((a) => <option key={a.id} value={a.id}>{a.name} {a.published_version ? `(v${a.published_version})` : `(${a.status})`}</option>)}
              </select>
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor={`${p}-msg`}>Message sent to the agent</Label>
              <Textarea id={`${p}-msg`} rows={3} className="font-mono text-xs" value={step.message} onChange={(e) => set({ message: e.target.value })} />
            </div>
          </>
        )}

        {step.type === "tool" && (
          <>
            <div className="space-y-1.5">
              <Label htmlFor={`${p}-tool`}>Tool</Label>
              <select id={`${p}-tool`} className={selectCls} value={step.tool_id ?? ""} onChange={(e) => set({ tool_id: e.target.value || null })}>
                <option value="">Select a tool…</option>
                {tools.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.kind})</option>)}
              </select>
            </div>
            <div className="sm:col-span-2"><ArgumentsEditor id={`${p}-args`} value={step.arguments} onChange={(v) => set({ arguments: v })} /></div>
          </>
        )}

        {step.type === "knowledge" && (
          <>
            <fieldset className="space-y-1.5 sm:col-span-2">
              <legend className="text-sm font-medium">Knowledge bases</legend>
              {kbs.length === 0 && <p className="text-sm text-muted-foreground">No knowledge bases yet.</p>}
              <div className="flex flex-wrap gap-3">
                {kbs.map((k) => (
                  <label key={k.id} className="flex items-center gap-1.5 text-sm">
                    <input type="checkbox" className="size-4" checked={step.knowledge_base_ids.includes(k.id)}
                      onChange={(e) => set({ knowledge_base_ids: e.target.checked ? [...step.knowledge_base_ids, k.id] : step.knowledge_base_ids.filter((x) => x !== k.id) })} />
                    {k.name}
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="space-y-1.5">
              <Label htmlFor={`${p}-query`}>Search query</Label>
              <Input id={`${p}-query`} className="font-mono text-xs" value={step.query} onChange={(e) => set({ query: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`${p}-k`}>Passages</Label>
              <Input id={`${p}-k`} type="number" min={1} max={20} value={step.top_k} onChange={(e) => set({ top_k: Math.max(1, Math.min(20, Number(e.target.value) || 1)) })} />
            </div>
          </>
        )}

        {step.type === "transform" && (
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor={`${p}-tpl`}>Template</Label>
            <Textarea id={`${p}-tpl`} rows={3} className="font-mono text-xs" value={step.template} onChange={(e) => set({ template: e.target.value })} />
          </div>
        )}

        {step.type === "condition" && step.condition && (
          <>
            <div className="space-y-1.5">
              <Label htmlFor={`${p}-left`}>Value</Label>
              <Input id={`${p}-left`} className="font-mono text-xs" value={step.condition.left} onChange={(e) => set({ condition: { ...step.condition!, left: e.target.value } })} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label htmlFor={`${p}-op`}>Operator</Label>
                <select id={`${p}-op`} className={selectCls} value={step.condition.op} onChange={(e) => set({ condition: { ...step.condition!, op: e.target.value as typeof step.condition.op } })}>
                  {OPS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={`${p}-right`}>Compared with</Label>
                <Input id={`${p}-right`} className="font-mono text-xs" value={step.condition.right} disabled={["is_empty", "not_empty"].includes(step.condition.op)} onChange={(e) => set({ condition: { ...step.condition!, right: e.target.value } })} />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="size-4" checked={step.condition.case_sensitive} onChange={(e) => set({ condition: { ...step.condition!, case_sensitive: e.target.checked } })} /> Case sensitive
            </label>
            <div />
            <RouteSelect id={`${p}-true`} label="If true, go to" value={step.on_true} onChange={(v) => set({ on_true: v })} ids={others} fallback="the next step" />
            <RouteSelect id={`${p}-false`} label="If false, go to" value={step.on_false} onChange={(v) => set({ on_false: v })} ids={others} fallback="the next step" />
          </>
        )}

        {step.type !== "condition" && (
          <RouteSelect id={`${p}-next`} label="Then go to" value={step.next} onChange={(v) => set({ next: v })} ids={others} fallback="the next step" />
        )}
      </div>
    </section>
  )
}
