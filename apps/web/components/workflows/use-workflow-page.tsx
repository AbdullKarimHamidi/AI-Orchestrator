"use client"

import { useParams } from "next/navigation"

import { useWorkflow } from "@/hooks/use-modules"
import { useWorkspaceCtx } from "@/lib/workspace-context"

export function useWorkflowPage() {
  const { workflowId } = useParams<{ workflowId: string }>()
  const { workspaceId } = useWorkspaceCtx()
  return { workflowId, workspaceId, workflow: useWorkflow(workspaceId, workflowId) }
}
