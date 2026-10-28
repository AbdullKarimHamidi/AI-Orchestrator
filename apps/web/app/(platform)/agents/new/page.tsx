"use client"

import { useRouter } from "next/navigation"
import { toast } from "sonner"

import { AgentForm, toFormValues } from "@/components/agents/agent-form"
import { ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { useAgentMutations, useKnowledgeBases, useProviders, useTools } from "@/hooks/use-api"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

export default function NewAgentPage() {
  const { workspaceId, role } = useWorkspaceCtx()
  const router = useRouter()
  const providers = useProviders(workspaceId)
  const tools = useTools(workspaceId)
  const kbs = useKnowledgeBases(workspaceId)
  const { create } = useAgentMutations(workspaceId)

  if (!can(role, "agents:write")) return <ErrorState error={new Error("Your role cannot create agents.")} />
  if (providers.isPending) return <LoadingRows />
  if (providers.isError) return <ErrorState error={providers.error} />
  const initial = toFormValues("", "")
  const demo = providers.data.find((p) => p.kind === "demo")
  if (demo && !initial.provider_id) {
    initial.provider_id = demo.id
    initial.model = "demo-echo"
  }
  return (
    <div className="max-w-3xl">
      <PageHeader title="New agent" description="Agents start as a draft. Publish to create an immutable version that production runs use." />
      <AgentForm
        initial={initial}
        providers={providers.data}
        tools={tools.data}
        knowledgeBases={kbs.data}
        submitLabel="Create agent"
        cancelHref="/agents"
        onSubmit={async (input) => {
          const a = await create.mutateAsync(input)
          toast.success("Agent created as draft")
          router.push(`/agents/${a.id}`)
        }}
      />
    </div>
  )
}
