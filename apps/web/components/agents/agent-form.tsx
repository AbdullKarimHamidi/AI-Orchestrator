"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { Plus, Trash2 } from "lucide-react"
import Link from "next/link"
import { useState } from "react"
import { useController, useFieldArray, useForm, useWatch, type Control, type UseFormRegister } from "react-hook-form"
import { z } from "zod"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type { AgentInput } from "@/hooks/use-api"
import type { AgentConfig, KnowledgeBase, Provider, Tool } from "@/lib/schemas"

const jsonObject = z
  .string()
  .refine((s) => {
    if (!s.trim()) return true
    try {
      const v = JSON.parse(s)
      return typeof v === "object" && v !== null && !Array.isArray(v) && (v.type === undefined || v.type === "object")
    } catch {
      return false
    }
  }, "Must be a JSON Schema object with type \"object\" (or empty)")

const optionalNumber = (min: number, max: number) =>
  z
    .string()
    .refine((s) => s.trim() === "" || (!Number.isNaN(Number(s)) && Number(s) >= min && Number(s) <= max), `Must be between ${min} and ${max}`)

export const agentFormSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(120),
  description: z.string().max(2000),
  system_prompt: z.string().max(50_000),
  provider_id: z.string().min(1, "Choose a provider"),
  model: z.string().trim().min(1, "Model is required").max(200),
  fallbacks: z.array(z.object({ provider_id: z.string().min(1, "Choose a provider"), model: z.string().trim().min(1, "Model is required") })).max(3),
  temperature: optionalNumber(0, 2),
  top_p: optionalNumber(0.0001, 1),
  max_output_tokens: z.coerce.number<string>().int().min(1).max(64_000),
  timeout_seconds: z.coerce.number<string>().int().min(5).max(900),
  max_cost_usd_per_run: optionalNumber(0, 1000),
  input_schema: jsonObject,
  output_schema: jsonObject,
  tool_ids: z.array(z.string()).max(50),
  knowledge_base_ids: z.array(z.string()).max(20),
  knowledge_top_k: z.coerce.number<string>().int().min(1).max(20),
  max_tool_calls: z.coerce.number<string>().int().min(0).max(50),
})
export type AgentFormValues = z.input<typeof agentFormSchema>

export function toFormValues(name: string, description: string, c?: AgentConfig): AgentFormValues {
  return {
    name,
    description,
    system_prompt: c?.system_prompt ?? "",
    provider_id: c?.model?.provider_id ?? "",
    model: c?.model?.model ?? "",
    fallbacks: c?.fallbacks ?? [],
    temperature: c?.params.temperature?.toString() ?? "",
    top_p: c?.params.top_p?.toString() ?? "",
    max_output_tokens: String(c?.params.max_output_tokens ?? 1024),
    timeout_seconds: String(c?.limits.timeout_seconds ?? 120),
    max_cost_usd_per_run: c?.limits.max_cost_usd_per_run?.toString() ?? "",
    input_schema: c?.input_schema ? JSON.stringify(c.input_schema, null, 2) : "",
    output_schema: c?.output_schema ? JSON.stringify(c.output_schema, null, 2) : "",
    tool_ids: c?.tool_ids ?? [],
    knowledge_base_ids: c?.knowledge_base_ids ?? [],
    knowledge_top_k: String(c?.knowledge_top_k ?? 5),
    max_tool_calls: String(c?.limits.max_tool_calls ?? 8),
  }
}

export function toAgentInput(v: AgentFormValues, base?: AgentConfig): AgentInput {
  const num = (s: string) => (s.trim() === "" ? null : Number(s))
  const obj = (s: string) => (s.trim() ? (JSON.parse(s) as Record<string, unknown>) : null)
  return {
    name: v.name.trim(),
    description: v.description,
    config: {
      system_prompt: v.system_prompt,
      model: { provider_id: v.provider_id, model: v.model.trim() },
      fallbacks: v.fallbacks.map((f) => ({ provider_id: f.provider_id, model: f.model.trim() })),
      params: { temperature: num(v.temperature), top_p: num(v.top_p), max_output_tokens: Number(v.max_output_tokens) },
      tool_ids: v.tool_ids ?? base?.tool_ids ?? [],
      knowledge_base_ids: v.knowledge_base_ids ?? base?.knowledge_base_ids ?? [],
      knowledge_top_k: Number(v.knowledge_top_k ?? 5),
      input_schema: obj(v.input_schema),
      output_schema: obj(v.output_schema),
      limits: { timeout_seconds: Number(v.timeout_seconds), max_cost_usd_per_run: num(v.max_cost_usd_per_run), max_tool_calls: Number(v.max_tool_calls ?? 8) },
    },
  }
}

function FieldError({ id, msg }: { id: string; msg?: string }) {
  return msg ? (
    <p id={id} className="text-xs text-destructive">
      {msg}
    </p>
  ) : null
}

const selectCls = "h-9 w-full rounded-md border bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring aria-invalid:border-destructive"

