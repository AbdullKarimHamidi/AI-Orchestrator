"use client"

import { useRouter, useSearchParams } from "next/navigation"
import { Suspense } from "react"

import { ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { EvalNav, PassRate } from "@/components/evaluations/eval-nav"
import { Verdict } from "@/components/evaluations/results-table"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useEvalCompare, useEvalRuns } from "@/hooks/use-modules"
import { fmtDate } from "@/lib/format"
import type { EvalRun } from "@/lib/schemas"
import { useWorkspaceCtx } from "@/lib/workspace-context"

const CHANGE: Record<string, { label: string; cls: string }> = {
  fixed: { label: "fixed", cls: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200" },
  regressed: { label: "regressed", cls: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200" },
  same_pass: { label: "still passing", cls: "text-muted-foreground" },
  same_fail: { label: "still failing", cls: "text-muted-foreground" },
  missing: { label: "only in one run", cls: "text-muted-foreground" },
}

function Side({ title, run }: { title: string; run: EvalRun }) {
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">{title}: {run.name}</CardTitle></CardHeader>
      <CardContent className="space-y-1 text-sm">
        <p>{run.agent_name} · {run.source === "draft" ? "draft" : `v${run.agent_version}`} · scorer {run.scorer.type}</p>
        <PassRate rate={run.summary.pass_rate} passed={run.summary.passed} total={run.summary.total} />
        <p className="text-xs text-muted-foreground">{fmtDate(run.created_at)}</p>
      </CardContent>
    </Card>
  )
}

function CompareInner() {
  const params = useSearchParams()
  const router = useRouter()
  const { workspaceId } = useWorkspaceCtx()
  const runs = useEvalRuns(workspaceId)
  const a = params.get("a") ?? ""
  const b = params.get("b") ?? ""
  const cmp = useEvalCompare(workspaceId, a || undefined, b || undefined)
  const runA = runs.data?.find((r) => r.id === a)
  const options = (exclude: string, sameDataset?: string) => (runs.data ?? []).filter((r) => r.id !== exclude && (!sameDataset || r.dataset_id === sameDataset))
  const set = (k: "a" | "b", v: string) => {
    const q = new URLSearchParams(params.toString())
    if (v) q.set(k, v)
    else q.delete(k)
    router.replace(`/evaluations/compare?${q}`)
  }
  return (
    <div>
      <PageHeader title="Compare evaluations" description="Two evaluation runs of the same dataset, case by case: which cases a change fixed and which it broke." />
      <EvalNav />
      <div className="mb-5 grid gap-3 sm:grid-cols-2">
        {(["a", "b"] as const).map((k) => (
          <div key={k} className="space-y-1.5">
            <Label htmlFor={`cmp-${k}`}>{k === "a" ? "Baseline (A)" : "Candidate (B)"}</Label>
            <select id={`cmp-${k}`} className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={k === "a" ? a : b} onChange={(e) => set(k, e.target.value)}>
              <option value="">Select an evaluation run…</option>
              {options(k === "a" ? b : a, k === "b" ? runA?.dataset_id : undefined).map((r) => (
                <option key={r.id} value={r.id}>{r.name} · {r.source === "draft" ? "draft" : `v${r.agent_version}`} · {r.summary.pass_rate === null ? "—" : `${Math.round(r.summary.pass_rate * 100)}%`}</option>
              ))}
            </select>
          </div>
        ))}
      </div>
      {!a || !b ? (
        <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">Choose two evaluation runs of the same dataset.</p>
      ) : cmp.isPending ? <LoadingRows /> : cmp.isError ? <ErrorState error={cmp.error} /> : (
        <>
          <div className="mb-4 grid gap-3 sm:grid-cols-2">
            <Side title="A" run={cmp.data.a} />
            <Side title="B" run={cmp.data.b} />
          </div>
          <p className="mb-2 text-sm"><span className="font-medium text-emerald-600">{cmp.data.fixed} fixed</span> · <span className="font-medium text-red-600">{cmp.data.regressed} regressed</span> · {cmp.data.rows.length} cases</p>
          <div className="overflow-x-auto rounded-xl border">
            <Table>
              <TableHeader><TableRow><TableHead>Case</TableHead><TableHead>Input</TableHead><TableHead>A</TableHead><TableHead>B</TableHead><TableHead>Change</TableHead></TableRow></TableHeader>
              <TableBody>
                {cmp.data.rows.map((r) => (
                  <TableRow key={r.case_id}>
                    <TableCell className="font-mono text-xs">{r.case_id}</TableCell>
                    <TableCell className="max-w-56 text-sm"><p className="line-clamp-2">{r.input}</p><p className="text-xs text-muted-foreground">expected: {r.expected || "—"}</p></TableCell>
                    <TableCell className="max-w-64"><Verdict r={r.a} /><p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{r.a?.output}</p></TableCell>
                    <TableCell className="max-w-64"><Verdict r={r.b} /><p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{r.b?.output}</p></TableCell>
                    <TableCell><span className={`rounded-md px-2 py-0.5 text-xs font-medium ${CHANGE[r.change].cls}`}>{CHANGE[r.change].label}</span></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </>
      )}
    </div>
  )
}

export default function ComparePage() {
  return <Suspense fallback={<LoadingRows />}><CompareInner /></Suspense>
}
