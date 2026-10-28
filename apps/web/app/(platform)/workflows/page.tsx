"use client"

import { Plus } from "lucide-react"
import Link from "next/link"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { StatusBadge } from "@/components/common/status-badge"
import { buttonVariants } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useWorkflows } from "@/hooks/use-modules"
import { fmtRelative } from "@/lib/format"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

export default function WorkflowsPage() {
  const { workspaceId, role } = useWorkspaceCtx()
  const workflows = useWorkflows(workspaceId)
  const canWrite = can(role, "agents:write")
  return (
    <div>
      <PageHeader
        title="Workflows"
        description="Multi-step pipelines that chain agents, tools, knowledge search, templates and conditions. They run in the worker like agent runs, with live per-step events."
        actions={canWrite && <Link href="/workflows/new" className={buttonVariants()}><Plus className="size-4" /> New workflow</Link>}
      />
      {workflows.isPending ? <LoadingRows /> : workflows.isError ? <ErrorState error={workflows.error} onRetry={() => workflows.refetch()} /> : workflows.data.items.length === 0 ? (
        <EmptyState title="No workflows yet" description="Combine published agents, tools and conditions into a pipeline, publish it, and run it from the UI or the API."
          action={canWrite && <Link href="/workflows/new" className={buttonVariants()}>Create your first workflow</Link>} />
      ) : (
        <div className="rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow><TableHead>Name</TableHead><TableHead>Status</TableHead><TableHead>Steps</TableHead><TableHead>Version</TableHead><TableHead>Updated</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {workflows.data.items.map((w) => (
                <TableRow key={w.id}>
                  <TableCell>
                    <Link href={`/workflows/${w.id}`} className="font-medium underline-offset-4 hover:underline">{w.name}</Link>
                    {w.description && <p className="max-w-md truncate text-xs text-muted-foreground">{w.description}</p>}
                  </TableCell>
                  <TableCell><StatusBadge status={w.status} /></TableCell>
                  <TableCell className="text-sm">{w.draft.steps.map((s) => s.type).join(" → ")}</TableCell>
                  <TableCell className="text-sm">{w.published_version ? `v${w.published_version}` : "—"}{w.draft_dirty && w.published_version ? <span className="ml-1 text-xs text-muted-foreground">(draft changed)</span> : null}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{fmtRelative(w.updated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
