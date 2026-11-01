"use client"

import { useMutation } from "@tanstack/react-query"
import { Code2, Crown, Database, LayoutTemplate, Plus, Save, ShieldCheck, Trash2, Users } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api-client"
import { type Project, projectSchema, type ProjectTeam } from "@/lib/schemas/projects"
import { cn } from "cn"

type AgentLite = { id: string; name: string }
type Kind = ProjectTeam["kind"]

const selectCls = "h-9 w-full rounded-md border bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
export const KIND_META: Record<Kind, { label: string; icon: typeof Code2; hint: string }> = {
  ui: { label: "UI / frontend", icon: LayoutTemplate, hint: "Pages, components, styling and the live preview (web/)." },
  backend: { label: "Backend", icon: Code2, hint: "API, business logic, auth and integrations (backend/)." },
  database: { label: "Database", icon: Database, hint: "Schema, migrations, indexes and seed data (database/)." },
  other: { label: "Other", icon: Users, hint: "Any other specialists: testing, docs, DevOps…" },
}

function newTeam(kind: Kind, n: number): ProjectTeam {
  return { id: `${kind}_${Date.now().toString(36)}_${n}`, name: KIND_META[kind].label.split(" /")[0], kind,
    responsibility: KIND_META[kind].hint, agent_ids: [], parallelism: 5, lead_agent_id: null }
}

