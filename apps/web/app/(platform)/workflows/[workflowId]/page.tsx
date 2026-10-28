"use client"

import Link from "next/link"

import { ErrorState, LoadingRows } from "@/components/common/states"
import { RunsTable } from "@/components/runs/runs-table"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { WorkflowRunPanel } from "@/components/workflows/run-panel"
import { useWorkflowPage } from "@/components/workflows/use-workflow-page"
import { WorkflowDiagram } from "@/components/workflows/workflow-diagram"
import { WorkflowHeader } from "@/components/workflows/workflow-header"
import { useAgents, useKnowledgeBases, useTools } from "@/hooks/use-api"
import { useWorkflowRuns, useWorkflowValidation, useWorkflowVersions } from "@/hooks/use-modules"
import { fmtDate } from "@/lib/format"

export default function WorkflowPage() {
  const { workflowId, workspaceId, workflow } = useWorkflowPage()
  const versions = useWorkflowVersions(workspaceId, workflowId)
  const runs = useWorkflowRuns(workspaceId, workflowId, 5)
  const validation = useWorkflowValidation(workspaceId, workflowId, workflow.data?.revision)
  const agents = useAgents(workspaceId)
  const tools = useTools(workspaceId)
  const kbs = useKnowledgeBases(workspaceId)
  if (workflow.isPending) return <LoadingRows />
  if (workflow.isError) return <ErrorState error={workflow.error} onRetry={() => workflow.refetch()} />
  const w = workflow.data
  const names = Object.fromEntries([
    ...(agents.data?.items ?? []).map((a) => [a.id, a.name]),
    ...(tools.data ?? []).map((t) => [t.id, t.name]),
    ...(kbs.data ?? []).map((k) => [k.id, k.name]),
  ])
  return (
    <div>
      <WorkflowHeader workflow={w} />
      {validation.data && !validation.data.valid && (
        <Alert className="mb-4">
          <AlertTitle>The draft cannot run or be published yet</AlertTitle>
          <AlertDescription><ul className="list-disc pl-4">{validation.data.problems.map((p) => <li key={p}>{p}</li>)}</ul></AlertDescription>
        </Alert>
      )}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-4">
          <WorkflowRunPanel workflow={w} />
          <Card>
            <CardHeader><CardTitle className="flex items-center justify-between">Recent runs <Link href={`/workflows/${w.id}/runs`} className="text-sm font-normal underline-offset-4 hover:underline">All runs</Link></CardTitle></CardHeader>
            <CardContent>{runs.data ? <RunsTable runs={runs.data.items} hideAgent emptyText="This workflow has not run yet." /> : <LoadingRows rows={2} />}</CardContent>
          </Card>
        </div>
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Draft flow</CardTitle></CardHeader>
            <CardContent><WorkflowDiagram definition={w.draft} names={names} /></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Versions</CardTitle></CardHeader>
            <CardContent>
              {versions.data?.length ? (
                <ol className="space-y-2 text-sm">
                  {versions.data.map((v) => (
                    <li key={v.id} className="flex items-baseline justify-between gap-2">
                      <span><span className="font-medium">v{v.version}</span>{v.version === w.published_version && <span className="ml-1 text-xs text-emerald-600">published</span>} <span className="text-muted-foreground">{v.note || `${v.definition.steps.length} steps`}</span></span>
                      <time className="shrink-0 text-xs text-muted-foreground">{fmtDate(v.created_at)}</time>
                    </li>
                  ))}
                </ol>
              ) : <p className="text-sm text-muted-foreground">No versions yet. Publish to create v1.</p>}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
