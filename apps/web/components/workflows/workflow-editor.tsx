"use client"

import { Plus } from "lucide-react"
import { useState } from "react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useAgents, useKnowledgeBases, useTools } from "@/hooks/use-api"
import { workflowDefinitionSchema, type StepType, type WorkflowDefinition } from "@/lib/schemas"
import { useWorkspaceCtx } from "@/lib/workspace-context"

import { StepEditor } from "./step-editor"
import { newStep, problemsOf, STEP_TYPES } from "./steps"
import { WorkflowDiagram } from "./workflow-diagram"

export interface WorkflowDraft {
  name: string
  description: string
  definition: WorkflowDefinition
}

export function WorkflowEditor({ initial, submitLabel, onSubmit }: { initial: WorkflowDraft; submitLabel: string; onSubmit: (d: WorkflowDraft) => Promise<void> }) {
  const { workspaceId } = useWorkspaceCtx()
  const agents = useAgents(workspaceId)
  const tools = useTools(workspaceId)
  const kbs = useKnowledgeBases(workspaceId)
  const [name, setName] = useState(initial.name)
  const [description, setDescription] = useState(initial.description)
  const [def, setDef] = useState<WorkflowDefinition>(initial.definition)
  const [addType, setAddType] = useState<StepType>("agent")
  const [mode, setMode] = useState<"visual" | "json">("visual")
  const [json, setJson] = useState("")
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [serverError, setServerError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const problems = problemsOf(def)
  const ids = def.steps.map((s) => s.id)
  const names = Object.fromEntries([
    ...(agents.data?.items ?? []).map((a) => [a.id, a.name]),
    ...(tools.data ?? []).map((t) => [t.id, t.name]),
    ...(kbs.data ?? []).map((k) => [k.id, k.name]),
  ])

  function update(i: number, s: WorkflowDefinition["steps"][number]) {
    const old = def.steps[i].id
    // keep routes pointing at a renamed step
    const steps = def.steps.map((x, j) => {
      const y = j === i ? s : x
      if (old === s.id) return y
      const fix = (v: string | null) => (v === old ? s.id : v)
      return { ...y, next: fix(y.next), on_true: fix(y.on_true), on_false: fix(y.on_false) }
    })
    setDef({ ...def, steps })
  }

  function move(i: number, dir: -1 | 1) {
    const steps = [...def.steps]
    const [s] = steps.splice(i, 1)
    steps.splice(i + dir, 0, s)
    setDef({ ...def, steps })
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setServerError(null)
    setSaving(true)
    try {
      await onSubmit({ name: name.trim(), description, definition: def })
    } catch (x) {
      setServerError(x instanceof Error ? x.message : "Save failed")
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-6 xl:grid-cols-[1fr_360px]" noValidate>
      <div className="min-w-0 space-y-4">
        {serverError && <Alert variant="destructive" role="alert"><AlertDescription>{serverError}</AlertDescription></Alert>}
        <Card>
          <CardHeader><CardTitle>Identity</CardTitle></CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="wf-name">Name</Label>
              <Input id="wf-name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="wf-max">Loop guard (max step executions)</Label>
              <Input id="wf-max" type="number" min={1} max={500} value={def.max_step_executions} onChange={(e) => setDef({ ...def, max_step_executions: Math.max(1, Math.min(500, Number(e.target.value) || 1)) })} />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="wf-desc">Description</Label>
              <Textarea id="wf-desc" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
          </CardContent>
        </Card>

        <div className="flex flex-wrap items-center gap-2">
          <h2 className="mr-auto text-lg font-semibold">Steps</h2>
          <div className="inline-flex rounded-md border p-0.5" role="group" aria-label="Editor mode">
            {(["visual", "json"] as const).map((m) => (
              <button key={m} type="button" aria-pressed={mode === m}
                className={`rounded px-2.5 py-1 text-sm ${mode === m ? "bg-accent font-medium" : "text-muted-foreground"}`}
                onClick={() => {
                  if (m === "json") setJson(JSON.stringify(def, null, 2))
                  setJsonError(null)
                  setMode(m)
                }}>
                {m === "visual" ? "Visual" : "JSON"}
              </button>
            ))}
          </div>
        </div>

        {mode === "json" ? (
          <Card>
            <CardContent className="space-y-2 pt-4">
              <Label htmlFor="wf-json" className="sr-only">Definition JSON</Label>
              <Textarea id="wf-json" rows={24} className="font-mono text-xs" value={json} aria-invalid={!!jsonError}
                onChange={(e) => {
                  setJson(e.target.value)
                  try {
                    const parsed = workflowDefinitionSchema.safeParse(JSON.parse(e.target.value))
                    if (!parsed.success) throw new Error(parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; "))
                    setDef(parsed.data)
                    setJsonError(null)
                  } catch (x) {
                    setJsonError((x as Error).message)
                  }
                }} />
              {jsonError && <p className="text-xs text-destructive">{jsonError}</p>}
            </CardContent>
          </Card>
        ) : (
          <>
            {def.steps.map((s, i) => (
              <StepEditor key={i} step={s} index={i} count={def.steps.length} ids={ids}
                agents={agents.data?.items ?? []} tools={tools.data ?? []} kbs={kbs.data ?? []}
                onChange={(x) => update(i, x)} onMove={(d) => move(i, d)}
                onRemove={() => setDef({ ...def, steps: def.steps.filter((_, j) => j !== i) })} />
            ))}
            <div className="flex flex-wrap items-end gap-2 rounded-xl border border-dashed p-4">
              <div className="space-y-1.5">
                <Label htmlFor="wf-add">Add a step</Label>
                <select id="wf-add" className="h-9 rounded-md border bg-background px-2 text-sm" value={addType} onChange={(e) => setAddType(e.target.value as StepType)}>
                  {STEP_TYPES.map((t) => <option key={t.type} value={t.type}>{t.label}</option>)}
                </select>
              </div>
              <Button type="button" variant="outline" disabled={def.steps.length >= 50} onClick={() => setDef({ ...def, steps: [...def.steps, newStep(addType, def.steps)] })}>
                <Plus className="size-4" /> Add step
              </Button>
              <p className="basis-full text-xs text-muted-foreground">
                Templates: <code>{"{{ input.message }}"}</code>, <code>{"{{ input.variables.name }}"}</code>, <code>{"{{ steps.<id>.text }}"}</code>, <code>{"{{ last.text }}"}</code>.
                Tool steps also expose <code>{"{{ steps.<id>.json.field }}"}</code> when the tool returns JSON.
              </p>
            </div>
          </>
        )}
      </div>

      <div className="space-y-4 xl:sticky xl:top-4 xl:self-start">
        <Card>
          <CardHeader>
            <CardTitle>Flow preview</CardTitle>
            <CardDescription>Steps run top to bottom unless a route says otherwise.</CardDescription>
          </CardHeader>
          <CardContent><WorkflowDiagram definition={def} names={names} /></CardContent>
        </Card>
        {problems.length > 0 && (
          <Alert>
            <AlertTitle>Fix before saving</AlertTitle>
            <AlertDescription><ul className="list-disc pl-4">{problems.map((p) => <li key={p}>{p}</li>)}</ul></AlertDescription>
          </Alert>
        )}
        <Button type="submit" className="w-full" disabled={saving || !name.trim() || problems.length > 0 || !!jsonError}>{saving ? "Saving…" : submitLabel}</Button>
      </div>
    </form>
  )
}