function ModelPicker({ prefix, providers, control, register, errors }: {
  prefix: "primary" | `fallbacks.${number}`
  providers: Provider[]
  control: Control<AgentFormValues, unknown, z.output<typeof agentFormSchema>>
  register: UseFormRegister<AgentFormValues>
  errors?: { provider_id?: { message?: string }; model?: { message?: string } }
}) {
  const providerField = prefix === "primary" ? "provider_id" : (`${prefix}.provider_id` as const)
  const modelField = prefix === "primary" ? "model" : (`${prefix}.model` as const)
  const pid = useWatch({ control, name: providerField }) as string
  const provider = providers.find((p) => p.id === pid)
  const listId = `models-${prefix.replace(".", "-")}`
  const pidId = `${listId}-provider`
  const modelId = `${listId}-model`
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="space-y-1.5">
        <Label htmlFor={pidId}>Provider</Label>
        <select id={pidId} className={selectCls} aria-invalid={!!errors?.provider_id} {...register(providerField)}>
          <option value="">Select a provider…</option>
          {providers.map((p) => (
            <option key={p.id} value={p.id} disabled={!p.enabled}>
              {p.name} ({p.kind}){p.enabled ? "" : " — disabled"}
            </option>
          ))}
        </select>
        <FieldError id={`${pidId}-err`} msg={errors?.provider_id?.message} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={modelId}>Model</Label>
        <Input id={modelId} list={listId} placeholder={provider?.allowed_models[0] ?? "model id"} aria-invalid={!!errors?.model} {...register(modelField)} />
        <datalist id={listId}>
          {provider?.allowed_models.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
        <FieldError id={`${modelId}-err`} msg={errors?.model?.message} />
        {provider && provider.allowed_models.length > 0 && <p className="text-xs text-muted-foreground">Allowlist: {provider.allowed_models.join(", ")}</p>}
      </div>
    </div>
  )
}

