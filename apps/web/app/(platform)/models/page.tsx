"use client"

import { Plus } from "lucide-react"
import { useState } from "react"

import { UsageTable } from "@/components/analytics/usage-table"
import { FreeProviders } from "@/components/models/free-providers"
import { AddProviderDialog } from "@/components/models/provider-dialog"
import { ProviderCard } from "@/components/models/provider-card"
import { ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { Button } from "@/components/ui/button"
import { usePresets, useProviders, useProviderUsage } from "@/hooks/use-api"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

export default function ModelsPage() {
  const { workspaceId, role } = useWorkspaceCtx()
  const providers = useProviders(workspaceId)
  const usage = useProviderUsage(workspaceId, 30)
  const presets = usePresets(workspaceId)
  const [open, setOpen] = useState(false)
  const canWrite = can(role, "providers:write")
  return (
    <div>
      <PageHeader
        title="Model gateway"
        description="Provider connections, model allowlists, health, and usage. Adapters call each provider's native API with no hidden retries."
        actions={canWrite && <Button onClick={() => setOpen(true)}><Plus className="size-4" /> Add provider</Button>}
      />
      {providers.isPending ? <LoadingRows /> : providers.isError ? <ErrorState error={providers.error} onRetry={() => providers.refetch()} /> : (
        <div className="grid gap-4 md:grid-cols-2">
          {providers.data.map((p) => <ProviderCard key={p.id} p={p} workspaceId={workspaceId} canWrite={canWrite} />)}
        </div>
      )}
      <h2 className="mt-8 mb-2 text-lg font-semibold">Free AI providers</h2>
      <p className="mb-3 text-sm text-muted-foreground">Real models at no cost. Each free tier needs its own key (free sign-up, no card); Ollama runs models on your own computer and needs no key. Agents can list several providers as fallbacks, so when one free tier hits its limit the next one answers.</p>
      {presets.isPending ? <LoadingRows rows={2} /> : presets.isError ? <ErrorState error={presets.error} onRetry={() => presets.refetch()} /> : <FreeProviders presets={presets.data} workspaceId={workspaceId} canWrite={canWrite} />}
      <h2 className="mt-8 mb-2 text-lg font-semibold">Usage (last 30 days)</h2>
      <p className="mb-3 text-sm text-muted-foreground">One row per provider and model. Every attempt, including failed attempts and fallbacks, is a usage record. Cost uses per-provider prices; models without a configured price count as $0 and are flagged.</p>
      {usage.isPending ? <LoadingRows rows={2} /> : usage.isError ? <ErrorState error={usage.error} /> : <UsageTable rows={usage.data} providers={providers.data ?? []} />}
      {canWrite && <AddProviderDialog workspaceId={workspaceId} open={open} onOpenChange={setOpen} />}
    </div>
  )
}
