"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useState } from "react"
import { useForm, useWatch } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useProviderMutations } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"

export const providerFormSchema = z
  .object({
    kind: z.enum(["openai", "anthropic", "gemini", "openai_compatible"]),
    name: z.string().trim().min(1, "Name is required").max(80),
    api_key: z.string().max(500),
    base_url: z.string().trim(),
    allowed_models: z.string(),
    timeout_seconds: z.coerce.number<string>().int().min(1).max(600),
  })
  .superRefine((v, ctx) => {
    if (v.kind === "openai_compatible") {
      if (!/^https?:\/\/.+/.test(v.base_url)) ctx.addIssue({ code: "custom", path: ["base_url"], message: "A http(s) base URL is required" })
    } else if (!v.api_key) {
      ctx.addIssue({ code: "custom", path: ["api_key"], message: "API key is required" })
    }
  })
type Values = z.input<typeof providerFormSchema>

const HINTS: Record<string, string> = {
  openai: "Chat Completions API. Example models: gpt-4.1-mini",
  anthropic: "Messages API (anthropic-version 2023-06-01).",
  gemini: "Gemini generateContent API (key sent as x-goog-api-key header).",
  openai_compatible: "Any server exposing /v1/chat/completions (vLLM, Ollama, LM Studio…). Include /v1 in the base URL.",
}

export function AddProviderDialog({ workspaceId, open, onOpenChange }: { workspaceId: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const { create } = useProviderMutations(workspaceId)
  const [err, setErr] = useState<string | null>(null)
  const form = useForm<Values, unknown, z.output<typeof providerFormSchema>>({
    resolver: zodResolver(providerFormSchema),
    defaultValues: { kind: "openai", name: "", api_key: "", base_url: "", allowed_models: "", timeout_seconds: "60" },
  })
  const kind = useWatch({ control: form.control, name: "kind" })
  const { errors, isSubmitting } = form.formState

  async function submit(v: z.output<typeof providerFormSchema>) {
    setErr(null)
    try {
      await create.mutateAsync({
        kind: v.kind,
        name: v.name,
        api_key: v.api_key || undefined,
        base_url: v.base_url || undefined,
        allowed_models: v.allowed_models.split(",").map((s) => s.trim()).filter(Boolean),
        timeout_seconds: v.timeout_seconds,
      })
      toast.success("Provider added. Run a connection test to verify the key.")
      form.reset()
      onOpenChange(false)
    } catch (e) {
      setErr(errorMessage(e))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add model provider</DialogTitle>
          <DialogDescription>The API key is encrypted at rest in the backend and never returned to the browser. Only its last 4 characters are shown.</DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(submit)} noValidate className="space-y-3">
          {err && <Alert variant="destructive" role="alert"><AlertDescription>{err}</AlertDescription></Alert>}
          <div className="space-y-1.5">
            <Label htmlFor="p-kind">Provider type</Label>
            <select id="p-kind" className="h-9 w-full rounded-md border bg-background px-2 text-sm" {...form.register("kind")}>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="gemini">Google Gemini</option>
              <option value="openai_compatible">OpenAI-compatible</option>
            </select>
            <p className="text-xs text-muted-foreground">{HINTS[kind]}</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="p-name">Display name</Label>
            <Input id="p-name" aria-invalid={!!errors.name} {...form.register("name")} />
            {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="p-key">API key{kind === "openai_compatible" && " (optional)"}</Label>
            <Input id="p-key" type="password" autoComplete="off" aria-invalid={!!errors.api_key} {...form.register("api_key")} />
            {errors.api_key && <p className="text-xs text-destructive">{errors.api_key.message}</p>}
          </div>
          {kind === "openai_compatible" && (
            <div className="space-y-1.5">
              <Label htmlFor="p-url">Base URL</Label>
              <Input id="p-url" placeholder="http://localhost:11434/v1" aria-invalid={!!errors.base_url} {...form.register("base_url")} />
              {errors.base_url && <p className="text-xs text-destructive">{errors.base_url.message}</p>}
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="p-models">Model allowlist (comma-separated; empty allows any)</Label>
            <Input id="p-models" placeholder="gpt-4.1-mini, gpt-4.1" {...form.register("allowed_models")} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="p-timeout">Request timeout (seconds)</Label>
            <Input id="p-timeout" inputMode="numeric" {...form.register("timeout_seconds")} />
            {errors.timeout_seconds && <p className="text-xs text-destructive">{errors.timeout_seconds.message}</p>}
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={isSubmitting}>{isSubmitting ? "Saving…" : "Add provider"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
