"use client"

import Link from "next/link"
import { useParams } from "next/navigation"

import { RunInspector } from "@/components/runs/run-inspector"
import { ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useRun } from "@/hooks/use-api"
import { useWorkspaceCtx } from "@/lib/workspace-context"

export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>()
  const { workspaceId } = useWorkspaceCtx()
  const run = useRun(workspaceId, runId)
  if (run.isPending) return <LoadingRows />
  if (run.isError) return <ErrorState error={run.error} onRetry={() => run.refetch()} />
  const r = run.data
  return (
    <div>
      <PageHeader title={`Run ${r.id.slice(0, 16)}…`} description={`${r.agent_name} · ${r.source === "draft" ? "draft snapshot" : `version ${r.agent_version}`}`} actions={r.kind === "workflow"
        ? <Link className="text-sm underline underline-offset-4" href={`/workflows/${r.workflow_id}`}>Open workflow</Link>
        : <Link className="text-sm underline underline-offset-4" href={`/agents/${r.agent_id}`}>Open agent</Link>} />
      <RunInspector run={r} />
      <Card className="mt-4">
        <CardHeader><CardTitle>{r.kind === "workflow" ? "Executed workflow definition (snapshot)" : "Executed configuration (snapshot)"}</CardTitle></CardHeader>
        <CardContent><pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs">{JSON.stringify(r.config, null, 2)}</pre></CardContent>
      </Card>
    </div>
  )
}
