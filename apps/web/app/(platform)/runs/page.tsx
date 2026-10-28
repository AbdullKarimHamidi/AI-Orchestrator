"use client"

import { useState } from "react"

import { RunsTable } from "@/components/runs/runs-table"
import { ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { useRuns } from "@/hooks/use-api"
import { runStatusSchema } from "@/lib/schemas"
import { useWorkspaceCtx } from "@/lib/workspace-context"

export default function RunsPage() {
  const { workspaceId } = useWorkspaceCtx()
  const [status, setStatus] = useState("")
  const runs = useRuns(workspaceId, { status: status || undefined, limit: 100 })
  return (
    <div>
      <PageHeader title="Runs" description="Every execution, its status, cost, and full event log. Active runs refresh automatically." />
      <div className="mb-4">
        <label htmlFor="run-status" className="sr-only">Filter by status</label>
        <select id="run-status" value={status} onChange={(e) => setStatus(e.target.value)} className="h-9 rounded-md border bg-background px-2 text-sm">
          <option value="">All statuses</option>
          {runStatusSchema.options.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
        </select>
        {runs.data && <span className="ml-3 text-sm text-muted-foreground">{runs.data.total} total</span>}
      </div>
      {runs.isPending ? <LoadingRows /> : runs.isError ? <ErrorState error={runs.error} onRetry={() => runs.refetch()} /> : <RunsTable runs={runs.data.items} emptyText={status ? "No runs with this status" : "No runs yet. Publish an agent and run it from its test console."} />}
    </div>
  )
}
