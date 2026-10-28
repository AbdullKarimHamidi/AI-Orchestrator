"use client"

import { useRouter } from "next/navigation"
import { toast } from "sonner"

import { ErrorState, LoadingRows } from "@/components/common/states"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { useWorkflowPage } from "@/components/workflows/use-workflow-page"
import { WorkflowEditor } from "@/components/workflows/workflow-editor"
import { WorkflowHeader } from "@/components/workflows/workflow-header"
import { useWorkflowMutations } from "@/hooks/use-modules"
import { ApiError } from "@/lib/api-client"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

export default function EditWorkflowPage() {
  const { workflowId, workspaceId, workflow } = useWorkflowPage()
  const { role } = useWorkspaceCtx()
  const { update } = useWorkflowMutations(workspaceId)
  const router = useRouter()
  if (workflow.isPending) return <LoadingRows />
  if (workflow.isError) return <ErrorState error={workflow.error} />
  const w = workflow.data
  return (
    <div>
      <WorkflowHeader workflow={w} />
      {!can(role, "agents:write") ? (
        <ErrorState error={new Error("Your role can view but not edit workflows.")} />
      ) : w.status === "archived" ? (
        <Alert><AlertDescription>Archived workflows cannot be edited. Restore it first.</AlertDescription></Alert>
      ) : (
        <>
          <Alert className="mb-4"><AlertDescription>You are editing the draft. Published versions are immutable; publish again to ship these changes.</AlertDescription></Alert>
          <WorkflowEditor key={w.revision} initial={{ name: w.name, description: w.description, definition: w.draft }} submitLabel="Save draft"
            onSubmit={async (d) => {
              try {
                await update.mutateAsync({ id: workflowId, revision: w.revision, ...d })
                toast.success("Draft saved")
                router.push(`/workflows/${workflowId}`)
              } catch (e) {
                if (e instanceof ApiError && e.code === "REVISION_MISMATCH") throw new Error("Someone else saved this workflow. Reload the page to get their changes.")
                throw e
              }
            }} />
        </>
      )}
    </div>
  )
}
