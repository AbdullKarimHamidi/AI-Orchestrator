"use client"

import { ErrorState, LoadingRows } from "@/components/common/states"
import { RunsTable } from "@/components/runs/runs-table"
import { useWorkflowPage } from "@/components/workflows/use-workflow-page"
import { WorkflowHeader } from "@/components/workflows/workflow-header"
import { useWorkflowRuns } from "@/hooks/use-modules"

export default function WorkflowRunsPage() {
  const { workflowId, workspaceId, workflow } = useWorkflowPage()
  const runs = useWorkflowRuns(workspaceId, workflowId, 200)
  if (workflow.isPending) return <LoadingRows />
  if (workflow.isError) return <ErrorState error={workflow.error} />
  return (
    <div>
      <WorkflowHeader workflow={workflow.data} />
      {runs.isPending ? <LoadingRows /> : runs.isError ? <ErrorState error={runs.error} onRetry={() => runs.refetch()} /> : (
        <>
          <p className="mb-3 text-sm text-muted-foreground">{runs.data.total} runs. Open one to see each step, its output and the model calls it made.</p>
          <RunsTable runs={runs.data.items} hideAgent emptyText="This workflow has not run yet." />
        </>
      )}
    </div>
  )
}
