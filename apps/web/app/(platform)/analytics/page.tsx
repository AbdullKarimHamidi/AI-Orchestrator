"use client"

import Link from "next/link"
import { useState } from "react"

import { DailyChart } from "@/components/analytics/daily-chart"
import { UsageTable } from "@/components/analytics/usage-table"
import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useProviders, useProviderUsage } from "@/hooks/use-api"
import { useBreakdown, useTimeseries } from "@/hooks/use-modules"
import { fmtInt, fmtMs, fmtUsd } from "@/lib/format"
import { useWorkspaceCtx } from "@/lib/workspace-context"

export default function AnalyticsPage() {
  const { workspaceId } = useWorkspaceCtx()
  const [days, setDays] = useState(30)
  const usage = useProviderUsage(workspaceId, days)
  const providers = useProviders(workspaceId)
  const series = useTimeseries(workspaceId, days)
  const breakdown = useBreakdown(workspaceId, days)
  const totals = usage.data?.reduce((a, r) => ({ calls: a.calls + r.calls, cost: a.cost + r.cost_usd, errors: a.errors + r.errors }), { calls: 0, cost: 0, errors: 0 })
  const runs = series.data?.reduce((a, r) => a + r.runs, 0) ?? 0
  return (
    <div>
      <PageHeader
        title="Analytics"
        description="Run volume and outcomes per day, a breakdown per agent and workflow, and usage and cost per provider and model."
        actions={<>
          <label htmlFor="a-days" className="sr-only">Time window</label>
          <select id="a-days" value={days} onChange={(e) => setDays(Number(e.target.value))} className="h-9 rounded-md border bg-background px-2 text-sm">
            {[7, 14, 30, 90].map((n) => <option key={n} value={n}>Last {n} days</option>)}
          </select>
        </>}
      />
      <Card className="mb-6">
        <CardHeader><CardTitle className="flex flex-wrap items-baseline justify-between gap-2">Runs per day <span className="text-sm font-normal text-muted-foreground">{fmtInt(runs)} runs · {fmtUsd(series.data?.reduce((a, r) => a + r.cost_usd, 0) ?? 0)}</span></CardTitle></CardHeader>
        <CardContent>{series.isPending ? <LoadingRows rows={3} /> : series.isError ? <ErrorState error={series.error} /> : <DailyChart rows={series.data} />}</CardContent>
      </Card>

      <h2 className="mb-2 font-medium">By agent and workflow</h2>
      {breakdown.isPending ? <LoadingRows /> : breakdown.isError ? <ErrorState error={breakdown.error} /> : breakdown.data.length === 0 ? <EmptyState title="No runs in this window" /> : (
        <div className="mb-8 rounded-xl border">
          <Table>
            <TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Type</TableHead><TableHead className="text-right">Runs</TableHead><TableHead className="text-right">Success</TableHead><TableHead className="text-right">Avg latency</TableHead><TableHead className="text-right">Tokens</TableHead><TableHead className="text-right">Cost</TableHead></TableRow></TableHeader>
            <TableBody>
              {breakdown.data.map((r) => (
                <TableRow key={`${r.kind}:${r.id}`}>
                  <TableCell><Link href={r.kind === "workflow" ? `/workflows/${r.id}` : `/agents/${r.id}`} className="font-medium underline-offset-4 hover:underline">{r.name || r.id}</Link></TableCell>
                  <TableCell className="text-sm">{r.kind}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmtInt(r.runs)}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.success_rate === null ? "—" : `${Math.round(r.success_rate * 100)}%`}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmtMs(r.avg_latency_ms)}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmtInt(r.tokens)}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmtUsd(r.cost_usd)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <h2 className="mb-2 font-medium">By provider and model</h2>
      {usage.isPending ? <LoadingRows /> : usage.isError ? <ErrorState error={usage.error} onRetry={() => usage.refetch()} /> : (
        <>
          {totals && <p className="mb-3 text-sm">{fmtInt(totals.calls)} provider calls · {fmtInt(totals.errors)} errors · {fmtUsd(totals.cost)}</p>}
          <UsageTable rows={usage.data} providers={providers.data ?? []} />
        </>
      )}
    </div>
  )
}
