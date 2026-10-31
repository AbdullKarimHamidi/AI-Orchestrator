"use client"

import { Check, ExternalLink } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAgentMutations, useProviderMutations } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"
import type { Preset } from "@/lib/schemas"

/** One-step setup for AI APIs with a free tier: get a key from the link, paste it, done. */
export function FreeProviders({ presets, workspaceId, canWrite }: { presets: Preset[]; workspaceId: string; canWrite: boolean }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {presets.map((p) => <PresetCard key={p.id} p={p} workspaceId={workspaceId} canWrite={canWrite} />)}
    </div>
  )
}

function PresetCard({ p, workspaceId, canWrite }: { p: Preset; workspaceId: string; canWrite: boolean }) {
  const m = useProviderMutations(workspaceId)
  const agents = useAgentMutations(workspaceId)
  const [value, setValue] = useState(p.needs_key ? "" : p.base_url ?? "")
  const inputId = `preset-${p.id}`

  async function moveStarterAgents() {
    try {
      const r = await agents.starterPack.mutateAsync()
      toast.success(`Starter agents now use ${p.name}: ${r.created.length + r.updated.length} ready${r.skipped.length ? `, ${r.skipped.length} you edited were left alone` : ""}.`)
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }

  async function add() {
    try {
      const prov = await m.addPreset.mutateAsync(p.needs_key ? { id: p.id, api_key: value.trim() } : { id: p.id, base_url: value.trim() || undefined })
      setValue("")
      if (prov.health.status === "unhealthy") {
        toast.warning(`${p.name} was added but is not reachable yet: ${prov.health.error ?? "unknown error"}`, { duration: 15000 })
        return
      }
      const models = prov.kind === "ollama" && prov.suggested_models.length ? ` Installed models: ${prov.suggested_models.slice(0, 4).join(", ")}.` : ""
      toast.success(`${p.name} is connected.${models}`, {
        duration: 12000,
        action: { label: "Use for starter agents", onClick: () => void moveStarterAgents() },
      })
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          {p.name}
          {p.provider_id && <Badge variant="secondary" className="ml-auto"><Check className="size-3" /> Connected</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground">{p.free_tier}</p>
        <p className="text-xs"><span className="text-muted-foreground">Models: </span><span className="font-mono">{p.models.join(", ")}</span></p>
        <a href={p.signup_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs underline">
          {p.needs_key ? "Get a free API key" : "Download Ollama"} <ExternalLink className="size-3" />
        </a>
        {!p.provider_id && canWrite && (
          <form className="space-y-1.5" onSubmit={(e) => { e.preventDefault(); void add() }}>
            <Label htmlFor={inputId}>{p.needs_key ? "API key" : "Ollama URL"}</Label>
            <div className="flex gap-2">
              <Input id={inputId} type={p.needs_key ? "password" : "url"} autoComplete="off" value={value}
                placeholder={p.needs_key ? "Paste your key" : "http://localhost:11434"} onChange={(e) => setValue(e.target.value)} />
              <Button type="submit" size="sm" disabled={m.addPreset.isPending || (p.needs_key && !value.trim())}>Connect</Button>
            </div>
            <p className="text-xs text-muted-foreground">{p.id === "ollama" ? "Running the app with Docker? Use http://host.docker.internal:11434 and start Ollama with OLLAMA_HOST=0.0.0.0." : null} Or set <code>{p.env_var}</code> in .env to connect it for every workspace.</p>
          </form>
        )}
      </CardContent>
    </Card>
  )
}
