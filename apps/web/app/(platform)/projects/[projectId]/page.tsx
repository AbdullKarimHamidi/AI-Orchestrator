"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Bot, CheckCircle2, Clock3, FileText, Hammer, Network, Play, Save, Sparkles, Users } from "lucide-react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { useState } from "react"
import { toast } from "sonner"

import { ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { type PlanningModel, PlanningModelPicker } from "@/components/projects/planning-model-picker"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { BuildTeamEditor } from "@/components/projects/build-team-editor"
import { BuildWorkspace } from "@/components/projects/build-workspace"
import { TeamFlow } from "@/components/projects/team-flow"
import { useAgents, useProviders } from "@/hooks/use-api"
import { api } from "@/lib/api-client"
import { projectSchema, type ProjectDocument } from "@/lib/schemas/projects"
import { useWorkspaceCtx } from "@/lib/workspace-context"
import { cn } from "cn"

type Tab = "plan" | "team" | "build" | "flow"
const TABS: { id: Tab; label: string; icon: typeof FileText }[] = [
  { id: "plan", label: "Plan", icon: FileText },
  { id: "team", label: "Build team", icon: Users },
  { id: "build", label: "Build & preview", icon: Hammer },
  { id: "flow", label: "Agent flow", icon: Network },
]
const runStatusLabel: Record<string, string> = { queued: "Queued", running: "Running", completed: "Completed", failed: "Failed", cancelled: "Cancelled", timed_out: "Timed out", waiting_for_approval: "Needs approval" }

export default function ProjectDetailPage() {
  const params = useParams<{ projectId: string }>()
  const projectId = params.projectId
  const { workspaceId } = useWorkspaceCtx()
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState("")
  const [title, setTitle] = useState<string | null>(null)
  const [content, setContent] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [error, setError] = useState("")
  const [tab, setTab] = useState<Tab>("plan")
  const agentsQuery = useAgents(workspaceId)
  const allAgents = agentsQuery.data?.items ?? []
  const publishedAgents = allAgents.filter((a) => a.status === "published" && a.published_version).map((a) => ({ id: a.id, name: a.name }))
  const agentNames = Object.fromEntries(allAgents.map((a) => [a.id, a.name]))
  const [planChoice, setPlanChoice] = useState<PlanningModel | null>(null)
  const providers = useProviders(workspaceId).data ?? []
  const project = useQuery({
    queryKey: ["project", workspaceId, projectId],
    queryFn: () => api.get(`/projects/${projectId}`, projectSchema),
    enabled: !!workspaceId && !!projectId,
    refetchInterval: (q) => [...(q.state.data?.planning_runs ?? []), ...(q.state.data?.build_runs ?? [])].some((r) => ["queued", "running"].includes(r.status)) ? 2000 : false,
  })
  const data = project.data
  const selected = selectedId === "__new__" ? undefined : data?.documents.find((d) => d.id === selectedId) ?? data?.documents[0]
  const editorTitle = title ?? (selectedId === "__new__" ? "" : selected?.title ?? "")
  const editorContent = content ?? (selectedId === "__new__" ? "" : selected?.content ?? "")
  const editorFeedback = feedback ?? (selectedId === "__new__" ? "" : selected?.feedback ?? "")
  async function invalidate() {
    await Promise.all([qc.invalidateQueries({ queryKey: ["project", workspaceId, projectId] }), qc.invalidateQueries({ queryKey: ["projects", workspaceId] })])
  }
  const savedModel = data?.planning_model
  const planningModel: PlanningModel = planChoice ?? (savedModel ? { provider_id: savedModel.provider_id, model: savedModel.model } : { provider_id: "", model: "" })
  const startPlan = useMutation({
    // Sends the feedback shown in the box (it starts from the selected document's saved feedback).
    mutationFn: () => api.post(`/projects/${projectId}/plan`, null, {
      feedback: editorFeedback ?? "",
      ...(planChoice?.provider_id ? { planning_model: { provider_id: planChoice.provider_id, model: planChoice.model.trim() } } : {}),
    }),
    onSuccess: async () => { toast.success("Planning agents queued"); setError(""); setPlanChoice(null); await invalidate() },
    onError: (e) => setError(e instanceof Error ? e.message : "Could not start planning"),
  })
  const saveDoc = useMutation({
    mutationFn: (doc: ProjectDocument) => api.patch(`/projects/${projectId}/documents/${doc.id}`, projectSchema, {
      revision: doc.revision, title: editorTitle.trim(), content: editorContent, feedback: editorFeedback, status: doc.status,
    }),
    onSuccess: async () => { toast.success("Document saved"); setError(""); setTitle(null); setContent(null); setFeedback(null); await invalidate() },
    onError: (e) => setError(e instanceof Error ? e.message : "Could not save document"),
  })
  const addDoc = useMutation({
    mutationFn: () => api.post(`/projects/${projectId}/documents`, projectSchema, { title: editorTitle.trim() || "New project document", kind: "specification", content: editorContent, feedback: editorFeedback, status: "draft" }),
    onSuccess: async (updated) => { const doc = updated.documents[updated.documents.length - 1]; setSelectedId(doc?.id ?? ""); setTitle(null); setContent(null); setFeedback(null); toast.success("Document added"); await invalidate() },
    onError: (e) => setError(e instanceof Error ? e.message : "Could not add document"),
  })
  const updateProject = useMutation({
    mutationFn: (status: "ready" | "in_progress") => api.patch(`/projects/${projectId}`, projectSchema, { revision: data!.revision, status }),
    onSuccess: async () => { toast.success("Project status updated"); await invalidate() },
    onError: (e) => setError(e instanceof Error ? e.message : "Could not update project"),
  })
  if (project.isPending) return <LoadingRows rows={6} />
  if (project.isError || !data) return <ErrorState error={project.error} onRetry={() => project.refetch()} />
  const busy = startPlan.isPending || saveDoc.isPending || addDoc.isPending
  return (
    <div className="space-y-6">
      <Link href="/projects" className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "w-fit")}><ArrowLeft className="size-4" /> All projects</Link>
      <PageHeader title={data.name} description={data.description || data.idea.slice(0, 180)}
        actions={<Button variant="outline" onClick={() => updateProject.mutate("ready")} disabled={updateProject.isPending || data.documents.length === 0}><CheckCircle2 className="size-4" /> Mark plan ready</Button>} />
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
      <div role="tablist" aria-label="Project sections" className="inline-flex flex-wrap gap-1 rounded-lg border bg-muted/40 p-1">
        {TABS.map((t) => <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)} className={cn("flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors", tab === t.id ? "bg-background font-medium shadow-sm" : "text-muted-foreground hover:text-foreground")}><t.icon className="size-4" />{t.label}</button>)}
      </div>
      {tab === "team" && <BuildTeamEditor key={data.revision} project={data} agents={publishedAgents} onSaved={async () => { await invalidate(); setTab("build") }} />}
      {tab === "build" && <BuildWorkspace project={data} onChanged={invalidate} onShowFlow={() => setTab("flow")} />}
      {tab === "flow" && <TeamFlow project={data} workspaceId={workspaceId} agentNames={agentNames} />}
      {tab === "plan" && <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Planning agents", value: data.planning_agent_ids.length, icon: Bot },
          { label: "Documents", value: data.documents.length, icon: FileText },
          { label: "Specialist teams", value: data.teams.length, icon: Sparkles },
          { label: "Planning runs", value: data.planning_runs.length, icon: Clock3 },
        ].map((s) => <div key={s.label} className="rounded-xl border bg-card p-4"><div className="flex items-center justify-between text-sm text-muted-foreground">{s.label}<s.icon className="size-4" /></div><p className="mt-2 text-2xl font-semibold tabular-nums">{s.value}</p></div>)}
      </section>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <Card>
            <CardHeader><CardTitle>Project brief</CardTitle><CardDescription>The original idea remains available to every planning iteration.</CardDescription></CardHeader>
            <CardContent><p className="whitespace-pre-wrap text-sm leading-6">{data.idea}</p></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Planning feedback</CardTitle><CardDescription>Tell the planning agents what to change. Their next run receives this feedback and the selected existing documents.</CardDescription></CardHeader>
            <CardContent className="space-y-3"><Textarea rows={4} value={editorFeedback} onChange={(e) => setFeedback(e.target.value)} maxLength={20000} placeholder="For example: split the backend into services, add role-based access, change the database model, or simplify the UI…" /><div className="rounded-lg border p-3"><p className="mb-2 text-sm font-medium">Planning model</p><PlanningModelPicker idPrefix="replan" providers={providers} value={planningModel} onChange={(v) => {
              setPlanChoice(v)
              if (!v.provider_id && savedModel) {
                // Back to each agent's own model: clear the project's saved choice.
                api.patch(`/projects/${projectId}`, projectSchema, { revision: data.revision, clear_planning_model: true }).then(invalidate).catch((e) => setError(e instanceof Error ? e.message : "Could not update the planning model"))
              }
            }} /></div><Button onClick={() => startPlan.mutate()} disabled={startPlan.isPending || (!!planningModel.provider_id && !planningModel.model.trim())}><Play className="size-4" /> {startPlan.isPending ? "Queueing planners…" : data.documents.length ? "Revise plan with feedback" : "Generate project plan"}</Button></CardContent>
          </Card>
          <Card>
            <CardHeader><div className="flex flex-wrap items-center justify-between gap-2"><div><CardTitle>Project documents</CardTitle><CardDescription>Edit generated plans, add your feedback, and approve reviewed documents.</CardDescription></div><Button variant="outline" onClick={() => { setSelectedId("__new__"); setTitle(null); setContent(null); setFeedback(null) }}><FileText className="size-4" /> New document</Button></div></CardHeader>
            <CardContent className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
              <div className="space-y-2">
                {data.documents.length === 0 && <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">Generated documents will appear here.</p>}
                {data.documents.map((doc) => <button key={doc.id} type="button" onClick={() => { setSelectedId(doc.id); setTitle(null); setContent(null); setFeedback(null) }} className={cn("w-full rounded-lg border p-3 text-left transition-colors", selected?.id === doc.id ? "border-primary/50 bg-primary/5" : "hover:bg-accent/40")}><span className="block line-clamp-2 text-sm font-medium">{doc.title}</span><span className="mt-1 block text-xs capitalize text-muted-foreground">{doc.kind.replaceAll("_", " ")} · {doc.status.replaceAll("_", " ")}</span></button>)}
              </div>
              <div className="min-w-0 space-y-3">
                <div className="space-y-1.5"><Label htmlFor="doc-title">Document title</Label><Input id="doc-title" value={editorTitle} onChange={(e) => setTitle(e.target.value)} placeholder="Architecture and implementation plan" /></div>
                <div className="space-y-1.5"><Label htmlFor="doc-content">Document content (Markdown supported)</Label><Textarea id="doc-content" value={editorContent} onChange={(e) => setContent(e.target.value)} rows={16} className="font-mono text-xs leading-5" placeholder="Write or edit the project specification here…" /></div>
                <div className="space-y-1.5"><Label htmlFor="doc-feedback">Feedback for the next revision</Label><Textarea id="doc-feedback" value={editorFeedback} onChange={(e) => setFeedback(e.target.value)} rows={3} placeholder="What should the planning agents change in this document?" /></div>
                <div className="flex flex-wrap gap-2">
                  {selected ? <Button onClick={() => saveDoc.mutate(selected)} disabled={busy || !editorTitle.trim()}><Save className="size-4" /> Save document</Button> : <Button onClick={() => addDoc.mutate()} disabled={busy || !editorTitle.trim()}><PlusIcon /> Save new document</Button>}
                  {selected && <Button variant="outline" onClick={() => api.patch(`/projects/${projectId}/documents/${selected.id}`, projectSchema, { revision: selected.revision, status: selected.status === "approved" ? "in_review" : "approved" }).then(async () => { toast.success(selected.status === "approved" ? "Moved back to review" : "Document approved"); await invalidate() }).catch((e) => setError(e instanceof Error ? e.message : "Could not update document"))}><CheckCircle2 className="size-4" /> {selected.status === "approved" ? "Reopen review" : "Approve document"}</Button>}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
        <aside className="space-y-5">
          <Card><CardHeader><CardTitle>Planning activity</CardTitle><CardDescription>Agent runs are queued independently and execute in the background.</CardDescription></CardHeader><CardContent className="space-y-3">
            {data.planning_runs.length === 0 ? <p className="text-sm text-muted-foreground">No planning runs yet.</p> : data.planning_runs.slice().reverse().map((run) => <div key={run.run_id} className="rounded-lg border p-3"><div className="flex items-start justify-between gap-2"><p className="text-sm font-medium">{run.agent_name}</p><span className="rounded-full border px-2 py-0.5 text-[11px]">{runStatusLabel[run.status] ?? run.status}</span></div><p className="mt-1 text-xs text-muted-foreground">{run.purpose}{run.model ? ` · ${run.model}` : ""}</p>{run.error != null && <p className="mt-2 text-xs text-destructive">{typeof run.error === "object" && run.error && "message" in run.error ? String((run.error as { message: unknown }).message) : String(typeof run.error === "object" ? JSON.stringify(run.error) : run.error)}</p>}{run.document_id && <p className="mt-2 text-xs text-emerald-600">Document created</p>}</div>)}
          </CardContent></Card>
          <Card className="border-primary/40 bg-primary/5"><CardHeader><CardTitle>Turn the plan into a project</CardTitle><CardDescription>Approve the plan documents you want built, choose who builds what, then start the build. The teams work in parallel and you watch the preview.</CardDescription></CardHeader><CardContent className="flex flex-col gap-2"><Button onClick={() => setTab("team")}><Users className="size-4" /> 1. Set up the build team</Button><Button variant="outline" onClick={() => setTab("build")}><Hammer className="size-4" /> 2. Build and preview</Button></CardContent></Card>
        </aside>
      </div>
      </>}
    </div>
  )
}

function PlusIcon() { return <FileText className="size-4" /> }
