"use client"

import { useQuery } from "@tanstack/react-query"
import { ArrowRight, Bot, Clock3, FileText, FolderKanban, Plus, Sparkles } from "lucide-react"
import Link from "next/link"
import { useMemo, useState } from "react"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api } from "@/lib/api-client"
import { pageOf } from "@/lib/schemas"
import { projectSchema } from "@/lib/schemas/projects"
import { useWorkspaceCtx } from "@/lib/workspace-context"
import { cn } from "cn"

const statusLabel: Record<string, string> = {
  planning: "Planning", ready: "Plan ready", in_progress: "In progress", blocked: "Blocked",
  completed: "Completed", archived: "Archived",
}
const statusTone: Record<string, string> = {
  planning: "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  ready: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  in_progress: "border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300",
  blocked: "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300",
  completed: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  archived: "border-border bg-muted text-muted-foreground",
}

export default function ProjectsPage() {
  const { workspaceId } = useWorkspaceCtx()
  const [search, setSearch] = useState("")
  const projects = useQuery({
    queryKey: ["projects", workspaceId],
    queryFn: () => api.get("/projects", pageOf(projectSchema), { query: { limit: 200 } }),
    enabled: !!workspaceId,
    refetchInterval: (q) => q.state.data?.items.some((p) => p.status === "planning") ? 2500 : false,
  })
  const filtered = useMemo(() => (projects.data?.items ?? []).filter((p) =>
    (p.name + " " + p.idea).toLowerCase().includes(search.toLowerCase())), [projects.data, search])
  const items = projects.data?.items ?? []
  return (
    <div className="space-y-6">
      <PageHeader title="Project Creator" description="Turn an idea into reviewed project documents, then organize specialist AI teams around an approved plan."
        actions={<Link href="/projects/new" className={buttonVariants()}><Plus className="size-4" /> New project</Link>} />
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Project summary">
        {[
          { label: "Total projects", value: items.length, icon: FolderKanban },
          { label: "Planning", value: items.filter((p) => p.status === "planning").length, icon: Sparkles },
          { label: "Documents", value: items.reduce((n, p) => n + p.documents.length, 0), icon: FileText },
          { label: "Configured agents", value: items.reduce((n, p) => n + p.planning_agent_ids.length + p.teams.reduce((t, team) => t + team.agent_ids.length, 0), 0), icon: Bot },
        ].map((stat) => (
          <div key={stat.label} className="rounded-xl border bg-card p-4">
            <div className="flex items-center justify-between text-sm text-muted-foreground"><span>{stat.label}</span><stat.icon className="size-4" /></div>
            <p className="mt-3 text-3xl font-semibold tracking-tight tabular-nums">{stat.value}</p>
          </div>
        ))}
      </section>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative min-w-0 flex-1"><Input aria-label="Search projects" placeholder="Search projects and ideas…" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
        <p className="text-xs text-muted-foreground">{filtered.length} project{filtered.length === 1 ? "" : "s"}</p>
      </div>
      {projects.isPending ? <LoadingRows rows={4} /> : projects.isError ? <ErrorState error={projects.error} onRetry={() => projects.refetch()} /> : filtered.length === 0 ? (
        <EmptyState title={search ? "No matching projects" : "Start with an idea"} description={search ? "Try a different search term." : "Choose one or two planning agents. They will work in parallel to draft documents you can review and revise."}
          action={!search && <Link href="/projects/new" className={buttonVariants()}><Plus className="size-4" /> Create your first project</Link>} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {filtered.map((project) => (
            <Link key={project.id} href={`/projects/${project.id}`} className="group flex min-w-0 flex-col rounded-xl border bg-card p-5 transition-colors hover:border-primary/40 hover:bg-accent/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <div className="flex items-start gap-3">
                <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><FolderKanban className="size-5" /></div>
                <div className="min-w-0 flex-1"><h2 className="truncate font-semibold">{project.name}</h2><p className="mt-1 line-clamp-2 min-h-10 text-sm text-muted-foreground">{project.description || project.idea}</p></div>
                <ArrowRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
              </div>
              <div className="mt-5 flex flex-wrap items-center gap-2">
                <span className={cn("rounded-full border px-2.5 py-1 text-xs font-medium", statusTone[project.status] ?? statusTone.archived)}>{statusLabel[project.status] ?? project.status}</span>
                {project.planning_runs.some((r) => ["queued", "running"].includes(r.status)) && <span className="flex items-center gap-1 text-xs text-muted-foreground"><Clock3 className="size-3.5" /> Agents working</span>}
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2 border-t pt-4 text-xs text-muted-foreground">
                <div><p className="text-base font-semibold text-foreground">{project.documents.length}</p><p>Documents</p></div>
                <div><p className="text-base font-semibold text-foreground">{project.teams.length}</p><p>Teams</p></div>
                <div><p className="text-base font-semibold text-foreground">{project.planning_agent_ids.length}</p><p>Planners</p></div>
              </div>
            </Link>
          ))}
        </div>
      )}
      <div className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground"><Sparkles className="mr-2 inline size-4" /> Planning runs use your existing published agents and model providers. Review documents before treating a plan as approved.</div>
    </div>
  )
}
