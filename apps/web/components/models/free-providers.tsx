"use client"

import { Check, ExternalLink } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useProviderMutations } from "@/hooks/use-api"
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
  const [value, setValue] = useState(p.needs_key ? "" : p.base_url ?? "")
  const inputId = `preset-${p.id}`

  async function add() {
    try {
      await m.addPreset.mutateAsync(p.needs_key ? { id: p.id, api_key: value.trim() } : { id: p.id, base_url: value.trim() || undefined })
      toast.success(`${p.name} is ready. Install the starter agents on the Agents page to use it.`)
      setValue("")
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
                placeholder={p.needs_key ? "Paste your key" : "http://host.docker.internal:11434/v1"} onChange={(e) => setValue(e.target.value)} />
              <Button type="submit" size="sm" disabled={m.addPreset.isPending || (p.needs_key && !value.trim())}>Connect</Button>
            </div>
            <p className="text-xs text-muted-foreground">{p.id === "ollama" ? "For Docker Desktop, use host.docker.internal and make sure Ollama accepts connections from Docker." : null} Or set <code>{p.env_var}</code> in .env to connect it for every workspace.</p>
          </form>
        )}
      </CardContent>
    </Card>
  )
}
