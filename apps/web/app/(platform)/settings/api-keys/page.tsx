"use client"

import { Copy } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { copyText } from "@/components/security/invite-panel"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useApiKeys, useTeamMutations } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"
import { fmtDate } from "@/lib/format"
import { roleSchema, type Role } from "@/lib/schemas"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

export default function ApiKeysPage() {
  const { workspaceId, role } = useWorkspaceCtx()
  const manage = can(role, "api_keys:manage")
  const keys = useApiKeys(workspaceId, manage)
  const t = useTeamMutations(workspaceId)
  const [name, setName] = useState("")
  const [keyRole, setKeyRole] = useState<Role>("operator")
  const [days, setDays] = useState("")
  const [err, setErr] = useState<string | null>(null)
  const [created, setCreated] = useState<string | null>(null)
  const origin = typeof window === "undefined" ? "" : window.location.origin

  if (!manage) {
    return (
      <div>
        <PageHeader title="API keys" />
        <p className="text-sm text-muted-foreground">Your role ({role}) cannot manage API keys. Ask an administrator.</p>
      </div>
    )
  }

  async function create(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    try {
      const k = await t.createKey.mutateAsync({ name, role: keyRole, expires_in_days: days ? Number(days) : null })
      setCreated(k.key)
      setName("")
    } catch (x) {
      setErr(errorMessage(x))
    }
  }

  return (
    <div>
      <PageHeader title="API keys" description="Call this workspace from your own apps, scripts and CI. A key acts with the role you give it, only in this workspace." />
      <form onSubmit={create} className="mb-6 rounded-xl border p-4">
        {err && <Alert variant="destructive" className="mb-3" role="alert"><AlertDescription>{err}</AlertDescription></Alert>}
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="k-name">Name</Label>
            <Input id="k-name" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. support-bot backend" className="w-64" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="k-role">Role</Label>
            <select id="k-role" value={keyRole} onChange={(e) => setKeyRole(e.target.value as Role)} className="h-9 rounded-md border bg-background px-2 text-sm">
              {roleSchema.options.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="k-days">Expires in (days)</Label>
            <Input id="k-days" inputMode="numeric" pattern="[0-9]*" value={days} onChange={(e) => setDays(e.target.value)} placeholder="never" className="w-28" />
          </div>
          <Button type="submit" disabled={t.createKey.isPending}>Create key</Button>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">Tip: <strong>operator</strong> can run published agents and read results, which is all most apps need.</p>
      </form>

      {created && (
        <div className="mb-6 rounded-lg border border-emerald-500/50 bg-emerald-500/5 p-4" role="status">
          <p className="mb-2 text-sm font-medium">Copy your key now. It will not be shown again.</p>
          <div className="flex gap-2">
            <Input readOnly value={created} aria-label="New API key" className="font-mono text-xs" onFocus={(e) => e.target.select()} />
            <Button type="button" variant="outline" onClick={() => copyText(created)} aria-label="Copy API key"><Copy className="size-4" /></Button>
          </div>
          <p className="mt-3 mb-1 text-xs text-muted-foreground">Run a published agent and wait up to 30 s for the answer:</p>
          <pre className="overflow-x-auto rounded bg-muted p-2 text-xs">{`curl -X POST "${origin}/api/v1/runs?wait_seconds=30" \\
  -H "Authorization: Bearer ${created.slice(0, 12)}…" \\
  -H "Content-Type: application/json" \\
  -d '{"agent_id": "agt_…", "input": {"message": "Hello"}}'`}</pre>
        </div>
      )}

      {keys.isPending ? <LoadingRows /> : keys.isError ? <ErrorState error={keys.error} onRetry={() => keys.refetch()} /> : keys.data.length === 0 ? (
        <EmptyState title="No API keys yet" description="Create one above to call agents from your own code." />
      ) : (
        <div className="rounded-xl border">
          <Table>
            <TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Key</TableHead><TableHead>Role</TableHead><TableHead>Last used</TableHead><TableHead>Expires</TableHead><TableHead><span className="sr-only">Actions</span></TableHead></TableRow></TableHeader>
            <TableBody>
              {keys.data.map((k) => (
                <TableRow key={k.id}>
                  <TableCell>{k.name}</TableCell>
                  <TableCell className="font-mono text-xs">{k.prefix}…</TableCell>
                  <TableCell className="text-sm">{k.role}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{k.last_used_at ? fmtDate(k.last_used_at) : "never"}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{k.expires_at ? fmtDate(k.expires_at) : "never"}</TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="ghost" className="text-destructive" onClick={async () => {
                      if (!window.confirm(`Revoke "${k.name}"? Apps using it stop working immediately.`)) return
                      try {
                        await t.revokeKey.mutateAsync(k.id)
                        toast.success("Key revoked")
                      } catch (x) {
                        toast.error(errorMessage(x))
                      }
                    }}>Revoke</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
