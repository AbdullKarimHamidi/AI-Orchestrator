"use client"

import { useRouter } from "next/navigation"
import { toast } from "sonner"

import { ErrorState, PageHeader } from "@/components/common/states"
import { ToolForm } from "@/components/tools/tool-form"
import { useToolMutations } from "@/hooks/use-api"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

export default function NewToolPage() {
  const { workspaceId, role } = useWorkspaceCtx()
  const { create } = useToolMutations(workspaceId)
  const router = useRouter()
  if (!can(role, "agents:write")) return <ErrorState error={new Error("Your role cannot create tools.")} />
  return (
    <div className="max-w-3xl">
      <PageHeader title="New HTTP tool" description="Let agents call one of your HTTP APIs." />
      <ToolForm submitLabel="Create tool" onSubmit={async (body) => {
        const t = await create.mutateAsync(body)
        toast.success("Tool created. Test it, then enable it on an agent.")
        router.push(`/tools/${t.id}`)
      }} />
    </div>
  )
}
