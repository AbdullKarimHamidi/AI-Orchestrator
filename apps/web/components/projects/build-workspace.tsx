"use client"

import { useMutation } from "@tanstack/react-query"
import { CheckCircle2, Eye, FileCode2, FilePlus2, Hammer, Maximize2, RefreshCw, Save, Trash2, XCircle } from "lucide-react"
import { useMemo, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api-client"
import { buildPreview } from "@/lib/project-preview"
import { type Project, projectSchema } from "@/lib/schemas/projects"
import { cn } from "cn"

const ACTIVE = ["queued", "running", "waiting_for_approval"]
const statusText: Record<string, string> = { queued: "Waiting for a worker", running: "Agents are working", completed: "Finished", failed: "Failed", cancelled: "Cancelled", timed_out: "Timed out", waiting_for_approval: "Needs approval" }

function errorText(e: unknown): string {
  if (!e) return ""
  if (typeof e === "object" && "message" in e) return String((e as { message: unknown }).message)
  return typeof e === "string" ? e : JSON.stringify(e)
}

/** Start build rounds, read the reviewers' verdict, preview the result and edit its files. */
export function BuildWorkspace({ project, onChanged, onShowFlow }: { project: Project; onChanged: () => Promise<void> | void; onShowFlow: () => void }) {
  const [instructions, setInstructions] = useState("")
  const [error, setError] = useState("")
  const [selected, setSelected] = useState<string | null>(null)
  const [draft, setDraft] = useState<string | null>(null)
  const [newPath, setNewPath] = useState("")
  const [view, setView] = useState<"preview" | "code">("preview")
  const [reload, setReload] = useState(0)
  const files = project.files
  const running = project.build_runs.find((b) => ACTIVE.includes(b.status))
  const last = project.build_runs[project.build_runs.length - 1]
  const hasTeam = project.teams.some((t) => t.agent_ids.length > 0)
  const preview = useMemo(() => buildPreview(files), [files])
  const current = files.find((f) => f.path === selected) ?? files.find((f) => f.path === "web/index.html") ?? files[0]
  const content = draft ?? current?.content ?? ""

  const start = useMutation({
    mutationFn: () => api.post(`/projects/${project.id}/build`, null, { instructions: instructions.trim() }),
    onSuccess: async () => { setError(""); setInstructions(""); toast.success("Build started. The teams are working in parallel."); await onChanged() },
    onError: (e) => setError(e instanceof Error ? e.message : "Could not start the build"),
  })
  const saveFile = useMutation({
    mutationFn: (v: { path: string; content: string }) => api.put(`/projects/${project.id}/files`, projectSchema, v),
    onSuccess: async (_, v) => { setError(""); setDraft(null); setSelected(v.path); setNewPath(""); toast.success(`Saved ${v.path}`); await onChanged() },
    onError: (e) => setError(e instanceof Error ? e.message : "Could not save the file"),
  })
  const deleteFile = useMutation({
    mutationFn: (path: string) => api.delete(`/projects/${project.id}/files?path=${encodeURIComponent(path)}`),
    onSuccess: async (_, path) => { setDraft(null); setSelected(null); toast.success(`Deleted ${path}`); await onChanged() },
    onError: (e) => setError(e instanceof Error ? e.message : "Could not delete the file"),
  })
  function openPreviewTab() {
    if (!preview) return
    const url = URL.createObjectURL(new Blob([preview], { type: "text/html" }))
    window.open(url, "_blank", "noopener")
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  }

  return (
    <div className="space-y-5">
      {error && <p role="alert" className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">{error}</p>}
      <div className="grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
        <div className="space-y-5">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Hammer className="size-5" /> {files.length ? "Request changes" : "Build the project"}</CardTitle>
              <CardDescription>{files.length ? "Describe what to change. The main agent gets your request with the current files and hands the work to the teams." : "The main agent takes the approved plan, gives tasks to the team coordinators, and the teams build in parallel. Plan reviewers check the result."}</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              <Label htmlFor="build-instructions" className="sr-only">Instructions</Label>
              <Textarea id="build-instructions" rows={4} maxLength={20000} value={instructions} onChange={(e) => setInstructions(e.target.value)}
                placeholder={files.length ? "For example: make the header blue, add a login page, store habits in the database…" : "Optional: anything to focus on in this first build round."} />
              <Button className="w-full" onClick={() => start.mutate()} disabled={start.isPending || !!running || !hasTeam || !project.director_agent_id}>
                <Hammer className="size-4" /> {running ? "Build in progress…" : start.isPending ? "Starting…" : files.length ? "Apply changes" : "Start build"}
              </Button>
              {(!hasTeam || !project.director_agent_id) && <p className="text-xs text-muted-foreground">Set up the build team first: a main agent and at least one team with agents.</p>}
              <Button variant="outline" className="w-full" onClick={onShowFlow}>Watch the agents as nodes</Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Build rounds</CardTitle><CardDescription>Each round, reviewers compare the work with the plan.</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              {project.build_runs.length === 0 && <p className="text-sm text-muted-foreground">No build rounds yet.</p>}
              {project.build_runs.slice().reverse().map((b) => (
                <div key={b.run_id} className="rounded-lg border p-3 text-sm">
                  <div className="flex items-center justify-between gap-2"><p className="font-medium">Round {b.round}</p>
                    <span className={cn("rounded-full border px-2 py-0.5 text-[11px]", ACTIVE.includes(b.status) && "animate-pulse border-sky-400 text-sky-600", b.status === "failed" && "border-destructive text-destructive")}>{statusText[b.status] ?? b.status}</span></div>
                  {b.instructions && <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">“{b.instructions}”</p>}
                  {b.status === "completed" && <p className="mt-2 text-xs">{b.files_written.length} file(s) written</p>}
                  {b.verdict && <p className={cn("mt-2 flex items-center gap-1 text-xs font-medium", b.verdict === "complete" ? "text-emerald-600" : "text-amber-600")}>{b.verdict === "complete" ? <CheckCircle2 className="size-3.5" /> : <XCircle className="size-3.5" />} Reviewers: {b.verdict === "complete" ? "matches the plan" : "work still missing"}</p>}
                  {b.review && <details className="mt-2 text-xs"><summary className="cursor-pointer text-muted-foreground">Reviewer report</summary><p className="mt-1 whitespace-pre-wrap">{b.review}</p></details>}
                  {b.error != null && <p className="mt-2 text-xs text-destructive">{errorText(b.error)}</p>}
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        <Card className="min-w-0">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div><CardTitle>Project</CardTitle><CardDescription>{files.length} file(s){last?.status === "completed" ? ` · updated in round ${last.round}` : ""}</CardDescription></div>
              <div className="flex flex-wrap gap-2">
                <div className="inline-flex rounded-lg border p-0.5" role="tablist">
                  <button role="tab" aria-selected={view === "preview"} className={cn("rounded-md px-3 py-1 text-sm", view === "preview" && "bg-muted font-medium")} onClick={() => setView("preview")}><Eye className="mr-1 inline size-3.5" />Preview</button>
                  <button role="tab" aria-selected={view === "code"} className={cn("rounded-md px-3 py-1 text-sm", view === "code" && "bg-muted font-medium")} onClick={() => setView("code")}><FileCode2 className="mr-1 inline size-3.5" />Files</button>
                </div>
                {view === "preview" && preview && <><Button size="sm" variant="outline" onClick={() => setReload((n) => n + 1)}><RefreshCw className="size-3.5" /> Reload</Button><Button size="sm" variant="outline" onClick={openPreviewTab}><Maximize2 className="size-3.5" /> Open</Button></>}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {view === "preview" ? (
              preview ? (
                <iframe key={reload} title="Project preview" srcDoc={preview} sandbox="allow-scripts allow-forms allow-modals allow-popups" className="h-[640px] w-full rounded-lg border bg-white" />
              ) : (
                <div className="flex h-[400px] flex-col items-center justify-center gap-2 rounded-lg border border-dashed text-center text-sm text-muted-foreground">
                  <Eye className="size-6" />
                  {running ? "The teams are building. The preview appears when the UI team delivers web/index.html." : files.length ? "No HTML page yet. Ask the UI team for web/index.html to get a preview." : "Start a build to see the project here."}
                </div>
              )
            ) : (
              <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
                <div className="space-y-2">
                  <div className="max-h-[520px] space-y-1 overflow-auto">
                    {files.length === 0 && <p className="text-xs text-muted-foreground">No files yet.</p>}
                    {files.map((f) => <button key={f.path} type="button" onClick={() => { setSelected(f.path); setDraft(null) }} className={cn("block w-full truncate rounded-md px-2 py-1.5 text-left font-mono text-xs", current?.path === f.path ? "bg-primary/10 text-primary" : "hover:bg-accent/50")} title={f.path}>{f.path}</button>)}
                  </div>
                  <form className="space-y-1.5 border-t pt-2" onSubmit={(e) => { e.preventDefault(); if (newPath.trim()) saveFile.mutate({ path: newPath.trim(), content: "" }) }}>
                    <Label htmlFor="new-file" className="text-xs">New file</Label>
                    <div className="flex gap-1"><Input id="new-file" className="h-8 font-mono text-xs" placeholder="web/about.html" value={newPath} onChange={(e) => setNewPath(e.target.value)} /><Button size="icon" variant="outline" className="size-8" aria-label="Add file" disabled={!newPath.trim()}><FilePlus2 className="size-3.5" /></Button></div>
                  </form>
                </div>
                {current ? (
                  <div className="min-w-0 space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2"><p className="font-mono text-xs text-muted-foreground">{current.path} · {current.updated_by === "agents" ? `written by agents${current.round ? ` in round ${current.round}` : ""}` : "edited by you"}</p>
                      <div className="flex gap-2"><Button size="sm" onClick={() => saveFile.mutate({ path: current.path, content })} disabled={draft === null || saveFile.isPending}><Save className="size-3.5" /> Save</Button><Button size="sm" variant="outline" onClick={() => deleteFile.mutate(current.path)} disabled={deleteFile.isPending}><Trash2 className="size-3.5" /> Delete</Button></div></div>
                    <Label htmlFor="file-editor" className="sr-only">File content</Label>
                    <Textarea id="file-editor" spellCheck={false} value={content} onChange={(e) => setDraft(e.target.value)} rows={26} className="font-mono text-xs leading-5" />
                  </div>
                ) : <p className="text-sm text-muted-foreground">Select a file to edit it.</p>}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
