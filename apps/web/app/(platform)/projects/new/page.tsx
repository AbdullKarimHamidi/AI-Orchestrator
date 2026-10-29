"use client"

import { useMutation, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Bot, Plus, Trash2 } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { toast } from "sonner"

import { PageHeader } from "@/components/common/states"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useAgents } from "@/hooks/use-api"
import { api } from "@/lib/api-client"
import { projectSchema } from "@/lib/schemas/projects"
import { useWorkspaceCtx } from "@/lib/workspace-context"
import { cn } from "cn"

type TeamDraft = { id: string; name: string; responsibility: string; agent_ids: string[]; parallelism: number }
const published = (agents: { id: string; name: string; status: string; published_version: number | null }[]) => agents.filter((a) => a.status === "published" && a.published_version)

export default function NewProjectPage() {
  const router = useRouter()
  const qc = useQueryClient()
  const { workspaceId } = useWorkspaceCtx()
  const agentsQuery = useAgents(workspaceId)
  const agents = published(agentsQuery.data?.items ?? [])
  const [name, setName] = useState("")
  const [idea, setIdea] = useState("")
  const [description, setDescription] = useState("")
  const [planners, setPlanners] = useState<string[]>([])
  const [supervisors, setSupervisors] = useState<string[]>([])
  const [teams, setTeams] = useState<TeamDraft[]>([])
  const [error, setError] = useState("")
  const create = useMutation({
    mutationFn: () => api.post("/projects", projectSchema, { name: name.trim(), idea: idea.trim(), description: description.trim(),
      planning_agent_ids: planners, supervisor_agent_ids: supervisors,
      teams: teams.map((t) => ({ ...t, agent_ids: t.agent_ids, parallelism: Math.max(1, Math.min(100, t.parallelism)) })) }),
    onSuccess: async (project) => { await qc.invalidateQueries({ queryKey: ["projects", workspaceId] }); toast.success("Project created"); router.push(`/projects/${project.id}`) },
    onError: (e) => setError(e instanceof Error ? e.message : "Could not create project"),
  })
  function toggle(list: string[], setter: (v: string[]) => void, id: string, max: number) {
    setter(list.includes(id) ? list.filter((x) => x !== id) : list.length < max ? [...list, id] : list)
  }
  function updateTeam(id: string, patch: Partial<TeamDraft>) {
    setTeams((current) => current.map((t) => t.id === id ? { ...t, ...patch } : t))
  }
  return (
    <div className="space-y-6">
      <Link href="/projects" className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "w-fit")}><ArrowLeft className="size-4" /> All projects</Link>
      <PageHeader title="Create a project" description="Describe the outcome, choose your planning agents, and optionally preconfigure specialist teams." />
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
      <form className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]" onSubmit={(e) => { e.preventDefault(); setError(""); create.mutate() }}>
        <div className="space-y-5">
          <Card>
            <CardHeader><CardTitle>Project brief</CardTitle><CardDescription>Be specific about what should be built, constraints, and how success will be measured.</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5"><Label htmlFor="project-name">Project name</Label><Input id="project-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required placeholder="e.g. Customer support workspace" /></div>
              <div className="space-y-1.5"><Label htmlFor="project-idea">Your idea and requirements</Label><Textarea id="project-idea" value={idea} onChange={(e) => setIdea(e.target.value)} required minLength={10} maxLength={20000} rows={9} placeholder="What should the project do? Who uses it? Which technologies or constraints matter? What does done mean?" /><p className="text-xs text-muted-foreground">{idea.length}/20,000 characters</p></div>
              <div className="space-y-1.5"><Label htmlFor="project-description">Short description (optional)</Label><Textarea id="project-description" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} maxLength={4000} placeholder="A short summary shown in the project list." /></div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Bot className="size-5" /> Planning agents</CardTitle><CardDescription>Select one or two published agents. They receive the brief and work concurrently to create project plans.</CardDescription></CardHeader>
            <CardContent className="space-y-2">
              {agentsQuery.isPending ? <p className="text-sm text-muted-foreground">Loading agents…</p> : agents.length === 0 ? <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">No published agents found. Create an agent, configure a provider, and publish it before planning.</p> : agents.map((agent) => (
                <label key={agent.id} className={cn("flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors", planners.includes(agent.id) ? "border-primary/50 bg-primary/5" : "hover:bg-accent/40")}>
                  <input type="checkbox" checked={planners.includes(agent.id)} onChange={() => toggle(planners, setPlanners, agent.id, 2)} disabled={!planners.includes(agent.id) && planners.length >= 2} className="size-4 accent-primary" />
                  <span className="min-w-0 flex-1"><span className="block text-sm font-medium">{agent.name}</span><span className="text-xs text-muted-foreground">Published v{agent.published_version}</span></span>
                  {planners.includes(agent.id) && <span className="text-xs font-medium text-primary">Selected</span>}
                </label>
              ))}
              <p className="text-xs text-muted-foreground">{planners.length}/2 selected</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Supervisor agents (optional)</CardTitle><CardDescription>Choose up to three published agents to reserve for plan compliance, coordination, and quality reviews. Their full autonomous feedback loop is a later orchestration phase.</CardDescription></CardHeader>
            <CardContent className="grid gap-2 sm:grid-cols-2">
              {agents.map((agent) => <label key={agent.id} className="flex items-center gap-2 rounded-md border p-2.5 text-sm"><input type="checkbox" checked={supervisors.includes(agent.id)} onChange={() => toggle(supervisors, setSupervisors, agent.id, 3)} disabled={!supervisors.includes(agent.id) && supervisors.length >= 3} className="size-4 accent-primary" /><span className="truncate">{agent.name}</span></label>)}
              {agents.length === 0 && <p className="text-sm text-muted-foreground">Publish agents to select supervisors.</p>}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Specialist teams (optional)</CardTitle><CardDescription>Set team roles now or configure them after reviewing the plan. Team size is not fixed.</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              {teams.map((team, index) => <div key={team.id} className="space-y-3 rounded-lg border p-4">
                <div className="flex items-center justify-between"><p className="text-sm font-semibold">Team {index + 1}</p><Button type="button" variant="ghost" size="icon" aria-label="Remove team" onClick={() => setTeams((xs) => xs.filter((t) => t.id !== team.id))}><Trash2 className="size-4" /></Button></div>
                <div className="grid gap-3 sm:grid-cols-2"><div className="space-y-1.5"><Label>Team name</Label><Input required value={team.name} onChange={(e) => updateTeam(team.id, { name: e.target.value })} placeholder="UI/UX team" /></div><div className="space-y-1.5"><Label>Parallelism limit</Label><Input type="number" min={1} max={100} value={team.parallelism} onChange={(e) => updateTeam(team.id, { parallelism: Number(e.target.value) || 1 })} /></div></div>
                <div className="space-y-1.5"><Label>Responsibilities</Label><Textarea required rows={2} value={team.responsibility} onChange={(e) => updateTeam(team.id, { responsibility: e.target.value })} placeholder="Design responsive pages, accessibility, and component states…" /></div>
                <div className="space-y-2"><Label>Assigned agents</Label><div className="grid gap-2 sm:grid-cols-2">{agents.map((agent) => <label key={agent.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={team.agent_ids.includes(agent.id)} onChange={() => updateTeam(team.id, { agent_ids: team.agent_ids.includes(agent.id) ? team.agent_ids.filter((id) => id !== agent.id) : [...team.agent_ids, agent.id] })} className="size-4 accent-primary" /><span className="truncate">{agent.name}</span></label>)}</div></div>
              </div>)}
              <Button type="button" variant="outline" onClick={() => setTeams((xs) => [...xs, { id: `team_${Date.now()}_${xs.length}`, name: "", responsibility: "", agent_ids: [], parallelism: 5 }])}><Plus className="size-4" /> Add specialist team</Button>
            </CardContent>
          </Card>
        </div>
        <aside className="space-y-4">
          <Card className="xl:sticky xl:top-20">
            <CardHeader><CardTitle>Before you create</CardTitle></CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="flex items-start gap-3"><span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold">1</span><p><strong>Save the brief</strong><span className="mt-1 block text-muted-foreground">Your idea and team configuration are stored in MongoDB.</span></p></div>
              <div className="flex items-start gap-3"><span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold">2</span><p><strong>Generate plans</strong><span className="mt-1 block text-muted-foreground">Selected planners run through the existing background queue.</span></p></div>
              <div className="flex items-start gap-3"><span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold">3</span><p><strong>Review before execution</strong><span className="mt-1 block text-muted-foreground">Edit the documents and add feedback before approving the plan.</span></p></div>
              <Button className="w-full" type="submit" disabled={create.isPending || !name.trim() || idea.trim().length < 10 || planners.length < 1}>{create.isPending ? "Creating project…" : "Create project"}<ArrowLeft className="size-4 rotate-180" /></Button>
              <p className="text-xs text-muted-foreground">Only published agents in this workspace can be assigned.</p>
            </CardContent>
          </Card>
        </aside>
      </form>
    </div>
  )
}
