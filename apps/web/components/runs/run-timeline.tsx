import { cn } from "cn"

import type { RunEvent } from "@/lib/schemas"

const TONE: Record<string, string> = {
  "model.error": "border-red-500",
  "run.failed": "border-red-500",
  "run.timed_out": "border-orange-500",
  "run.cancelled": "border-zinc-500",
  "run.cancel_requested": "border-zinc-400",
  "run.completed": "border-emerald-500",
  "model.response": "border-emerald-400",
  "run.lease_expired": "border-amber-500",
  "tool.call": "border-sky-500",
  "tool.result": "border-sky-400",
  "tool.limit_reached": "border-amber-500",
  "knowledge.retrieved": "border-violet-500",
}

function summary(e: RunEvent): string {
  const d = e.data as Record<string, unknown>
  switch (e.type) {
    case "model.request":
      return `${d.slot}: ${d.provider_kind} / ${d.model}`
    case "model.response":
      return `${d.slot}: ${d.input_tokens} in / ${d.output_tokens} out · ${d.latency_ms} ms${d.priced ? "" : " · unpriced"}`
    case "model.error":
      return `${d.slot}: ${d.kind}${d.status ? ` (HTTP ${d.status})` : ""} — ${d.message}${d.will_fallback ? " · trying fallback" : ""}`
    case "model.skipped":
      return `${d.slot}: ${d.reason}`
    case "tool.call":
      return `${d.tool}(${JSON.stringify(d.arguments ?? {}).slice(0, 200)})`
    case "tool.result":
      return `${d.tool}: ${d.ok ? "ok" : "error"} · ${d.latency_ms} ms · ${String(d.preview ?? "").slice(0, 200)}`
    case "tool.limit_reached":
      return `stopped after ${d.max_tool_calls} tool calls; asking the model for a final answer`
    case "knowledge.retrieved": {
      const sources = (d.sources ?? []) as { n: number; title: string }[]
      return d.count ? `${d.count} passage${d.count === 1 ? "" : "s"}: ${sources.map((s) => `[${s.n}] ${s.title}`).join(", ")}` : "no matching passages"
    }
    case "run.started":
      return `attempt ${d.attempt}`
    case "run.lease_expired":
      return `worker ${d.previous_worker} lost; now ${d.new_status}`
    default: {
      const err = d.error as { message?: string } | null | undefined
      return err?.message ?? ""
    }
  }
}

export function RunTimeline({ events, live }: { events: RunEvent[]; live?: boolean }) {
  return (
    <ol className="space-y-2" aria-live={live ? "polite" : undefined} aria-label="Run events">
      {events.map((e) => (
        <li key={e.seq} className={cn("border-l-2 py-1 pl-3", TONE[e.type] ?? "border-border")}>
          <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
            <span className="font-mono text-xs text-muted-foreground tabular-nums">#{e.seq}</span>
            <span className="font-medium">{e.type}</span>
            <time className="text-xs text-muted-foreground" dateTime={e.ts}>{new Date(e.ts).toLocaleTimeString()}</time>
          </div>
          {summary(e) && <p className="text-sm break-words text-muted-foreground">{summary(e)}</p>}
        </li>
      ))}
      {events.length === 0 && <li className="text-sm text-muted-foreground">Waiting for events…</li>}
    </ol>
  )
}
