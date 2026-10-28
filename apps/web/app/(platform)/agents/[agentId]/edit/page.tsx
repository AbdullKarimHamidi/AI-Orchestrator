"use client"

import { useRouter } from "next/navigation"
import { toast } from "sonner"

import { AgentForm, toFormValues } from "@/components/agents/agent-form"
import { AgentHeader } from "@/components/agents/agent-header"
import { useAgentPage } from "@/components/agents/use-agent-page"
import { ErrorState, LoadingRows } from "@/components/common/states"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { useAgentMutations, useKnowledgeBases, useProviders, useTools } from "@/hooks/use-api"
import { ApiError } from "@/lib/api-client"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

export default function EditAgentPage() {
  const { agentId, workspaceId, agent } = useAgentPage()
  const { role } = useWorkspaceCtx()
  const providers = useProviders(workspaceId)
  const tools = useTools(workspaceId)
  const kbs = useKnowledgeBases(workspaceId)
  const { update } = useAgentMutations(workspaceId)
  const router = useRouter()
  if (agent.isPending || providers.isPending) return <LoadingRows />
  if (agent.isError) return <ErrorState error={agent.error} />
  if (providers.isError) return <ErrorState error={providers.error} />
  const a = agent.data
  return (
    <div>
      <AgentHeader agent={a} actions={false} />
      {!can(role, "agents:write") ? (
        <ErrorState error={new Error("Your role can view but not edit agents.")} />
      ) : a.status === "retired" ? (
        <Alert><AlertDescription>Retired agents cannot be edited.</AlertDescription></Alert>
      ) : (
        <div className="max-w-3xl">
          <Alert className="mb-4">
            <AlertDescription>You are editing the draft. Published versions are immutable; publish again to ship these changes.</AlertDescription>
          </Alert>
          <AgentForm
            key={a.revision}
            initial={toFormValues(a.name, a.description, a.draft)}
            baseConfig={a.draft}
            providers={providers.data}
            tools={tools.data}
            knowledgeBases={kbs.data}
            submitLabel="Save draft"
            cancelHref={`/agents/${agentId}`}
            onSubmit={async (input) => {
              try {
                await update.mutateAsync({ id: agentId, revision: a.revision, ...input })
                toast.success("Draft saved")
                router.push(`/agents/${agentId}`)
              } catch (e) {
                if (e instanceof ApiError && e.code === "REVISION_MISMATCH") {
                  agent.refetch()
                  throw new Error("Someone else changed this agent. The latest version has been loaded; re-apply your edits.")
                }
                throw e
              }
            }}
          />
        </div>
      )}
    </div>
  )
}
