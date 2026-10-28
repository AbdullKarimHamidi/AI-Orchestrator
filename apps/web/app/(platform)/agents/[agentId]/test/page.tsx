"use client"

import { useState } from "react"

import { AgentHeader } from "@/components/agents/agent-header"
import { useAgentPage } from "@/components/agents/use-agent-page"
import { RunInspector } from "@/components/runs/run-inspector"
import { ErrorState, LoadingRows } from "@/components/common/states"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useRun, useRunMutations } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

export default function TestConsolePage() {
  const { agentId, workspaceId, agent } = useAgentPage()
  const { role } = useWorkspaceCtx()
  const { create } = useRunMutations(workspaceId)
  const [message, setMessage] = useState("")
  const [variables, setVariables] = useState("")
  const [source, setSource] = useState<"draft" | "published">("draft")
  const [error, setError] = useState<string | null>(null)
  const [runId, setRunId] = useState<string>("")
  const run = useRun(workspaceId, runId)

  if (agent.isPending) return <LoadingRows />
  if (agent.isError) return <ErrorState error={agent.error} />
  const a = agent.data
  const canDraft = can(role, "agents:write")
  const canPublished = can(role, "runs:create") && a.status === "published"

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    let vars: Record<string, unknown> | undefined
    if (variables.trim()) {
      try {
        vars = JSON.parse(variables)
      } catch {
        setError("Variables must be valid JSON")
        return
      }
    }
    try {
      const r = await create.mutateAsync({ agent_id: agentId, source, input: { message, ...(vars ? { variables: vars } : {}) }, idempotencyKey: crypto.randomUUID() })
      setRunId(r.id)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <div>
      <AgentHeader agent={a} actions={false} />
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Send a test message</CardTitle>
          <CardDescription>
            The run is queued and executed by the background worker, exactly like production. Draft runs snapshot the current draft config.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            {error && <Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert>}
            <fieldset className="flex flex-wrap gap-4 text-sm">
              <legend className="sr-only">Configuration to test</legend>
              <label className="flex items-center gap-2">
                <input type="radio" name="source" value="draft" checked={source === "draft"} disabled={!canDraft} onChange={() => setSource("draft")} /> Current draft
              </label>
              <label className="flex items-center gap-2">
                <input type="radio" name="source" value="published" checked={source === "published"} disabled={!canPublished} onChange={() => setSource("published")} />
                Published {a.published_version ? `v${a.published_version}` : "(none)"}
              </label>
            </fieldset>
            <div className="space-y-1.5">
              <Label htmlFor="msg">Message</Label>
              <Textarea id="msg" rows={4} value={message} onChange={(e) => setMessage(e.target.value)} required />
            </div>
            {a.draft.input_schema && (
              <div className="space-y-1.5">
                <Label htmlFor="vars">Variables (JSON, validated against the input schema)</Label>
                <Textarea id="vars" rows={3} className="font-mono text-xs" value={variables} onChange={(e) => setVariables(e.target.value)} />
              </div>
            )}
            <Button type="submit" disabled={!message.trim() || create.isPending || (source === "draft" ? !canDraft : !canPublished)}>
              {create.isPending ? "Queuing…" : "Run"}
            </Button>
          </form>
        </CardContent>
      </Card>
      {runId && (run.data ? <RunInspector run={run.data} compact /> : run.isError ? <ErrorState error={run.error} /> : <LoadingRows rows={2} />)}
    </div>
  )
}
