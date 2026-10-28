"use client"

import { cn } from "cn"
import Link from "next/link"
import { usePathname } from "next/navigation"

const TABS = [
  { href: "/evaluations", label: "Overview" },
  { href: "/evaluations/datasets", label: "Datasets" },
  { href: "/evaluations/runs", label: "Evaluation runs" },
  { href: "/evaluations/compare", label: "Compare" },
]

export function EvalNav() {
  const pathname = usePathname()
  return (
    <nav aria-label="Evaluation sections" className="mb-5 flex gap-1 overflow-x-auto border-b">
      {TABS.map((t) => (
        <Link key={t.href} href={t.href} aria-current={pathname === t.href ? "page" : undefined}
          className={cn("-mb-px border-b-2 px-3 py-2 text-sm whitespace-nowrap", pathname === t.href ? "border-primary font-medium" : "border-transparent text-muted-foreground hover:text-foreground")}>
          {t.label}
        </Link>
      ))}
    </nav>
  )
}

export function PassRate({ rate, passed, total }: { rate: number | null; passed?: number; total?: number }) {
  if (rate === null) return <span className="text-sm text-muted-foreground">—</span>
  const pct = Math.round(rate * 100)
  const tone = pct >= 80 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-red-500"
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-1.5 w-20 overflow-hidden rounded-full bg-muted" aria-hidden><span className={cn("block h-full", tone)} style={{ width: `${pct}%` }} /></span>
      <span className="text-sm tabular-nums">{pct}%{total !== undefined && <span className="text-muted-foreground"> ({passed}/{total})</span>}</span>
    </span>
  )
}

export const SCORERS = [
  ["contains", "Output contains expected"],
  ["exact", "Exact match"],
  ["not_contains", "Output does not contain expected"],
  ["regex", "Expected is a regex"],
  ["json_valid", "Output is valid JSON"],
  ["not_empty", "Output is not empty"],
] as const
