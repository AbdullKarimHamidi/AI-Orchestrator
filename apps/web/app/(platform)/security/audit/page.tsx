"use client"

import { useState } from "react"

import { ErrorState, EmptyState, LoadingRows, PageHeader } from "@/components/common/states"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAuditLogs, useMembers } from "@/hooks/use-api"
import { fmtDate } from "@/lib/format"
import { useWorkspaceCtx } from "@/lib/workspace-context"

export default function AuditPage() {
  const { workspaceId } = useWorkspaceCtx()
  const [action, setAction] = useState("")
  const [offset, setOffset] = useState(0)
  const logs = useAuditLogs(workspaceId, action || undefined, offset)
  const members = useMembers(workspaceId)
  const who = (id: string | null) => (id ? members.data?.find((m) => m.user_id === id)?.email ?? id : "system")
  return (
    <div>
      <PageHeader title="Audit log" description="Append-only record of security-relevant changes in this workspace. Secret values are never recorded." />
      <div className="mb-4 flex items-center gap-3">
        <label htmlFor="a-action" className="sr-only">Filter by action</label>
        <Input id="a-action" placeholder="Filter by exact action, e.g. agent.publish" value={action} onChange={(e) => { setAction(e.target.value.trim()); setOffset(0) }} className="w-80" />
        {logs.data && <span className="text-sm text-muted-foreground">{logs.data.total} entries</span>}
      </div>
      {logs.isPending ? <LoadingRows /> : logs.isError ? <ErrorState error={logs.error} onRetry={() => logs.refetch()} /> : logs.data.items.length === 0 ? <EmptyState title="No audit entries" /> : (
        <>
          <div className="rounded-xl border">
            <Table>
              <TableHeader><TableRow><TableHead>Time</TableHead><TableHead>Action</TableHead><TableHead>Actor</TableHead><TableHead>Target</TableHead><TableHead>Details</TableHead></TableRow></TableHeader>
              <TableBody>
                {logs.data.items.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell className="text-sm whitespace-nowrap">{fmtDate(e.ts)}</TableCell>
                    <TableCell className="font-mono text-xs">{e.action}</TableCell>
                    <TableCell className="text-sm">{who(e.actor_id)}</TableCell>
                    <TableCell className="font-mono text-xs">{e.target_type}{e.target_id ? `:${e.target_id.slice(0, 12)}` : ""}</TableCell>
                    <TableCell className="max-w-md truncate font-mono text-xs" title={JSON.stringify(e.details)}>{JSON.stringify(e.details)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="mt-3 flex gap-2">
            <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</Button>
            <Button size="sm" variant="outline" disabled={offset + 50 >= logs.data.total} onClick={() => setOffset(offset + 50)}>Next</Button>
          </div>
        </>
      )}
    </div>
  )
}
