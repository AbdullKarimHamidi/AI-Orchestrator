"use client"

import { useParams, useRouter } from "next/navigation"
import { useState } from "react"
import { toast } from "sonner"

import { ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { ToolForm } from "@/components/tools/tool-form"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { useTool, useToolMutations } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

function exampleArgs(schema: Record<string, unknown>): string {
  const props = (schema.properties ?? {}) as Record<string, { type?: string }>
  return JSON.stringify(Object.fromEntries(Object.entries(props).map(([k, v]) => [k, v.type === "number" || v.type === "integer" ? 0 : v.type === "boolean" ? false : ""])), null, 2)
}

export default function ToolPage() {
  const { toolId } = useParams<{ toolId: string }>()
  const { workspaceId, role } = useWorkspaceCtx()
  const tool = useTool(workspaceId, toolId)
  const m = useToolMutations(workspaceId)
  const router = useRouter()
  const [args, setArgs] = useState<string | null>(null)
  const write = can(role, "agents:write")

  if (tool.isPending) return <LoadingRows />
  if (tool.isError) return <ErrorState error={tool.error} onRetry={() => tool.refetch()} />
  const t = tool.data
  const argText = args ?? exampleArgs(t.input_schema)
  const result = m.test.data

  async function runTest() {
    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(argText)
    } catch {
      return toast.error("Arguments are not valid JSON")
    }
    m.test.mutate({ id: t.id, args: parsed })
  }

  return (
    <div className="max-w-3xl space-y-6">
      <PageHeader title={t.name} description={t.kind === "http" ? "HTTP tool" : "MCP tool"} actions={write && (
        <>
          <div className="flex items-center gap-2">
            <Switch id="t-enabled" checked={t.enabled} onCheckedChange={async (v: boolean) => {
              try {
                await m.update.mutateAsync({ id: t.id, enabled: v })
                toast.success(v ? "Tool enabled" : "Tool disabled: agents can no longer call it")
              } catch (e) {
                toast.error(errorMessage(e))
              }
            }} />
            <Label htmlFor="t-enabled">Enabled</Label>
          </div>
          <Button variant="outline" className="text-destructive" onClick={async () => {
            if (!window.confirm(`Delete tool ${t.name}? Agents using it will lose access.`)) return
            try {
              await m.remove.mutateAsync(t.id)
              toast.success("Tool deleted")
              router.push("/tools")
            } catch (e) {
              toast.error(errorMessage(e))
            }
          }}>Delete</Button>
        </>
      )} />
      {write && (
        <Card>
          <CardHeader>
            <CardTitle>Test the tool</CardTitle>
            <CardDescription>Makes one real call with these arguments, exactly as an agent would.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Label htmlFor="t-args" className="sr-only">Arguments</Label>
            <Textarea id="t-args" rows={5} className="font-mono text-xs" value={argText} onChange={(e) => setArgs(e.target.value)} />
            <Button onClick={runTest} disabled={m.test.isPending}>{m.test.isPending ? "Calling…" : "Run test"}</Button>
            {result && (
              <div role="status" className={result.ok ? "rounded-md border border-emerald-500/50 p-3" : "rounded-md border border-destructive/50 p-3"}>
                <p className="mb-2 text-sm font-medium">{result.ok ? "Success" : "Failed"} · {result.latency_ms} ms</p>
                <pre className="max-h-72 overflow-auto text-xs whitespace-pre-wrap">{result.ok ? result.output : result.error}</pre>
              </div>
            )}
          </CardContent>
        </Card>
      )}
      {write ? (
        <ToolForm key={t.updated_at} tool={t} submitLabel="Save changes" onSubmit={async (body) => {
          await m.update.mutateAsync({ id: t.id, ...body })
          toast.success("Tool saved")
        }} />
      ) : (
        <pre className="rounded-md bg-muted p-3 text-xs">{JSON.stringify({ description: t.description, input_schema: t.input_schema, http: t.http, mcp: t.mcp }, null, 2)}</pre>
      )}
    </div>
  )
}
