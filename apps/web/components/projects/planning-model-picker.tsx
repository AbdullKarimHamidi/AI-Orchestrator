"use client"

import Link from "next/link"

import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { Provider } from "@/lib/schemas"

/** "" provider_id means: each planning agent runs on its own published model. */
export type PlanningModel = { provider_id: string; model: string }

const selectCls = "h-9 w-full rounded-md border bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"

export function modelsFor(provider: Provider | undefined): string[] {
  if (!provider) return []
  return provider.allowed_models.length ? provider.allowed_models : provider.suggested_models
}

/** Providers a planning run can use: enabled, and not the Demo echo model unless nothing else exists. */
export function usableProviders(providers: Provider[]): Provider[] {
  const enabled = providers.filter((p) => p.enabled)
  const real = enabled.filter((p) => p.kind !== "demo")
  return real.length ? real : enabled
}

export function PlanningModelPicker({ providers, value, onChange, idPrefix = "planning" }: {
  providers: Provider[]
  value: PlanningModel
  onChange: (v: PlanningModel) => void
  idPrefix?: string
}) {
  const options = usableProviders(providers)
  const provider = options.find((p) => p.id === value.provider_id)
  const suggestions = modelsFor(provider)
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-provider`}>Provider</Label>
        <select id={`${idPrefix}-provider`} className={selectCls} value={value.provider_id}
          onChange={(e) => {
            const next = options.find((p) => p.id === e.target.value)
            onChange({ provider_id: e.target.value, model: modelsFor(next)[0] ?? "" })
          }}>
          <option value="">Each agent&apos;s own published model</option>
          {options.map((p) => <option key={p.id} value={p.id}>{p.name}{p.health.status === "unhealthy" ? " (last test failed)" : ""}</option>)}
        </select>
      </div>
      {value.provider_id && (
        <div className="space-y-1.5">
          <Label htmlFor={`${idPrefix}-model`}>Model</Label>
          <Input id={`${idPrefix}-model`} list={`${idPrefix}-models`} value={value.model} placeholder={suggestions[0] ?? "model id"}
            onChange={(e) => onChange({ ...value, model: e.target.value })} />
          <datalist id={`${idPrefix}-models`}>{suggestions.map((m) => <option key={m} value={m} />)}</datalist>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        {value.provider_id
          ? "Every planning agent keeps its instructions but answers with this model."
          : "Planners use the model saved in their last published version. Edits you have not published are not used."}
        {options.length === 0 && <> <Link href="/models" className="underline">Add a provider</Link> first.</>}
      </p>
    </div>
  )
}
