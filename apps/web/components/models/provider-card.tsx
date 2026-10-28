"use client"

import { useState } from "react"
import { toast } from "sonner"

import { DemoBadge, StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { useProviderMutations } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"
import { fmtRelative } from "@/lib/format"
import type { Provider } from "@/lib/schemas"

export function ProviderCard({ p, workspaceId, canWrite }: { p: Provider; workspaceId: string; canWrite: boolean }) {
  const m = useProviderMutations(workspaceId)
  const [dialog, setDialog] = useState<null | "rotate" | "delete" | "models">(null)
  const [value, setValue] = useState("")
  const [models, setModels] = useState<string[] | null>(null)
  const demo = p.kind === "demo"

  async function act(fn: () => Promise<unknown>, ok: string) {
    try {
      await fn()
      toast.success(ok)
      setDialog(null)
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {p.name} {demo && <DemoBadge />}
          <span className="ml-auto"><StatusBadge status={p.health.status} /></span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          <dt className="text-muted-foreground">Type</dt><dd className="font-mono text-xs">{p.kind}</dd>
          {p.base_url && (<><dt className="text-muted-foreground">Base URL</dt><dd className="font-mono text-xs break-all">{p.base_url}</dd></>)}
          {!demo && (<><dt className="text-muted-foreground">API key</dt><dd className="font-mono text-xs">{p.has_api_key ? `••••${p.api_key_last4}` : "none"}</dd></>)}
          <dt className="text-muted-foreground">Allowlist</dt><dd className="text-xs">{p.allowed_models.length ? p.allowed_models.join(", ") : "any model"}</dd>
          <dt className="text-muted-foreground">Timeout</dt><dd>{p.timeout_seconds}s</dd>
          <dt className="text-muted-foreground">Last check</dt>
          <dd>{p.health.checked_at ? `${fmtRelative(p.health.checked_at)}${p.health.latency_ms != null ? ` · ${p.health.latency_ms} ms` : ""}` : "never"}</dd>
        </dl>
        {p.health.error && <p className="rounded-md bg-red-50 p-2 text-xs text-red-800 dark:bg-red-950/50 dark:text-red-200">{p.health.error}</p>}
        {demo && <p className="text-xs text-muted-foreground">Built-in for demo mode. Returns deterministic synthetic text and never calls a real model. demo-slow takes 60 s (to exercise cancel/timeout); demo-fail always errors (to exercise fallbacks).</p>}
        {models && <p className="text-xs text-muted-foreground">Catalog ({models.length}): {models.slice(0, 30).join(", ")}{models.length > 30 ? "…" : ""}</p>}
        {canWrite && (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button size="sm" variant="outline" disabled={m.test.isPending} onClick={async () => {
              try {
                const r = await m.test.mutateAsync(p.id)
                setModels(r.models)
                if (r.ok) toast.success(`Connected in ${r.latency_ms} ms (${r.models.length} models)`)
                else toast.error(`Connection failed: ${r.error}`)
              } catch (e) {
                toast.error(errorMessage(e))
              }
            }}>
              {m.test.isPending ? "Testing…" : "Test connection"}
            </Button>
            {!demo && (
              <>
                <Button size="sm" variant="outline" onClick={() => { setValue(""); setDialog("rotate") }}>Rotate key</Button>
                <Button size="sm" variant="outline" onClick={() => { setValue(p.allowed_models.join(", ")); setDialog("models") }}>Edit allowlist</Button>
                <label className="ml-auto flex items-center gap-2 text-xs">
                  <Switch checked={p.enabled} onCheckedChange={(v) => act(() => m.update.mutateAsync({ id: p.id, enabled: v }), v ? "Provider enabled" : "Provider disabled")} aria-label="Enabled" />
                  Enabled
                </label>
                <Button size="sm" variant="ghost" className="text-destructive" onClick={() => setDialog("delete")}>Delete</Button>
              </>
            )}
          </div>
        )}
      </CardContent>
      <Dialog open={dialog !== null} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent>
          {dialog === "rotate" && (
            <>
              <DialogHeader>
                <DialogTitle>Rotate API key</DialogTitle>
                <DialogDescription>The new key replaces the old one immediately for all new provider calls. The change is audited.</DialogDescription>
              </DialogHeader>
              <Label htmlFor={`rot-${p.id}`}>New API key</Label>
              <Input id={`rot-${p.id}`} type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} />
              <DialogFooter>
                <Button variant="ghost" onClick={() => setDialog(null)}>Cancel</Button>
                <Button disabled={!value} onClick={() => act(() => m.update.mutateAsync({ id: p.id, api_key: value }), "Key rotated")}>Rotate</Button>
              </DialogFooter>
            </>
          )}
          {dialog === "models" && (
            <>
              <DialogHeader>
                <DialogTitle>Model allowlist</DialogTitle>
                <DialogDescription>Comma-separated model IDs. Agents may only publish and run models on this list. Leave empty to allow any.</DialogDescription>
              </DialogHeader>
              <Label htmlFor={`al-${p.id}`}>Allowed models</Label>
              <Input id={`al-${p.id}`} value={value} onChange={(e) => setValue(e.target.value)} />
              <DialogFooter>
                <Button variant="ghost" onClick={() => setDialog(null)}>Cancel</Button>
                <Button onClick={() => act(() => m.update.mutateAsync({ id: p.id, allowed_models: value.split(",").map((s) => s.trim()).filter(Boolean) }), "Allowlist saved")}>Save</Button>
              </DialogFooter>
            </>
          )}
          {dialog === "delete" && (
            <>
              <DialogHeader>
                <DialogTitle>Delete {p.name}?</DialogTitle>
                <DialogDescription>Agents referencing this provider will fail to publish and their runs will skip this provider in the fallback chain.</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="ghost" onClick={() => setDialog(null)}>Cancel</Button>
                <Button variant="destructive" onClick={() => act(() => m.remove.mutateAsync(p.id), "Provider deleted")}>Delete</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  )
}
