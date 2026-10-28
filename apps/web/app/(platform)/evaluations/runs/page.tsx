"use client"

import { ChevronDown, ChevronRight } from "lucide-react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { Fragment, Suspense, useState } from "react"
import { toast } from "sonner"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { StatusBadge } from "@/components/common/status-badge"
import { EvalNav, PassRate, SCORERS } from "@/components/evaluations/eval-nav"
import { ResultsTable } from "@/components/evaluations/results-table"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAgents } from "@/hooks/use-api"
import { useDatasets, useEvalMutations, useEvalRuns } from "@/hooks/use-modules"
import { errorMessage } from "@/lib/api-client"
import { fmtMs, fmtRelative, fmtUsd } from "@/lib/format"
import type { ScorerType } from "@/lib/schemas"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

const selectCls = "h-9 w-full rounded-md border bg-background px-2 text-sm"

function NewEvaluation({ onCreated, initialDataset }: { onCreated: (id: string) => void; initialDataset: string }) {
  const { workspaceId, role } = useWorkspaceCtx()
  const datasets = useDatasets(workspaceId)
  const agents = useAgents(workspaceId)
  const m = useEvalMutations(workspaceId)
  const [datasetId, setDatasetId] = useState(initialDataset)
  const [agentId, setAgentId] = useState("")
  const [source, setSource] = useState<"published" | "draft">("published")
  const [scorer, setScorer] = useState<ScorerType>("contains")
  const [caseSensitive, setCaseSensitive] = useState(false)
  const [name, setName] = useState("")
  const agent = agents.data?.items.find((a) => a.id === agentId)
  const ds = datasets.data?.find((d) => d.id === datasetId)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    try {
      const ev = await m.createRun.mutateAsync({ dataset_id: datasetId, agent_id: agentId, source, scorer: { type: scorer, case_sensitive: caseSensitive }, name })
      toast.success(`Queued ${ev.summary.total} case runs`)
      setName("")
      onCreated(ev.id)
    } catch (x) {
      toast.error(errorMessage(x))
    }
  }

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>New evaluation</CardTitle>
        <CardDescription>Queues one run per case. Use the draft to test unpublished changes, then compare against the published version.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="ev-ds">Dataset</Label>
            <select id="ev-ds" className={selectCls} value={datasetId} onChange={(e) => setDatasetId(e.target.value)} required>
              <option value="">Select a dataset…</option>
              {datasets.data?.map((d) => <option key={d.id} value={d.id}>{d.name} ({d.case_count} cases)</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ev-agent">Agent</Label>
            <select id="ev-agent" className={selectCls} value={agentId} onChange={(e) => { setAgentId(e.target.value); const a = agents.data?.items.find((x) => x.id === e.target.value); setSource(a?.published_version ? "published" : "draft") }} required>
              <option value="">Select an agent…</option>
              {agents.data?.items.filter((a) => a.status !== "retired").map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ev-src">Configuration</Label>
            <select id="ev-src" className={selectCls} value={source} onChange={(e) => setSource(e.target.value as "published" | "draft")}>
              <option value="published" disabled={!agent?.published_version || agent.status !== "published"}>Published{agent?.published_version ? ` v${agent.published_version}` : ""}</option>
              {can(role, "agents:write") && <option value="draft">Draft</option>}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ev-scorer">Scorer</Label>
            <select id="ev-scorer" className={selectCls} value={scorer} onChange={(e) => setScorer(e.target.value as ScorerType)}>
              {SCORERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ev-name">Name</Label>
            <Input id="ev-name" value={name} onChange={(e) => setName(e.target.value)} placeholder={agent && ds ? `${agent.name} on ${ds.name}` : "optional"} />
          </div>
          <label className="flex items-center gap-2 self-end pb-2 text-sm"><input type="checkbox" className="size-4" checked={caseSensitive} onChange={(e) => setCaseSensitive(e.target.checked)} /> Case sensitive</label>
          <div className="sm:col-span-2 lg:col-span-3">
            <Button type="submit" disabled={!datasetId || !agentId || m.createRun.isPending}>{m.createRun.isPending ? "Queuing…" : `Run evaluation${ds ? ` (${ds.case_count} cases)` : ""}`}</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

function EvalRunsInner() {
  const params = useSearchParams()
  const { workspaceId, role } = useWorkspaceCtx()
  const runs = useEvalRuns(workspaceId)
  const m = useEvalMutations(workspaceId)
  const [open, setOpen] = useState<string | null>(params.get("id"))
  return (
    <div>
      <PageHeader title="Evaluation runs" description="Scores update live while the worker processes the cases." />
      <EvalNav />
      {can(role, "runs:create") && <NewEvaluation initialDataset={params.get("dataset") ?? ""} onCreated={setOpen} />}
      {runs.isPending ? <LoadingRows /> : runs.isError ? <ErrorState error={runs.error} onRetry={() => runs.refetch()} /> : runs.data.length === 0 ? (
        <EmptyState title="No evaluation runs yet" description="Pick a dataset and an agent above." />
      ) : (
        <div className="rounded-xl border">
          <Table>
            <TableHeader><TableRow><TableHead className="w-8" /><TableHead>Evaluation</TableHead><TableHead>Agent</TableHead><TableHead>Scorer</TableHead><TableHead>Status</TableHead><TableHead>Pass rate</TableHead><TableHead className="text-right">Avg latency</TableHead><TableHead className="text-right">Cost</TableHead><TableHead>Created</TableHead></TableRow></TableHeader>
            <TableBody>
              {runs.data.map((r) => (
                <Fragment key={r.id}>
                  <TableRow className="cursor-pointer" onClick={() => setOpen(open === r.id ? null : r.id)}>
                    <TableCell>
                      <button type="button" aria-expanded={open === r.id} aria-label={`Show results of ${r.name}`} onClick={(e) => { e.stopPropagation(); setOpen(open === r.id ? null : r.id) }}>
                        {open === r.id ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                      </button>
                    </TableCell>
                    <TableCell><span className="font-medium">{r.name}</span><span className="block text-xs text-muted-foreground">{r.dataset_name}</span></TableCell>
                    <TableCell className="text-sm"><Link href={`/agents/${r.agent_id}`} onClick={(e) => e.stopPropagation()} className="underline-offset-4 hover:underline">{r.agent_name}</Link> <span className="text-muted-foreground">{r.source === "draft" ? "draft" : `v${r.agent_version}`}</span></TableCell>
                    <TableCell className="text-sm">{r.scorer.type}</TableCell>
                    <TableCell><StatusBadge status={r.status} /> {r.status === "running" && <span className="text-xs text-muted-foreground">{r.summary.finished}/{r.summary.total}</span>}</TableCell>
                    <TableCell><PassRate rate={r.summary.pass_rate} passed={r.summary.passed} total={r.summary.total} /></TableCell>
                    <TableCell className="text-right text-sm tabular-nums">{fmtMs(r.summary.avg_latency_ms)}</TableCell>
                    <TableCell className="text-right text-sm tabular-nums">{fmtUsd(r.summary.cost_usd)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{fmtRelative(r.created_at)}</TableCell>
                  </TableRow>
                  {open === r.id && (
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={9} className="bg-muted/30 p-3">
                        <ResultsTable results={r.results} />
                        <div className="mt-2 flex gap-2">
                          <Link href={`/evaluations/compare?a=${r.id}`} className="text-sm underline-offset-4 hover:underline">Compare with another run</Link>
                          {can(role, "agents:write") && (
                            <Button size="sm" variant="ghost" className="ml-auto text-destructive" onClick={async () => {
                              try {
                                await m.removeRun.mutateAsync(r.id)
                                toast.success("Evaluation deleted (case runs are kept in Runs)")
                              } catch (x) {
                                toast.error(errorMessage(x))
                              }
                            }}>Delete evaluation</Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

export default function EvalRunsPage() {
  return <Suspense fallback={<LoadingRows />}><EvalRunsInner /></Suspense>
}
