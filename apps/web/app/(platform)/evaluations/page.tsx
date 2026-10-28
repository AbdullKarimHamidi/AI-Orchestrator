"use client"

import Link from "next/link"

import { ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { StatusBadge } from "@/components/common/status-badge"
import { EvalNav, PassRate } from "@/components/evaluations/eval-nav"
import { buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useDatasets, useEvalRuns } from "@/hooks/use-modules"
import { fmtRelative, fmtUsd } from "@/lib/format"
import { useWorkspaceCtx } from "@/lib/workspace-context"

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardHeader className="pb-1"><CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle></CardHeader>
      <CardContent><p className="text-2xl font-semibold tabular-nums">{value}</p>{hint && <p className="text-xs text-muted-foreground">{hint}</p>}</CardContent>
    </Card>
  )
}

export default function EvaluationsPage() {
  const { workspaceId } = useWorkspaceCtx()
  const datasets = useDatasets(workspaceId)
  const runs = useEvalRuns(workspaceId)
  const done = runs.data?.filter((r) => r.status === "completed") ?? []
  const avg = done.length ? done.reduce((a, r) => a + (r.summary.pass_rate ?? 0), 0) / done.length : null
  return (
    <div>
      <PageHeader title="Evaluations" description="Test agents offline against datasets of cases before you publish. Each case runs through the worker exactly like production traffic and is scored deterministically."
        actions={<Link href="/evaluations/runs" className={buttonVariants()}>Run an evaluation</Link>} />
      <EvalNav />
      {datasets.isError ? <ErrorState error={datasets.error} /> : runs.isError ? <ErrorState error={runs.error} /> : (
        <>
          <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Datasets" value={String(datasets.data?.length ?? "…")} hint={`${datasets.data?.reduce((a, d) => a + d.case_count, 0) ?? 0} cases in total`} />
            <Stat label="Evaluation runs" value={String(runs.data?.length ?? "…")} hint={`${runs.data?.filter((r) => r.status === "running").length ?? 0} running`} />
            <Stat label="Average pass rate" value={avg === null ? "—" : `${Math.round(avg * 100)}%`} hint="over completed evaluations" />
            <Stat label="Evaluation spend" value={fmtUsd(runs.data?.reduce((a, r) => a + r.summary.cost_usd, 0) ?? 0)} hint="model cost of all cases" />
          </div>
          <h2 className="mb-2 font-medium">Recent evaluations</h2>
          {runs.isPending ? <LoadingRows /> : runs.data.length === 0 ? (
            <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
              No evaluations yet. <Link href="/evaluations/datasets" className="underline">Create a dataset</Link>, then <Link href="/evaluations/runs" className="underline">run it against an agent</Link>.
            </div>
          ) : (
            <div className="rounded-xl border">
              <Table>
                <TableHeader><TableRow><TableHead>Evaluation</TableHead><TableHead>Agent</TableHead><TableHead>Dataset</TableHead><TableHead>Status</TableHead><TableHead>Pass rate</TableHead><TableHead>Created</TableHead></TableRow></TableHeader>
                <TableBody>
                  {runs.data.slice(0, 10).map((r) => (
                    <TableRow key={r.id}>
                      <TableCell><Link href={`/evaluations/runs?id=${r.id}`} className="font-medium underline-offset-4 hover:underline">{r.name}</Link></TableCell>
                      <TableCell className="text-sm">{r.agent_name} <span className="text-muted-foreground">{r.source === "draft" ? "draft" : `v${r.agent_version}`}</span></TableCell>
                      <TableCell className="text-sm">{r.dataset_name}</TableCell>
                      <TableCell><StatusBadge status={r.status} /></TableCell>
                      <TableCell><PassRate rate={r.summary.pass_rate} passed={r.summary.passed} total={r.summary.total} /></TableCell>
                      <TableCell className="text-sm text-muted-foreground">{fmtRelative(r.created_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