/** Who builds the project: the main agent, a task coordinator and agents per team, and plan reviewers. */
export function BuildTeamEditor({ project, agents, onSaved }: { project: Project; agents: AgentLite[]; onSaved: () => Promise<void> | void }) {
  const [director, setDirector] = useState(project.director_agent_id ?? project.supervisor_agent_ids[0] ?? project.planning_agent_ids[0] ?? "")
  const [reviewers, setReviewers] = useState<string[]>(project.reviewer_agent_ids)
  const [teams, setTeams] = useState<ProjectTeam[]>(project.teams.length ? project.teams : [newTeam("ui", 0), newTeam("backend", 1), newTeam("database", 2)])
  const [error, setError] = useState("")
  const save = useMutation({
    mutationFn: () => api.patch(`/projects/${project.id}`, projectSchema, {
      revision: project.revision, director_agent_id: director, reviewer_agent_ids: reviewers,
      teams: teams.map((t) => ({ ...t, name: t.name.trim() || KIND_META[t.kind].label, responsibility: t.responsibility.trim() || KIND_META[t.kind].hint, lead_agent_id: t.lead_agent_id || null, parallelism: Math.max(1, Math.min(100, t.parallelism)) })),
    }),
    onSuccess: async () => { setError(""); toast.success("Build team saved"); await onSaved() },
    onError: (e) => setError(e instanceof Error ? e.message : "Could not save the build team"),
  })
  const update = (id: string, patch: Partial<ProjectTeam>) => setTeams((xs) => xs.map((t) => (t.id === id ? { ...t, ...patch } : t)))
  const name = (id: string | null | undefined) => agents.find((a) => a.id === id)?.name
  const ready = !!director && teams.some((t) => t.agent_ids.length > 0)

  return (
    <div className="space-y-5">
      {error && <p role="alert" className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">{error}</p>}
      {agents.length === 0 && <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">Publish some agents first. Every role below is filled by a published agent.</p>}
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Crown className="size-5 text-violet-500" /> Main agent</CardTitle><CardDescription>Owns the plan. Splits it into tasks for the team coordinators, sends fixes back, and delivers the project.</CardDescription></CardHeader>
          <CardContent><Label htmlFor="build-director" className="sr-only">Main agent</Label>
            <select id="build-director" className={selectCls} value={director} onChange={(e) => setDirector(e.target.value)}>
              <option value="">Choose the main agent…</option>
              {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck className="size-5 text-emerald-500" /> Plan reviewers</CardTitle><CardDescription>Check whether the work matches the plan. The main agent sends them the results, and the first reviewer gives the final verdict.</CardDescription></CardHeader>
          <CardContent className="grid gap-2 sm:grid-cols-2">
            {agents.map((a) => <label key={a.id} className="flex items-center gap-2 rounded-md border p-2 text-sm"><input type="checkbox" className="size-4 accent-primary" checked={reviewers.includes(a.id)} disabled={!reviewers.includes(a.id) && reviewers.length >= 5}
              onChange={() => setReviewers((xs) => (xs.includes(a.id) ? xs.filter((x) => x !== a.id) : [...xs, a.id]))} /><span className="truncate">{a.name}</span></label>)}
          </CardContent>
        </Card>
      </div>

      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div><h3 className="font-semibold">Teams</h3><p className="text-sm text-muted-foreground">Teams work at the same time. A task coordinator takes the main agent&apos;s tasks and hands them to the team&apos;s agents.</p></div>
          <div className="flex flex-wrap gap-2">{(Object.keys(KIND_META) as Kind[]).map((k) => { const Icon = KIND_META[k].icon; return <Button key={k} type="button" size="sm" variant="outline" onClick={() => setTeams((xs) => [...xs, newTeam(k, xs.length)])}><Plus className="size-3.5" /><Icon className="size-3.5" /> {KIND_META[k].label}</Button> })}</div>
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          {teams.map((team) => {
            const Icon = KIND_META[team.kind].icon
            return (
              <Card key={team.id} className={cn(team.agent_ids.length === 0 && "border-dashed")}>
                <CardHeader className="pb-3"><div className="flex items-center justify-between gap-2"><CardTitle className="flex items-center gap-2 text-base"><Icon className="size-4" /> {team.name || KIND_META[team.kind].label}</CardTitle><Button type="button" variant="ghost" size="icon" aria-label={`Remove ${team.name} team`} onClick={() => setTeams((xs) => xs.filter((t) => t.id !== team.id))}><Trash2 className="size-4" /></Button></div></CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid gap-3 sm:grid-cols-[1fr_150px]">
                    <div className="space-y-1.5"><Label htmlFor={`${team.id}-name`}>Team name</Label><Input id={`${team.id}-name`} value={team.name} maxLength={120} onChange={(e) => update(team.id, { name: e.target.value })} /></div>
                    <div className="space-y-1.5"><Label htmlFor={`${team.id}-kind`}>Works on</Label><select id={`${team.id}-kind`} className={selectCls} value={team.kind} onChange={(e) => update(team.id, { kind: e.target.value as Kind })}>{(Object.keys(KIND_META) as Kind[]).map((k) => <option key={k} value={k}>{KIND_META[k].label}</option>)}</select></div>
                  </div>
                  <div className="space-y-1.5"><Label htmlFor={`${team.id}-resp`}>Responsibilities</Label><Textarea id={`${team.id}-resp`} rows={2} maxLength={1000} value={team.responsibility} onChange={(e) => update(team.id, { responsibility: e.target.value })} /></div>
                  <div className="grid gap-3 sm:grid-cols-[1fr_150px]">
                    <div className="space-y-1.5"><Label htmlFor={`${team.id}-lead`}>Task coordinator</Label><select id={`${team.id}-lead`} className={selectCls} value={team.lead_agent_id ?? ""} onChange={(e) => update(team.id, { lead_agent_id: e.target.value || null })}><option value="">{team.agent_ids.length > 1 ? `Main agent coordinates (${name(director) ?? "not chosen"})` : "None, the main agent assigns directly"}</option>{agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></div>
                    <div className="space-y-1.5"><Label htmlFor={`${team.id}-par`}>Parallel tasks</Label><Input id={`${team.id}-par`} type="number" min={1} max={100} value={team.parallelism} onChange={(e) => update(team.id, { parallelism: Number(e.target.value) || 1 })} /></div>
                  </div>
                  <fieldset className="space-y-1.5"><legend className="text-sm font-medium">Agents in this team</legend>
                    <div className="grid gap-1.5 sm:grid-cols-2">{agents.map((a) => <label key={a.id} className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-primary" checked={team.agent_ids.includes(a.id)} onChange={() => update(team.id, { agent_ids: team.agent_ids.includes(a.id) ? team.agent_ids.filter((x) => x !== a.id) : [...team.agent_ids, a.id] })} /><span className="truncate">{a.name}</span></label>)}</div>
                    {team.agent_ids.length === 0 && <p className="text-xs text-muted-foreground">Pick at least one agent, or remove this team. Empty teams are skipped.</p>}
                  </fieldset>
                </CardContent>
              </Card>
            )
          })}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => save.mutate()} disabled={save.isPending || !director}><Save className="size-4" /> {save.isPending ? "Saving…" : "Save build team"}</Button>
        {!ready && <p className="text-sm text-muted-foreground">Choose a main agent and put at least one agent in a team.</p>}
      </div>
    </div>
  )
}
