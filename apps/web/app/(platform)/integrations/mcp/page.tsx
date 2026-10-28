"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"
import { toast } from "sonner"

import { ErrorState, PageHeader } from "@/components/common/states"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useToolMutations } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

export default function McpImportPage() {
  const { workspaceId, role } = useWorkspaceCtx()
  const m = useToolMutations(workspaceId)
  const router = useRouter()
  const [url, setUrl] = useState("")
  const [authName, setAuthName] = useState("Authorization")
  const [authValue, setAuthValue] = useState("")
  const [prefix, setPrefix] = useState("")
  const [picked, setPicked] = useState<string[]>([])

  if (!can(role, "agents:write")) return <ErrorState error={new Error("Your role cannot add tools.")} />
  const secret_headers = authName.trim() && authValue ? { [authName.trim()]: authValue } : {}
  const remote = m.discoverMcp.data

  async function discover(e: React.FormEvent) {
    e.preventDefault()
    setPicked([])
    try {
      const tools = await m.discoverMcp.mutateAsync({ server_url: url.trim(), secret_headers })
      setPicked(tools.map((t) => t.name))
    } catch {
      // shown below
    }
  }

  async function importTools() {
    try {
      const created = await m.importMcp.mutateAsync({ server_url: url.trim(), secret_headers, tools: picked, name_prefix: prefix })
      toast.success(`Imported ${created.length} tool${created.length === 1 ? "" : "s"}`)
      router.push("/tools")
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <PageHeader title="Import tools from an MCP server" description="Connect a remote MCP server (Streamable HTTP transport), pick the tools you trust, and assign them to agents like any other tool." />
      <Card>
        <CardHeader>
          <CardTitle>Server</CardTitle>
          <CardDescription>The credential is encrypted at rest and stored on each imported tool. Private network addresses are blocked unless the server sets TOOLS_ALLOW_PRIVATE_NETWORKS=true.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={discover} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="mcp-url">Server URL</Label>
              <Input id="mcp-url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://mcp.example.com/mcp" className="font-mono text-sm" required />
            </div>
            <div className="flex flex-wrap gap-2">
              <div className="w-48 space-y-1.5">
                <Label htmlFor="mcp-hname">Auth header</Label>
                <Input id="mcp-hname" value={authName} onChange={(e) => setAuthName(e.target.value)} />
              </div>
              <div className="min-w-64 flex-1 space-y-1.5">
                <Label htmlFor="mcp-hvalue">Value (optional)</Label>
                <Input id="mcp-hvalue" type="password" autoComplete="off" value={authValue} onChange={(e) => setAuthValue(e.target.value)} placeholder="Bearer …" />
              </div>
            </div>
            <Button type="submit" disabled={!/^https?:\/\/.+/.test(url.trim()) || m.discoverMcp.isPending}>{m.discoverMcp.isPending ? "Connecting…" : "Discover tools"}</Button>
          </form>
        </CardContent>
      </Card>
      {m.discoverMcp.isError && <Alert variant="destructive" role="alert"><AlertDescription>{errorMessage(m.discoverMcp.error)}</AlertDescription></Alert>}
      {remote && (
        <Card>
          <CardHeader>
            <CardTitle>Tools offered ({remote.length})</CardTitle>
            <CardDescription>Only the tools you select are imported. A prefix helps avoid name clashes between servers.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {remote.length === 0 ? <p className="text-sm text-muted-foreground">The server offers no tools.</p> : (
              <ul className="space-y-2">
                {remote.map((t) => (
                  <li key={t.name}>
                    <label className="flex items-start gap-2 text-sm">
                      <input type="checkbox" className="mt-1" checked={picked.includes(t.name)} onChange={(e) => setPicked(e.target.checked ? [...picked, t.name] : picked.filter((n) => n !== t.name))} />
                      <span>
                        <span className="font-mono font-medium">{t.name}</span>
                        {t.description && <span className="block text-xs text-muted-foreground">{t.description}</span>}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex flex-wrap items-end gap-2">
              <div className="w-56 space-y-1.5">
                <Label htmlFor="mcp-prefix">Name prefix (optional)</Label>
                <Input id="mcp-prefix" value={prefix} onChange={(e) => setPrefix(e.target.value)} placeholder="github_" className="font-mono" />
              </div>
              <Button type="button" onClick={importTools} disabled={!picked.length || m.importMcp.isPending}>{m.importMcp.isPending ? "Importing…" : `Import ${picked.length} selected`}</Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
