"use client"

import { Plus, Sparkles } from "lucide-react"
import Link from "next/link"
import { useState } from "react"
import { toast } from "sonner"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { StatusBadge } from "@/components/common/status-badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAgentMutations, useAgents } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"
import { fmtRelative } from "@/lib/format"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

export default function AgentsPage() {
  const { workspaceId, role } = useWorkspaceCtx()
  const [q, setQ] = useState("")
  const [status, setStatus] = useState("")
  const agents = useAgents(workspaceId, { q: q || undefined, status: status || undefined })
  const canWrite = can(role, "agents:write")
  const canPublish = can(role, "agents:publish")
  const m = useAgentMutations(workspaceId)

  async function installStarters() {
    try {
      const r = await m.starterPack.mutateAsync()
      const parts = [r.created.length && `${r.created.length} added`, r.updated.length && `${r.updated.length} moved to your best free provider`]
      toast.success(parts.filter(Boolean).join(", ") || "Starter agents are already up to date")
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }
  const starterButton = canPublish && (
    <Button variant="outline" disabled={m.starterPack.isPending} onClick={installStarters}
      title="Ready-made agents on the best free provider you have connected (Models page)">
      <Sparkles className="size-4" /> Install starter agents
    </Button>
  )

  return (
    <div>
      <PageHeader
        title="Agents"
        description="Versioned agent definitions. Production runs always execute an immutable published version."
        actions={(
          <div className="flex flex-wrap gap-2">
            {starterButton}
            {canWrite && (
              <Link href="/agents/new" className={buttonVariants()}>
                <Plus className="size-4" /> New agent
              </Link>
            )}
          </div>
        )}
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <label htmlFor="agent-search" className="sr-only">Search agents</label>
        <Input id="agent-search" placeholder="Search by name…" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-xs" />
        <label htmlFor="agent-status" className="sr-only">Filter by status</label>
        <select id="agent-status" value={status} onChange={(e) => setStatus(e.target.value)} className="h-9 rounded-md border bg-background px-2 text-sm">
          <option value="">All statuses</option>
          {["draft", "published", "paused", "retired"].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      {agents.isPending ? (
        <LoadingRows />
      ) : agents.isError ? (
        <ErrorState error={agents.error} onRetry={() => agents.refetch()} />
      ) : agents.data.items.length === 0 ? (
        <EmptyState
          title={q || status ? "No agents match these filters" : "No agents yet"}
          description={q || status ? "Try a different search." : "Create an agent, choose a model, and publish a version to start running it."}
          action={canWrite && !q && !status && (
            <div className="flex flex-wrap justify-center gap-2">
              {starterButton}
              <Link href="/agents/new" className={buttonVariants()}>Create your first agent</Link>
            </div>
          )}
        />
      ) : (
        <div className="rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Published</TableHead>
                <TableHead>Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {agents.data.items.map((a) => (
                <TableRow key={a.id}>
                  <TableCell>
                    <Link href={`/agents/${a.id}`} className="font-medium hover:underline">{a.name}</Link>
                    {a.description && <p className="max-w-xs truncate text-xs text-muted-foreground">{a.description}</p>}
                  </TableCell>
                  <TableCell><StatusBadge status={a.status} /></TableCell>
                  <TableCell className="font-mono text-xs">{a.draft.model?.model ?? "—"}</TableCell>
                  <TableCell>
                    {a.published_version ? `v${a.published_version}` : "—"}
                    {a.draft_dirty && a.published_version && <span className="ml-2 text-xs text-amber-700 dark:text-amber-400">unpublished changes</span>}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{fmtRelative(a.updated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
