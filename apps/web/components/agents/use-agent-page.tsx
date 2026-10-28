"use client"

import { useParams } from "next/navigation"

import { useAgent } from "@/hooks/use-api"
import { useWorkspaceCtx } from "@/lib/workspace-context"

export function useAgentPage() {
  const { agentId } = useParams<{ agentId: string }>()
  const { workspaceId } = useWorkspaceCtx()
  return { agentId, workspaceId, agent: useAgent(workspaceId, agentId) }
}
