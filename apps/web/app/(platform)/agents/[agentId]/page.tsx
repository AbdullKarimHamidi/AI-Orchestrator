"use client"

import Link from "next/link"

import { AgentHeader } from "@/components/agents/agent-header"
import { useAgentPage } from "@/components/agents/use-agent-page"
import { RunsTable } from "@/components/runs/runs-table"
import { ErrorState, LoadingRows } from "@/components/common/states"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useProviders, useRuns } from "@/hooks/use-api"
import { fmtDate } from "@/lib/format"

export default function AgentDetailPage() {
  const { agentId, workspaceId, agent } = useAgentPage()
  const providers = useProviders(workspaceId)
  const runs = useRuns(workspaceId, { agent_id: agentId, limit: 10 })
  if (agent.isPending) return <LoadingRows />
  if (agent.isError) return <ErrorState error={agent.error} onRetry={() => agent.refetch()} />
  const a = agent.data
  const pname = (id?: string) => providers.data?.find((p) => p.id === id)?.name ?? id ?? "—"
  const c = a.draft
  return (
    <div>
      <AgentHeader agent={a} />
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Draft configuration</CardTitle></CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted-foreground">Primary</dt>
              <dd className="font-mono text-xs">{c.model ? `${pname(c.model.provider_id)} / ${c.model.model}` : "Not set"}</dd>
              <dt className="text-muted-foreground">Fallbacks</dt>
              <dd className="font-mono text-xs">{c.fallbacks.length ? c.fallbacks.map((f) => `${pname(f.provider_id)} / ${f.model}`).join(" → ") : "None"}</dd>
              <dt className="text-muted-foreground">Max output</dt>
              <dd>{c.params.max_output_tokens} tokens</dd>
              <dt className="text-muted-foreground">Temperature</dt>
              <dd>{c.params.temperature ?? "provider default"}</dd>
              <dt className="text-muted-foreground">Timeout</dt>
              <dd>{c.limits.timeout_seconds}s</dd>
              <dt className="text-muted-foreground">Cost cap</dt>
              <dd>{c.limits.max_cost_usd_per_run !== null ? `$${c.limits.max_cost_usd_per_run}` : "None"}</dd>
              <dt className="text-muted-foreground">Schemas</dt>
              <dd>{[c.input_schema && "input", c.output_schema && "output"].filter(Boolean).join(", ") || "None"}</dd>
            </dl>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>System prompt</CardTitle></CardHeader>
          <CardContent>
            <pre className="max-h-64 overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap">{c.system_prompt || "(empty)"}</pre>
            <p className="mt-3 text-xs text-muted-foreground">Created {fmtDate(a.created_at)} · Revision {a.revision}</p>
          </CardContent>
        </Card>
      </div>
      <div className="mt-6">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Recent runs</h2>
          <Link href={`/runs`} className="text-sm underline underline-offset-4">All runs</Link>
        </div>
        {runs.isPending ? <LoadingRows rows={2} /> : runs.isError ? <ErrorState error={runs.error} /> : <RunsTable runs={runs.data.items} hideAgent emptyText="No runs yet. Use the test console to try the draft." />}
      </div>
    </div>
  )
}
