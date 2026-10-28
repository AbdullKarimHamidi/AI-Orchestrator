"use client"

import Link from "next/link"
import { useState } from "react"

import { RunsTable } from "@/components/runs/runs-table"
import { ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useDashboard } from "@/hooks/use-api"
import { fmtInt, fmtMs, fmtUsd } from "@/lib/format"
import { useWorkspaceCtx } from "@/lib/workspace-context"

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card size="sm">
      <CardHeader><CardTitle className="text-sm font-normal text-muted-foreground">{label}</CardTitle></CardHeader>
      <CardContent>
        <p className="text-2xl font-semibold tabular-nums">{value}</p>
        {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  )
}

export default function DashboardPage() {
  const { workspaceId, workspaceName } = useWorkspaceCtx()
  const [days, setDays] = useState(7)
  const d = useDashboard(workspaceId, days)
  return (
    <div>
      <PageHeader
        title="Dashboard"
        description={`Live figures for ${workspaceName}, computed from runs and usage records in MongoDB.`}
        actions={
          <>
            <label htmlFor="window" className="sr-only">Time window</label>
            <select id="window" value={days} onChange={(e) => setDays(Number(e.target.value))} className="h-9 rounded-md border bg-background px-2 text-sm">
              {[1, 7, 30, 90].map((n) => <option key={n} value={n}>Last {n} day{n > 1 ? "s" : ""}</option>)}
            </select>
          </>
        }
      />
      {d.isPending ? (
        <LoadingRows rows={6} />
      ) : d.isError ? (
        <ErrorState error={d.error} onRetry={() => d.refetch()} />
      ) : (
        <>
          {d.data.demo_runs > 0 && (
            <p className="mb-4 rounded-md border border-amber-400 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
              {d.data.demo_runs} of {d.data.runs_total} runs in this window used the Demo provider (synthetic output, $0). They are included in the counts below.
            </p>
          )}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Metric label="Runs" value={fmtInt(d.data.runs_total)} hint={Object.entries(d.data.runs_by_status).map(([k, v]) => `${v} ${k.replaceAll("_", " ")}`).join(" · ") || "No runs yet"} />
            <Metric label="Success rate" value={d.data.success_rate === null ? "—" : `${(d.data.success_rate * 100).toFixed(1)}%`} hint="completed / finished" />
            <Metric label="Latency p50 / p95" value={`${fmtMs(d.data.p50_latency_ms)}`} hint={`p95 ${fmtMs(d.data.p95_latency_ms)}`} />
            <Metric label="Cost" value={fmtUsd(d.data.cost_usd)} hint={`${fmtInt(d.data.input_tokens)} in / ${fmtInt(d.data.output_tokens)} out tokens`} />
            <Metric label="Agents" value={fmtInt(d.data.agents_total)} hint={`${d.data.agents_published} published`} />
            <Metric label="Providers" value={fmtInt(d.data.providers_total)} hint={d.data.providers_unhealthy ? `${d.data.providers_unhealthy} unhealthy` : "none reported unhealthy"} />
            <Metric label="Month-to-date spend" value={fmtUsd(d.data.month_to_date_cost_usd)} hint={d.data.monthly_budget_usd !== null ? `of ${fmtUsd(d.data.monthly_budget_usd)} budget` : "No budget set"} />
            <Metric label="Window" value={`${d.data.window_days}d`} hint="Change with the selector above" />
          </div>
          <div className="mt-8">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Recent runs</h2>
              <Link href="/runs" className="text-sm underline underline-offset-4">View all</Link>
            </div>
            <RunsTable runs={d.data.recent_runs} emptyText="No runs yet. Create and publish an agent to get started." />
          </div>
        </>
      )}
    </div>
  )
}
