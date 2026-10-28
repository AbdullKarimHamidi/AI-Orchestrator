"use client"

import { Plus, Trash2 } from "lucide-react"
import Link from "next/link"
import { useState } from "react"
import { toast } from "sonner"

import { ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { EvalNav } from "@/components/evaluations/eval-nav"
import { parseCases, type CaseRow } from "@/components/evaluations/parse-cases"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useDatasets, useEvalMutations } from "@/hooks/use-modules"
import { errorMessage } from "@/lib/api-client"
import { fmtRelative } from "@/lib/format"
import type { Dataset } from "@/lib/schemas"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

type Row = CaseRow

function DatasetEditor({ dataset, onDone }: { dataset: Dataset | null; onDone: (id?: string) => void }) {
  const { workspaceId, role } = useWorkspaceCtx()
  const m = useEvalMutations(workspaceId)
  const [name, setName] = useState(dataset?.name ?? "")
  const [description, setDescription] = useState(dataset?.description ?? "")
  const [rows, setRows] = useState<Row[]>(dataset?.cases.map((c) => ({ id: c.id, input: c.input, expected: c.expected })) ?? [{ id: "", input: "", expected: "" }])
  const [bulk, setBulk] = useState("")
  const canWrite = can(role, "agents:write")
  const valid = rows.filter((r) => r.input.trim())

  async function save() {
    const body = { name: name.trim(), description, cases: valid.map((r) => ({ id: r.id, input: r.input, expected: r.expected })) }
    try {
      if (dataset) {
        await m.updateDataset.mutateAsync({ id: dataset.id, ...body })
        toast.success("Dataset saved")
        onDone(dataset.id)
      } else {
        const d = await m.createDataset.mutateAsync(body)
        toast.success("Dataset created")
        onDone(d.id)
      }
    } catch (x) {
      toast.error(errorMessage(x))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{dataset ? `Edit "${dataset.name}"` : "New dataset"}</CardTitle>
        <CardDescription>Each case is sent to the agent as <code>input.message</code>. &quot;Expected&quot; is what the scorer checks the output against (text, or a regex with the regex scorer).</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5"><Label htmlFor="ds-name">Name</Label><Input id="ds-name" value={name} onChange={(e) => setName(e.target.value)} disabled={!canWrite} /></div>
          <div className="space-y-1.5"><Label htmlFor="ds-desc">Description</Label><Input id="ds-desc" value={description} onChange={(e) => setDescription(e.target.value)} disabled={!canWrite} /></div>
        </div>
        <div className="space-y-2">
          <div className="hidden grid-cols-[110px_1fr_1fr_36px] gap-2 text-xs font-medium text-muted-foreground sm:grid"><span>Case id</span><span>Input</span><span>Expected</span><span /></div>
          {rows.map((r, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-[110px_1fr_1fr_36px]">
              <Input aria-label={`Case ${i + 1} id`} className="font-mono text-xs" placeholder={`case_${i + 1}`} value={r.id} disabled={!canWrite} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, id: e.target.value } : x)))} />
              <Textarea aria-label={`Case ${i + 1} input`} rows={2} value={r.input} disabled={!canWrite} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, input: e.target.value } : x)))} />
              <Textarea aria-label={`Case ${i + 1} expected`} rows={2} value={r.expected} disabled={!canWrite} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, expected: e.target.value } : x)))} />
              {canWrite && <Button type="button" variant="ghost" size="icon" aria-label={`Remove case ${i + 1}`} onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>}
            </div>
          ))}
          {canWrite && <Button type="button" variant="outline" size="sm" disabled={rows.length >= 500} onClick={() => setRows([...rows, { id: "", input: "", expected: "" }])}><Plus className="size-4" /> Add case</Button>}
        </div>
        {canWrite && (
          <details className="rounded-lg border p-3">
            <summary className="cursor-pointer text-sm font-medium">Bulk import</summary>
            <p className="mt-2 text-xs text-muted-foreground">Paste a JSON array, JSON Lines (<code>{'{"input": "...", "expected": "..."}'}</code> per line), or one <code>input | expected</code> per line. Imported cases are appended.</p>
            <Label htmlFor="ds-bulk" className="sr-only">Cases to import</Label>
            <Textarea id="ds-bulk" rows={5} className="mt-2 font-mono text-xs" value={bulk} onChange={(e) => setBulk(e.target.value)} placeholder={"What is 2+2? | 4\nCapital of France? | Paris"} />
            <Button type="button" size="sm" variant="outline" className="mt-2" onClick={() => {
              try {
                const parsed = parseCases(bulk)
                setRows([...rows.filter((r) => r.input.trim()), ...parsed])
                setBulk("")
                toast.success(`${parsed.length} cases added`)
              } catch (x) {
                toast.error(`Could not parse: ${(x as Error).message}`)
              }
            }}>Import</Button>
          </details>
        )}
        {canWrite && (
          <div className="flex flex-wrap gap-2">
            <Button onClick={save} disabled={!name.trim() || m.createDataset.isPending || m.updateDataset.isPending}>{dataset ? "Save dataset" : "Create dataset"}</Button>
            {dataset && <Link href={`/evaluations/runs?dataset=${dataset.id}`} className={buttonVariants({ variant: "outline" })}>Evaluate an agent on it</Link>}
            {dataset && (
              <Button variant="ghost" className="ml-auto text-destructive" onClick={async () => {
                if (!window.confirm(`Delete dataset "${dataset.name}"? Past evaluation runs are kept.`)) return
                try {
                  await m.removeDataset.mutateAsync(dataset.id)
                  toast.success("Dataset deleted")
                  onDone()
                } catch (x) {
                  toast.error(errorMessage(x))
                }
              }}>Delete</Button>
            )}
            <span className="self-center text-sm text-muted-foreground">{valid.length} case{valid.length === 1 ? "" : "s"}</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function DatasetsPage() {
  const { workspaceId, role } = useWorkspaceCtx()
  const datasets = useDatasets(workspaceId)
  // null = show the first dataset (or the "new" form when there is none)
  const [selected, setSelected] = useState<string | null>(null)
  const active = selected ?? datasets.data?.[0]?.id ?? "new"
  const shown = active === "new" ? null : datasets.data?.find((d) => d.id === active) ?? null
  return (
    <div>
      <PageHeader title="Evaluation datasets" description="Reusable sets of test cases: inputs with expected answers." />
      <EvalNav />
      {datasets.isPending ? <LoadingRows /> : datasets.isError ? <ErrorState error={datasets.error} onRetry={() => datasets.refetch()} /> : (
        <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
          <div className="space-y-2">
            {can(role, "agents:write") && <Button variant={active === "new" ? "default" : "outline"} className="w-full" onClick={() => setSelected("new")}><Plus className="size-4" /> New dataset</Button>}
            <ul className="space-y-1" aria-label="Datasets">
              {datasets.data.map((d) => (
                <li key={d.id}>
                  <button type="button" onClick={() => setSelected(d.id)} aria-current={active === d.id ? "true" : undefined}
                    className={`w-full rounded-md border px-3 py-2 text-left ${active === d.id ? "border-primary bg-accent" : "hover:bg-muted"}`}>
                    <span className="block truncate text-sm font-medium">{d.name}</span>
                    <span className="block text-xs text-muted-foreground">{d.case_count} cases · {fmtRelative(d.updated_at)}</span>
                  </button>
                </li>
              ))}
              {datasets.data.length === 0 && <li className="px-1 text-sm text-muted-foreground">No datasets yet.</li>}
            </ul>
          </div>
          <DatasetEditor key={shown ? `${shown.id}:${shown.updated_at}` : "new"} dataset={shown} onDone={(id) => setSelected(id ?? null)} />
        </div>
      )}
    </div>
  )
}