function CheckboxList({ name, control, items, empty }: {
  name: "tool_ids" | "knowledge_base_ids"
  control: Control<AgentFormValues, unknown, z.output<typeof agentFormSchema>>
  items: { id: string; label: string; hint: string }[]
  empty: React.ReactNode
}) {
  const { field } = useController({ control, name })
  const value = (field.value as string[]) ?? []
  // keep assignments to items that no longer exist visible, so they can be removed
  const known = new Set(items.map((i) => i.id))
  const all = [...items, ...value.filter((v) => !known.has(v)).map((id) => ({ id, label: id, hint: "not found (deleted?)" }))]
  if (all.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>
  return (
    <ul className="space-y-1.5">
      {all.map((i) => (
        <li key={i.id} className="flex items-start gap-2">
          <input
            type="checkbox"
            id={`${name}-${i.id}`}
            className="mt-1 size-4"
            checked={value.includes(i.id)}
            onChange={(e) => field.onChange(e.target.checked ? [...value, i.id] : value.filter((v) => v !== i.id))}
          />
          <label htmlFor={`${name}-${i.id}`} className="text-sm">
            <span className="font-medium">{i.label}</span> <span className="text-muted-foreground">{i.hint}</span>
          </label>
        </li>
      ))}
    </ul>
  )
}

export function AgentForm({ initial, baseConfig, providers, tools = [], knowledgeBases = [], submitLabel, onSubmit, cancelHref }: {
  initial: AgentFormValues
  baseConfig?: AgentConfig
  providers: Provider[]
  tools?: Tool[]
  knowledgeBases?: KnowledgeBase[]
  submitLabel: string
  onSubmit: (input: AgentInput) => Promise<void>
  cancelHref: string
}) {
  const [serverError, setServerError] = useState<string | null>(null)
  const form = useForm<AgentFormValues, unknown, z.output<typeof agentFormSchema>>({ resolver: zodResolver(agentFormSchema), defaultValues: initial })
  const { register, control, formState } = form
  const { errors, isSubmitting, isDirty } = formState
  const fallbacks = useFieldArray({ control, name: "fallbacks" })

  async function submit(values: z.output<typeof agentFormSchema>) {
    setServerError(null)
    try {
      await onSubmit(toAgentInput(values as unknown as AgentFormValues, baseConfig))
    } catch (e) {
      setServerError(e instanceof Error ? e.message : "Save failed")
    }
  }

  return (
    <form onSubmit={form.handleSubmit(submit)} noValidate className="space-y-6">
      {serverError && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{serverError}</AlertDescription>
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Identity</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="name">Name</Label>
            <Input id="name" aria-invalid={!!errors.name} aria-describedby="name-err" {...register("name")} />
            <FieldError id="name-err" msg={errors.name?.message} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="description">Description</Label>
            <Textarea id="description" rows={2} {...register("description")} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Instructions</CardTitle>
          <CardDescription>The system prompt sent with every request.</CardDescription>
        </CardHeader>
        <CardContent>
          <Label htmlFor="system_prompt" className="sr-only">
            System prompt
          </Label>
          <Textarea id="system_prompt" rows={8} className="font-mono text-sm" {...register("system_prompt")} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Model routing</CardTitle>
          <CardDescription>
            One attempt per entry, in order. Fallbacks are tried only after the previous attempt fails; every attempt is budget-checked and recorded.{" "}
            {providers.length === 0 && (
              <Link href="/models" className="underline">
                Configure a provider first.
              </Link>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Primary</legend>
            <ModelPicker prefix="primary" providers={providers} control={control} register={register} errors={{ provider_id: errors.provider_id, model: errors.model }} />
          </fieldset>
          {fallbacks.fields.map((f, i) => (
            <fieldset key={f.id} className="space-y-2 rounded-lg border p-3">
              <div className="flex items-center justify-between">
                <legend className="text-sm font-medium">Fallback {i + 1}</legend>
                <Button type="button" variant="ghost" size="sm" onClick={() => fallbacks.remove(i)} aria-label={`Remove fallback ${i + 1}`}>
                  <Trash2 className="size-4" />
                </Button>
              </div>
              <ModelPicker prefix={`fallbacks.${i}`} providers={providers} control={control} register={register} errors={errors.fallbacks?.[i]} />
            </fieldset>
          ))}
          <Button type="button" variant="outline" size="sm" disabled={fallbacks.fields.length >= 3} onClick={() => fallbacks.append({ provider_id: "", model: "" })}>
            <Plus className="size-4" /> Add fallback
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Parameters and limits</CardTitle>
          <CardDescription>Leave temperature / top-p empty to use the provider default.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          {([
            ["temperature", "Temperature (0–2)"],
            ["top_p", "Top-p (0–1)"],
            ["max_output_tokens", "Max output tokens"],
            ["timeout_seconds", "Timeout (seconds)"],
            ["max_cost_usd_per_run", "Max cost per run (USD)"],
          ] as const).map(([name, label]) => (
            <div key={name} className="space-y-1.5">
              <Label htmlFor={name}>{label}</Label>
              <Input id={name} inputMode="decimal" aria-invalid={!!errors[name]} aria-describedby={`${name}-err`} {...register(name)} />
              <FieldError id={`${name}-err`} msg={errors[name]?.message} />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Input and output contracts</CardTitle>
          <CardDescription>Optional JSON Schemas. Inputs are validated before a run is queued; outputs are parsed and validated after the model responds.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          {(["input_schema", "output_schema"] as const).map((n) => (
            <div key={n} className="space-y-1.5">
              <Label htmlFor={n}>{n === "input_schema" ? "Input schema (variables)" : "Output schema"}</Label>
              <Textarea id={n} rows={7} className="font-mono text-xs" placeholder='{"type": "object", "properties": {}}' aria-invalid={!!errors[n]} aria-describedby={`${n}-err`} {...register(n)} />
              <FieldError id={`${n}-err`} msg={errors[n]?.message} />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Tools</CardTitle>
          <CardDescription>The model may call only the tools checked here. Every call is validated against the tool&apos;s schema and recorded in the run timeline.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <CheckboxList name="tool_ids" control={control}
            items={tools.map((t) => ({ id: t.id, label: t.name, hint: `${t.kind.toUpperCase()}${t.enabled ? "" : " · disabled"} · ${t.description.slice(0, 80)}` }))}
            empty={<>No tools yet. <Link href="/tools/new" className="underline">Create a tool</Link> or <Link href="/integrations/mcp" className="underline">import from an MCP server</Link>.</>} />
          <div className="max-w-48 space-y-1.5">
            <Label htmlFor="max_tool_calls">Max tool calls per run</Label>
            <Input id="max_tool_calls" inputMode="numeric" aria-invalid={!!errors.max_tool_calls} {...register("max_tool_calls")} />
            <FieldError id="max_tool_calls-err" msg={errors.max_tool_calls?.message} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Knowledge</CardTitle>
          <CardDescription>Before every answer, the most relevant passages from these knowledge bases are added to the prompt and returned as citations.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <CheckboxList name="knowledge_base_ids" control={control}
            items={knowledgeBases.map((k) => ({ id: k.id, label: k.name, hint: `${k.doc_count} documents · ${k.embedding ? k.embedding.model : "built-in search"}` }))}
            empty={<>No knowledge bases yet. <Link href="/knowledge/bases" className="underline">Create one</Link>.</>} />
          <div className="max-w-48 space-y-1.5">
            <Label htmlFor="knowledge_top_k">Passages per answer</Label>
            <Input id="knowledge_top_k" inputMode="numeric" aria-invalid={!!errors.knowledge_top_k} {...register("knowledge_top_k")} />
            <FieldError id="knowledge_top_k-err" msg={errors.knowledge_top_k?.message} />
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center justify-end gap-2">
        <Link href={cancelHref} className={buttonVariants({ variant: "ghost" })}>
          Cancel
        </Link>
        <Button type="submit" disabled={isSubmitting || (!isDirty && submitLabel !== "Create agent")}>
          {isSubmitting ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  )
}
