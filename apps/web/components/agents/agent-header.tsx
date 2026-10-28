"use client"

import { DemoBadge, StatusBadge } from "@/components/common/status-badge"
import { PageHeader } from "@/components/common/states"
import type { Agent } from "@/lib/schemas"

import { AgentActions } from "./agent-actions"
import { AgentTabs } from "./agent-tabs"

export function AgentHeader({ agent, actions = true }: { agent: Agent; actions?: boolean }) {
  return (
    <>
      <PageHeader title={agent.name} description={agent.description || undefined} actions={actions && <AgentActions agent={agent} />} />
      <div className="-mt-3 mb-4 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        <StatusBadge status={agent.status} />
        <span>{agent.published_version ? `Serving v${agent.published_version}` : "Not published"}</span>
        {agent.draft_dirty && agent.published_version !== null && <span className="text-amber-700 dark:text-amber-400">· Draft has unpublished changes</span>}
        {agent.draft.model?.model.startsWith("demo-") && <DemoBadge />}
      </div>
      <AgentTabs id={agent.id} />
    </>
  )
}
