"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Bot, CheckCircle2, Clock3, FileText, Network, Play, Save, Sparkles } from "lucide-react"
import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import { useState } from "react"
import { toast } from "sonner"

import { ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { projectTeamDefinition } from "@/components/workflows/canvas/graph"
import { useWorkflowMutations } from "@/hooks/use-modules"
import { api } from "@/lib/api-client"
import { projectSchema, type ProjectDocument } from "@/lib/schemas/projects"
import { useWorkspaceCtx } from "@/lib/workspace-context"
import { cn } from "cn"

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
  const project = useQuery({
    queryKey: ["project", workspaceId, projectId],
    queryFn: () => api.get(`/projects/${projectId}`, projectSchema),
    enabled: !!workspaceId && !!projectId,
    refetchInterval: (q) => q.state.data?.planning_runs.some((r) => ["queued", "running"].includes(r.status)) ? 2000 : false,
  })
  const data = project.data
  const selected = selectedId === "__new__" ? undefined : data?.documents.find((d) => d.id === selectedId) ?? data?.documents[0]
  const editorTitle = title ?? (selectedId === "__new__" ? "" : selected?.title ?? "")
  const editorContent = content ?? (selectedId === "__new__" ? "" : selected?.content ?? "")
  const editorFeedback = feedback ?? (selectedId === "__new__" ? "" : selected?.feedback ?? "")
  async function invalidate() {
    await Promise.all([qc.invalidateQueries({ queryKey: ["project", workspaceId, projectId] }), qc.invalidateQueries({ queryKey: ["projects", workspaceId] })])
  }
  const startPlan = useMutation({
    mutationFn: () => api.post(`/projects/${projectId}/plan`, null, { feedback }),
    onSuccess: async () => { toast.success("Planning agents queued"); setError(""); await invalidate() },
    onError: (e) => setError(e instanceof Error ? e.message : "Could not start planning"),
  })
  const workflows = useWorkflowMutations(workspaceId)
  const router = useRouter()
  const buildTeam = useMutation({
    mutationFn: async () => {
      const definition = data ? projectTeamDefinition(data) : null
      if (!definition) throw new Error("Add at least one supervisor or planning agent and one team agent first.")
      return workflows.create.mutateAsync({ name: `${data!.name} team`.slice(0, 120), description: `Agent team for project ${data!.name}`, definition })
    },
    onSuccess: (w) => { toast.success("Team workflow created. Check the agents, then publish it."); router.push(`/workflows/${w.id}/edit`) },
    onError: (e) => setError(e instanceof Error ? e.message : "Could not build the team workflow"),
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
            <CardContent className="space-y-3"><Textarea rows={4} value={editorFeedback} onChange={(e) => setFeedback(e.target.value)} maxLength={20000} placeholder="For example: split the backend into services, add role-based access, change the database model, or simplify the UI…" /><Button onClick={() => startPlan.mutate()} disabled={startPlan.isPending}><Play className="size-4" /> {startPlan.isPending ? "Queueing planners…" : data.documents.length ? "Revise plan with feedback" : "Generate project plan"}</Button></CardContent>
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
            {data.planning_runs.length === 0 ? <p className="text-sm text-muted-foreground">No planning runs yet.</p> : data.planning_runs.slice().reverse().map((run) => <div key={run.run_id} className="rounded-lg border p-3"><div className="flex items-start justify-between gap-2"><p className="text-sm font-medium">{run.agent_name}</p><span className="rounded-full border px-2 py-0.5 text-[11px]">{runStatusLabel[run.status] ?? run.status}</span></div><p className="mt-1 text-xs text-muted-foreground">{run.purpose}</p>{run.error != null && <p className="mt-2 text-xs text-destructive">{String(typeof run.error === "object" ? JSON.stringify(run.error) : run.error)}</p>}{run.document_id && <p className="mt-2 text-xs text-emerald-600">Document created</p>}</div>)}
          </CardContent></Card>
          <Card><CardHeader><CardTitle>Team configuration</CardTitle><CardDescription>Set up any number of agents after the plan is approved.</CardDescription></CardHeader><CardContent className="space-y-3">{data.teams.length === 0 ? <p className="text-sm text-muted-foreground">No specialist teams configured yet.</p> : data.teams.map((team) => <div key={team.id} className="rounded-lg border p-3"><p className="font-medium">{team.name}</p><p className="mt-1 text-xs text-muted-foreground">{team.responsibility}</p><p className="mt-2 text-xs">{team.agent_ids.length} agents · up to {team.parallelism} parallel tasks</p></div>)}<p className="text-xs text-muted-foreground">Turn this team into a runnable workflow: your supervisor agents lead, each team gets a lead, and the leads delegate tasks to the team&apos;s agents in parallel. You can rearrange it on the canvas before publishing.</p><Button variant="outline" onClick={() => buildTeam.mutate()} disabled={buildTeam.isPending}><Network className="size-4" /> {buildTeam.isPending ? "Building…" : "Build team workflow"}</Button></CardContent></Card>
        </aside>
      </div>
    </div>
  )
}

function PlusIcon() { return <FileText className="size-4" /> }
