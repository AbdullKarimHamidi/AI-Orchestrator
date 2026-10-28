"use client"

import Link from "next/link"
import { useState } from "react"
import { toast } from "sonner"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { useAgents } from "@/hooks/use-api"
import { useMemories, useMemoryMutations, useMemoryScopes } from "@/hooks/use-modules"
import { errorMessage } from "@/lib/api-client"
import { fmtDate, fmtRelative } from "@/lib/format"
import type { Memory } from "@/lib/schemas"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

const selectCls = "h-9 w-full rounded-md border bg-background px-2 text-sm"

function AddMemory({ agentId, agents }: { agentId: string; agents: { id: string; name: string }[] }) {
  const { workspaceId } = useWorkspaceCtx()
  const m = useMemoryMutations(workspaceId)
  const [agent, setAgent] = useState(agentId)
  const [scope, setScope] = useState("global")
  const [content, setContent] = useState("")
  const [tags, setTags] = useState("")
  const [ttl, setTtl] = useState("")
  const target = agent || agentId

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    try {
      await m.create.mutateAsync({ agent_id: target, scope: scope.trim() || "global", content: content.trim(), tags: tags.split(",").map((t) => t.trim()).filter(Boolean), ttl_days: ttl ? Number(ttl) : null })
      setContent("")
      setTags("")
      toast.success("Memory saved")
    } catch (x) {
      toast.error(errorMessage(x))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Add a memory</CardTitle>
        <CardDescription>A fact the agent should know in future runs. Scope &quot;global&quot; applies to every run; any other scope applies only to runs whose input has the same <code>memory_scope</code> (for example an end-user id).</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="mem-agent">Agent</Label>
            <select id="mem-agent" className={selectCls} value={target} onChange={(e) => setAgent(e.target.value)} required>
              <option value="">Select an agent…</option>
              {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="mem-scope">Scope</Label>
            <Input id="mem-scope" value={scope} onChange={(e) => setScope(e.target.value)} placeholder="global or user-123" pattern="[A-Za-z0-9_.:@\-]{1,120}" />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="mem-content">Memory</Label>
            <Textarea id="mem-content" rows={3} value={content} onChange={(e) => setContent(e.target.value)} placeholder="The customer prefers answers in Dari and is on the Business plan." required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="mem-tags">Tags (comma separated)</Label>
            <Input id="mem-tags" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="preference, account" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="mem-ttl">Delete after (days)</Label>
            <Input id="mem-ttl" type="number" min={1} max={3650} value={ttl} onChange={(e) => setTtl(e.target.value)} placeholder="keep forever" />
          </div>
          <div className="sm:col-span-2">
            <Button type="submit" disabled={!target || !content.trim() || m.create.isPending}>Save memory</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

function MemoryRow({ m, agentName, canWrite }: { m: Memory; agentName: string; canWrite: boolean }) {
  const { workspaceId } = useWorkspaceCtx()
  const mut = useMemoryMutations(workspaceId)
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(m.content)
  return (
    <TableRow>
      <TableCell className="max-w-xl">
        {editing ? (
          <div className="space-y-2">
            <Label htmlFor={`edit-${m.id}`} className="sr-only">Memory text</Label>
            <Textarea id={`edit-${m.id}`} rows={3} value={text} onChange={(e) => setText(e.target.value)} />
            <div className="flex gap-2">
              <Button size="sm" onClick={async () => {
                try {
                  await mut.update.mutateAsync({ id: m.id, content: text.trim() })
                  setEditing(false)
                  toast.success("Memory updated")
                } catch (x) {
                  toast.error(errorMessage(x))
                }
              }}>Save</Button>
              <Button size="sm" variant="ghost" onClick={() => { setText(m.content); setEditing(false) }}>Cancel</Button>
            </div>
          </div>
        ) : (
          <>
            <p className="text-sm whitespace-pre-wrap">{m.content}</p>
            <div className="mt-1 flex flex-wrap gap-1">
              {m.tags.map((t) => <span key={t} className="rounded bg-muted px-1.5 text-[11px]">{t}</span>)}
              {m.source === "run" && m.run_id && <Link href={`/runs/${m.run_id}`} className="text-[11px] text-muted-foreground underline-offset-4 hover:underline">from run</Link>}
            </div>
          </>
        )}
      </TableCell>
      <TableCell className="text-sm">{agentName}</TableCell>
      <TableCell className="font-mono text-xs">{m.scope}</TableCell>
      <TableCell className="text-sm text-muted-foreground">{fmtRelative(m.created_at)}{m.expires_at && <span className="block text-xs">expires {fmtDate(m.expires_at)}</span>}</TableCell>
      <TableCell className="text-right">
        {canWrite && !editing && (
          <div className="flex justify-end gap-1">
            <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>Edit</Button>
            <Button size="sm" variant="ghost" className="text-destructive" onClick={async () => {
              try {
                await mut.remove.mutateAsync(m.id)
                toast.success("Memory deleted")
              } catch (x) {
                toast.error(errorMessage(x))
              }
            }}>Delete</Button>
          </div>
        )}
      </TableCell>
    </TableRow>
  )
}

export default function MemoryPage() {
  const { workspaceId, role } = useWorkspaceCtx()
  const agents = useAgents(workspaceId)
  const [agentId, setAgentId] = useState("")
  const [scope, setScope] = useState("")
  const [q, setQ] = useState("")
  const memories = useMemories(workspaceId, { agent_id: agentId || undefined, scope: scope || undefined, q: q || undefined })
  const scopes = useMemoryScopes(workspaceId, agentId || undefined)
  const mut = useMemoryMutations(workspaceId)
  const canWrite = can(role, "agents:write")
  const agentList = (agents.data?.items ?? []).map((a) => ({ id: a.id, name: a.name, enabled: a.draft.memory.enabled }))
  const nameOf = (id: string) => agentList.find((a) => a.id === id)?.name ?? id

  return (
    <div>
      <PageHeader title="Memory" description="Long-term memory for agents. Agents with memory enabled (Agent → Edit → Memory) receive the newest memories of the run's scope in their prompt, and can save each conversation automatically." />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-4">
          {canWrite && <AddMemory agentId={agentId} agents={agentList} />}
          <div className="flex flex-wrap gap-2">
            <label htmlFor="mf-agent" className="sr-only">Filter by agent</label>
            <select id="mf-agent" className="h-9 rounded-md border bg-background px-2 text-sm" value={agentId} onChange={(e) => { setAgentId(e.target.value); setScope("") }}>
              <option value="">All agents</option>
              {agentList.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
            <label htmlFor="mf-scope" className="sr-only">Filter by scope</label>
            <Input id="mf-scope" placeholder="Scope" value={scope} onChange={(e) => setScope(e.target.value)} className="w-40" />
            <label htmlFor="mf-q" className="sr-only">Search memories</label>
            <Input id="mf-q" placeholder="Search text…" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-xs" />
          </div>
          {memories.isPending ? <LoadingRows /> : memories.isError ? <ErrorState error={memories.error} onRetry={() => memories.refetch()} /> : memories.data.items.length === 0 ? (
            <EmptyState title="No memories" description={agentId || scope || q ? "Nothing matches these filters." : "Add one above, or enable \"Save conversations\" on an agent."} />
          ) : (
            <div className="rounded-xl border">
              <Table>
                <TableHeader><TableRow><TableHead>Memory</TableHead><TableHead>Agent</TableHead><TableHead>Scope</TableHead><TableHead>Created</TableHead><TableHead className="sr-only">Actions</TableHead></TableRow></TableHeader>
                <TableBody>{memories.data.items.map((m) => <MemoryRow key={m.id} m={m} agentName={nameOf(m.agent_id)} canWrite={canWrite} />)}</TableBody>
              </Table>
            </div>
          )}
        </div>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Scopes</CardTitle>
              <CardDescription>Deletion requests: &quot;Forget&quot; removes every memory in a scope, e.g. when an end user asks to be forgotten.</CardDescription>
            </CardHeader>
            <CardContent>
              {scopes.data?.length ? (
                <ul className="space-y-2 text-sm">
                  {scopes.data.map((s) => (
                    <li key={`${s.agent_id}:${s.scope}`} className="flex items-center gap-2">
                      <button type="button" className="min-w-0 flex-1 text-left" onClick={() => { setAgentId(s.agent_id); setScope(s.scope) }}>
                        <span className="block truncate font-mono text-xs">{s.scope}</span>
                        <span className="block truncate text-xs text-muted-foreground">{nameOf(s.agent_id)} · {s.count} · {fmtRelative(s.last_at)}</span>
                      </button>
                      {canWrite && (
                        <Button size="sm" variant="outline" onClick={async () => {
                          if (!window.confirm(`Delete all ${s.count} memories in scope "${s.scope}" of ${nameOf(s.agent_id)}?`)) return
                          try {
                            const r = await mut.forget.mutateAsync({ agent_id: s.agent_id, scope: s.scope })
                            toast.success(`${r.deleted} memories deleted`)
                          } catch (x) {
                            toast.error(errorMessage(x))
                          }
                        }}>Forget</Button>
                      )}
                    </li>
                  ))}
                </ul>
              ) : <p className="text-sm text-muted-foreground">No memories stored yet.</p>}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Agents using memory</CardTitle></CardHeader>
            <CardContent>
              <ul className="space-y-1 text-sm">
                {agentList.map((a) => (
                  <li key={a.id} className="flex justify-between gap-2">
                    <Link href={`/agents/${a.id}/edit`} className="truncate underline-offset-4 hover:underline">{a.name}</Link>
                    <span className={a.enabled ? "text-emerald-600" : "text-muted-foreground"}>{a.enabled ? "enabled" : "off"}</span>
                  </li>
                ))}
                {agentList.length === 0 && <li className="text-muted-foreground">No agents yet.</li>}
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
