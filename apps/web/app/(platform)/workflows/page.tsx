"use client"

import { useMemo, useState } from "react"
import { Activity, ArrowRight, GitBranch, Plus, Search, Workflow } from "lucide-react"
import Link from "next/link"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { StatusBadge } from "@/components/common/status-badge"
import { buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useWorkflows } from "@/hooks/use-modules"
import { fmtRelative } from "@/lib/format"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

export default function WorkflowsPage() {
  const { workspaceId, role } = useWorkspaceCtx()
  const workflows = useWorkflows(workspaceId)
  const canWrite = can(role, "agents:write")
  const [search, setSearch] = useState("")
  const items = useMemo(() => workflows.data?.items ?? [], [workflows.data?.items])
  const filtered = useMemo(() => items.filter((w) => (w.name + " " + w.description).toLowerCase().includes(search.toLowerCase())), [items, search])
  const published = items.filter((w) => w.status === "published").length
  const drafts = items.filter((w) => w.status === "draft").length
  return (
    <div className="space-y-6">
      <PageHeader title="Workflows" description="Design multi-step pipelines that coordinate agents, tools, knowledge retrieval, transformations, and conditional routes."
        actions={canWrite && <Link href="/workflows/new" className={buttonVariants()}><Plus className="size-4" /> New workflow</Link>} />
      <section className="grid gap-3 sm:grid-cols-3" aria-label="Workflow summary">
        {[
          { label: "Total workflows", value: items.length, icon: Workflow },
          { label: "Published", value: published, icon: GitBranch },
          { label: "Drafts", value: drafts, icon: Activity },
        ].map((stat) => <div key={stat.label} className="rounded-xl border bg-card p-4"><div className="flex items-center justify-between text-sm text-muted-foreground">{stat.label}<stat.icon className="size-4" /></div><p className="mt-3 text-3xl font-semibold tracking-tight tabular-nums">{stat.value}</p></div>)}
      </section>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative min-w-0 flex-1"><Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input aria-label="Search workflows" className="pl-9" placeholder="Search workflows…" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
        <p className="text-xs text-muted-foreground">{filtered.length} workflow{filtered.length === 1 ? "" : "s"}</p>
      </div>
      {workflows.isPending ? <LoadingRows rows={4} /> : workflows.isError ? <ErrorState error={workflows.error} onRetry={() => workflows.refetch()} /> : filtered.length === 0 ? (
        <EmptyState title={search ? "No matching workflows" : "No workflows yet"} description={search ? "Try another name or description." : "Combine published agents, tools, knowledge and conditions into a reusable pipeline."}
          action={canWrite && <Link href="/workflows/new" className={buttonVariants()}><Plus className="size-4" /> Create your first workflow</Link>} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {filtered.map((w) => (
            <Link key={w.id} href={`/workflows/${w.id}`} className="group flex min-w-0 flex-col rounded-xl border bg-card p-5 transition-colors hover:border-primary/40 hover:bg-accent/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <div className="flex items-start gap-3"><div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><GitBranch className="size-5" /></div><div className="min-w-0 flex-1"><h2 className="truncate font-semibold">{w.name}</h2><p className="mt-1 line-clamp-2 min-h-10 text-sm text-muted-foreground">{w.description || "No description added yet."}</p></div><ArrowRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" /></div>
              <div className="mt-4 flex flex-wrap items-center gap-2"><StatusBadge status={w.status} />{w.published_version ? <span className="rounded-full border px-2.5 py-1 text-xs text-muted-foreground">Published v{w.published_version}</span> : <span className="rounded-full border border-dashed px-2.5 py-1 text-xs text-muted-foreground">Not published</span>}{w.draft_dirty && w.published_version ? <span className="text-xs text-amber-700 dark:text-amber-300">Draft changed</span> : null}</div>
              <div className="mt-4 flex items-center justify-between gap-3 border-t pt-4 text-xs text-muted-foreground"><span>{w.draft.steps.length} step{w.draft.steps.length === 1 ? "" : "s"} · {w.draft.steps.map((s) => s.type).slice(0, 3).join(" → ")}{w.draft.steps.length > 3 ? " → …" : ""}</span><span className="shrink-0">{fmtRelative(w.updated_at)}</span></div>
            </Link>
          ))}
        </div>
      )}
      <div className="flex items-start gap-2 rounded-xl border border-dashed p-4 text-sm text-muted-foreground"><Workflow className="mt-0.5 size-4 shrink-0" /> Use the workflow editor to validate routes and references before publishing. Published versions remain immutable, and runs execute through the background worker.</div>
    </div>
  )
}
