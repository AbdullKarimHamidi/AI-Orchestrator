"use client"

import { useState } from "react"
import { toast } from "sonner"

import { AgentHeader } from "@/components/agents/agent-header"
import { useAgentPage } from "@/components/agents/use-agent-page"
import { EmptyState, ErrorState, LoadingRows } from "@/components/common/states"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAgentMutations, useAgentVersions, useVersionDiff } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"
import { fmtDate } from "@/lib/format"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

const show = (v: unknown) => (v === undefined ? "∅" : JSON.stringify(v))

export default function VersionsPage() {
  const { agentId, workspaceId, agent } = useAgentPage()
  const { role } = useWorkspaceCtx()
  const versions = useAgentVersions(workspaceId, agentId)
  const { rollback } = useAgentMutations(workspaceId)
  const [a, setA] = useState<number>()
  const [b, setB] = useState<number>()
  const diff = useVersionDiff(workspaceId, agentId, a, b)

  if (agent.isPending || versions.isPending) return <LoadingRows />
  if (agent.isError) return <ErrorState error={agent.error} />
  if (versions.isError) return <ErrorState error={versions.error} />
  const list = versions.data
  return (
    <div>
      <AgentHeader agent={agent.data} />
      {list.length === 0 ? (
        <EmptyState title="No versions yet" description="Publishing the draft creates version 1." />
      ) : (
        <>
          <div className="rounded-xl border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Version</TableHead>
                  <TableHead>Note</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead>Config hash</TableHead>
                  <TableHead>Published</TableHead>
                  <TableHead><span className="sr-only">Actions</span></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((v) => (
                  <TableRow key={v.id}>
                    <TableCell className="font-medium">
                      v{v.version} {agent.data.published_version === v.version && <Badge className="ml-1">serving</Badge>}
                    </TableCell>
                    <TableCell className="max-w-xs truncate text-sm">{v.note || "—"}</TableCell>
                    <TableCell className="font-mono text-xs">{v.config.model?.model}</TableCell>
                    <TableCell className="font-mono text-xs" title={v.config_hash}>{v.config_hash.slice(0, 12)}</TableCell>
                    <TableCell className="text-sm">{fmtDate(v.created_at)}</TableCell>
                    <TableCell className="text-right">
                      {can(role, "agents:publish") && agent.data.status !== "retired" && agent.data.published_version !== v.version && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={async () => {
                            try {
                              await rollback.mutateAsync({ id: agentId, version: v.version })
                              toast.success(`Now serving v${v.version}; draft reset to it`)
                            } catch (e) {
                              toast.error(errorMessage(e))
                            }
                          }}
                        >
                          Roll back to v{v.version}
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {list.length > 1 && (
            <Card className="mt-6">
              <CardHeader><CardTitle>Compare versions</CardTitle></CardHeader>
              <CardContent>
                <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
                  <label htmlFor="cmp-a">From</label>
                  <select id="cmp-a" className="h-8 rounded-md border bg-background px-2" value={a ?? ""} onChange={(e) => setA(Number(e.target.value) || undefined)}>
                    <option value="">—</option>
                    {list.map((v) => <option key={v.version} value={v.version}>v{v.version}</option>)}
                  </select>
                  <label htmlFor="cmp-b">to</label>
                  <select id="cmp-b" className="h-8 rounded-md border bg-background px-2" value={b ?? ""} onChange={(e) => setB(Number(e.target.value) || undefined)}>
                    <option value="">—</option>
                    {list.map((v) => <option key={v.version} value={v.version}>v{v.version}</option>)}
                  </select>
                </div>
                {!a || !b || a === b ? (
                  <p className="text-sm text-muted-foreground">Choose two different versions.</p>
                ) : diff.isPending ? (
                  <LoadingRows rows={2} />
                ) : diff.isError ? (
                  <ErrorState error={diff.error} />
                ) : diff.data.changes.length === 0 ? (
                  <p className="text-sm">These versions have identical configuration.</p>
                ) : (
                  <Table>
                    <TableHeader><TableRow><TableHead>Field</TableHead><TableHead>v{a}</TableHead><TableHead>v{b}</TableHead></TableRow></TableHeader>
                    <TableBody>
                      {diff.data.changes.map((c) => (
                        <TableRow key={c.path}>
                          <TableCell className="font-mono text-xs">{c.path}</TableCell>
                          <TableCell className="max-w-xs font-mono text-xs break-all whitespace-pre-wrap text-red-700 dark:text-red-400">{show(c.from)}</TableCell>
                          <TableCell className="max-w-xs font-mono text-xs break-all whitespace-pre-wrap text-emerald-700 dark:text-emerald-400">{show(c.to)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
