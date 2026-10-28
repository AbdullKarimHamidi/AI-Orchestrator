"use client"

import { Plus } from "lucide-react"
import Link from "next/link"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { Badge } from "@/components/ui/badge"
import { buttonVariants } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useTools } from "@/hooks/use-api"
import { fmtDate } from "@/lib/format"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

export default function ToolsPage() {
  const { workspaceId, role } = useWorkspaceCtx()
  const tools = useTools(workspaceId)
  const write = can(role, "agents:write")
  const actions = write && (
    <>
      <Link href="/integrations/mcp" className={buttonVariants({ variant: "outline" })}>Import from MCP</Link>
      <Link href="/tools/new" className={buttonVariants()}><Plus className="size-4" /> New HTTP tool</Link>
    </>
  )
  return (
    <div>
      <PageHeader title="Tools" description="Functions agents can call: your HTTP APIs or tools on MCP servers. Assign them per agent; every call is validated and logged." actions={actions} />
      {tools.isPending ? <LoadingRows /> : tools.isError ? <ErrorState error={tools.error} onRetry={() => tools.refetch()} /> : tools.data.length === 0 ? (
        <EmptyState title="No tools yet" description="Connect an HTTP API (for example your CRM or ticket system) or import tools from an MCP server, then enable them on an agent." action={actions} />
      ) : (
        <div className="rounded-xl border">
          <Table>
            <TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Type</TableHead><TableHead>Target</TableHead><TableHead>Updated</TableHead></TableRow></TableHeader>
            <TableBody>
              {tools.data.map((t) => (
                <TableRow key={t.id}>
                  <TableCell>
                    <Link href={`/tools/${t.id}`} className="font-mono text-sm font-medium underline-offset-4 hover:underline">{t.name}</Link>
                    {!t.enabled && <Badge variant="outline" className="ml-2">disabled</Badge>}
                    <p className="max-w-md truncate text-xs text-muted-foreground">{t.description}</p>
                  </TableCell>
                  <TableCell><Badge variant="secondary">{t.kind.toUpperCase()}</Badge></TableCell>
                  <TableCell className="max-w-xs truncate font-mono text-xs">{t.kind === "http" ? `${t.http?.method} ${t.http?.url}` : `${t.mcp?.server_url} → ${t.mcp?.tool_name}`}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{fmtDate(t.updated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
