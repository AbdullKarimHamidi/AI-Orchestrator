import { cn } from "cn"

import type { AgentStatus, RunStatus } from "@/lib/schemas"

const STYLES: Record<string, string> = {
  queued: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-100",
  running: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200",
  waiting_for_approval: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  completed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  failed: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
  cancelled: "bg-zinc-200 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200",
  timed_out: "bg-orange-100 text-orange-900 dark:bg-orange-950 dark:text-orange-200",
  draft: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-100",
  published: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  paused: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  retired: "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  healthy: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  unhealthy: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
  unknown: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
}

export function StatusBadge({ status, className }: { status: RunStatus | AgentStatus | string; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap", STYLES[status] ?? STYLES.unknown, className)}>
      {status === "running" && <span className="size-1.5 animate-pulse rounded-full bg-current" aria-hidden />}
      {status.replaceAll("_", " ")}
    </span>
  )
}

export function DemoBadge() {
  return (
    <span className="inline-flex items-center rounded-md border border-amber-400 px-1.5 py-0.5 text-[11px] font-semibold text-amber-800 dark:text-amber-300" title="Synthetic output from the demo provider. No model was called.">
      DEMO
    </span>
  )
}
