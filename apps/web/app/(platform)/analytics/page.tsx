"use client"

import { useState } from "react"

import { UsageTable } from "@/components/analytics/usage-table"
import { ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { useProviders, useProviderUsage } from "@/hooks/use-api"
import { fmtInt, fmtUsd } from "@/lib/format"
import { useWorkspaceCtx } from "@/lib/workspace-context"

export default function AnalyticsPage() {
  const { workspaceId } = useWorkspaceCtx()
  const [days, setDays] = useState(30)
  const usage = useProviderUsage(workspaceId, days)
  const providers = useProviders(workspaceId)
  const totals = usage.data?.reduce((a, r) => ({ calls: a.calls + r.calls, cost: a.cost + r.cost_usd, errors: a.errors + r.errors }), { calls: 0, cost: 0, errors: 0 })
  return (
    <div>
      <PageHeader
        title="Analytics"
        description="Usage and cost by provider and model, aggregated from usage records. Time-series charts and per-agent breakdowns are in development."
        actions={<>
          <label htmlFor="a-days" className="sr-only">Time window</label>
          <select id="a-days" value={days} onChange={(e) => setDays(Number(e.target.value))} className="h-9 rounded-md border bg-background px-2 text-sm">
            {[1, 7, 30, 90].map((n) => <option key={n} value={n}>Last {n} days</option>)}
          </select>
        </>}
      />
      {usage.isPending ? <LoadingRows /> : usage.isError ? <ErrorState error={usage.error} onRetry={() => usage.refetch()} /> : (
        <>
          {totals && <p className="mb-3 text-sm">{fmtInt(totals.calls)} provider calls · {fmtInt(totals.errors)} errors · {fmtUsd(totals.cost)}</p>}
          <UsageTable rows={usage.data} providers={providers.data ?? []} />
        </>
      )}
    </div>
  )
}
