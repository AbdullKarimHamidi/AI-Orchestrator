"use client"

import { useState } from "react"
import { toast } from "sonner"

import { RunInspector } from "@/components/runs/run-inspector"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useRun } from "@/hooks/use-api"
import { useWorkflowMutations } from "@/hooks/use-modules"
import { errorMessage } from "@/lib/api-client"
import type { Workflow } from "@/lib/schemas"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

export function WorkflowRunPanel({ workflow: w }: { workflow: Workflow }) {
  const { workspaceId, role } = useWorkspaceCtx()
  const m = useWorkflowMutations(workspaceId)
  const [message, setMessage] = useState("")
  const [variables, setVariables] = useState("")
  const [scope, setScope] = useState("")
  const [source, setSource] = useState<"published" | "draft">(w.published_version ? "published" : "draft")
  const [runId, setRunId] = useState("")
  const run = useRun(workspaceId, runId)
  if (!can(role, "runs:create")) return null

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    let vars: Record<string, unknown> = {}
    try {
      vars = variables.trim() ? JSON.parse(variables) : {}
    } catch {
      toast.error("Variables must be valid JSON")
      return
    }
    try {
      const r = await m.run.mutateAsync({ id: w.id, source, input: { message, ...(variables.trim() ? { variables: vars } : {}), ...(scope.trim() ? { memory_scope: scope.trim() } : {}) } })
      setRunId(r.id)
      toast.success("Workflow run queued")
    } catch (x) {
      toast.error(errorMessage(x))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Run this workflow</CardTitle>
        <CardDescription>The run is queued for the worker; steps and model calls stream in below.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="wr-msg">Message</Label>
            <Textarea id="wr-msg" rows={3} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="e.g. I was charged twice and want a refund" required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="wr-vars">Variables (JSON, optional)</Label>
            <Input id="wr-vars" className="font-mono text-xs" value={variables} onChange={(e) => setVariables(e.target.value)} placeholder='{"customer": "Ada"}' />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label htmlFor="wr-src">Definition</Label>
              <select id="wr-src" className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={source} onChange={(e) => setSource(e.target.value as "published" | "draft")}>
                <option value="published" disabled={!w.published_version}>Published v{w.published_version ?? "—"}</option>
                {can(role, "agents:write") && <option value="draft">Draft</option>}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="wr-scope">Memory scope</Label>
              <Input id="wr-scope" value={scope} onChange={(e) => setScope(e.target.value)} placeholder="optional" />
            </div>
          </div>
          <div className="sm:col-span-2">
            <Button type="submit" disabled={!message.trim() || m.run.isPending || w.status === "archived"}>{m.run.isPending ? "Queuing…" : "Run workflow"}</Button>
          </div>
        </form>
        {run.data && <RunInspector run={run.data} compact />}
      </CardContent>
    </Card>
  )
}
