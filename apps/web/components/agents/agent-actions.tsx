"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAgentMutations } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"
import type { Agent } from "@/lib/schemas"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

type DialogKind = null | "publish" | "clone" | "retire" | "delete"

export function AgentActions({ agent }: { agent: Agent }) {
  const { workspaceId, role } = useWorkspaceCtx()
  const m = useAgentMutations(workspaceId)
  const router = useRouter()
  const [open, setOpen] = useState<DialogKind>(null)
  const [text, setText] = useState("")
  const [busy, setBusy] = useState(false)
  const canPublish = can(role, "agents:publish")
  const canWrite = can(role, "agents:write")
  const retired = agent.status === "retired"

  async function run(fn: () => Promise<unknown>, ok: string) {
    setBusy(true)
    try {
      await fn()
      toast.success(ok)
      setOpen(null)
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      {canPublish && !retired && (
        <Button onClick={() => { setText(""); setOpen("publish") }} disabled={!agent.draft_dirty && agent.published_version === agent.latest_version && agent.published_version !== null}>
          Publish{agent.latest_version ? ` v${agent.latest_version + 1}` : " v1"}
        </Button>
      )}
      {canPublish && agent.status === "published" && (
        <Button variant="outline" disabled={busy} onClick={() => run(() => m.transition.mutateAsync({ id: agent.id, action: "pause" }), "Agent paused")}>Pause</Button>
      )}
      {canPublish && agent.status === "paused" && (
        <Button variant="outline" disabled={busy} onClick={() => run(() => m.transition.mutateAsync({ id: agent.id, action: "resume" }), "Agent resumed")}>Resume</Button>
      )}
      {canWrite && <Button variant="outline" onClick={() => { setText(`${agent.name} (copy)`); setOpen("clone") }}>Clone</Button>}
      {canPublish && !retired && <Button variant="outline" onClick={() => setOpen("retire")}>Retire</Button>}
      {canWrite && <Button variant="destructive" onClick={() => setOpen("delete")}>Delete</Button>}

      <Dialog open={open !== null} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent>
          {open === "publish" && (
            <>
              <DialogHeader>
                <DialogTitle>Publish a new version</DialogTitle>
                <DialogDescription>The current draft becomes an immutable version. Production runs switch to it immediately.</DialogDescription>
              </DialogHeader>
              <div className="space-y-1.5">
                <Label htmlFor="pub-note">Release note (optional)</Label>
                <Input id="pub-note" value={text} onChange={(e) => setText(e.target.value)} maxLength={500} />
              </div>
              <DialogFooter>
                <Button variant="ghost" onClick={() => setOpen(null)}>Cancel</Button>
                <Button disabled={busy} onClick={() => run(() => m.publish.mutateAsync({ id: agent.id, note: text }), "Version published")}>Publish</Button>
              </DialogFooter>
            </>
          )}
          {open === "clone" && (
            <>
              <DialogHeader>
                <DialogTitle>Clone agent</DialogTitle>
                <DialogDescription>Copies the current draft into a new draft agent. Versions and runs are not copied.</DialogDescription>
              </DialogHeader>
              <div className="space-y-1.5">
                <Label htmlFor="clone-name">New name</Label>
                <Input id="clone-name" value={text} onChange={(e) => setText(e.target.value)} />
              </div>
              <DialogFooter>
                <Button variant="ghost" onClick={() => setOpen(null)}>Cancel</Button>
                <Button
                  disabled={busy || !text.trim()}
                  onClick={() => run(async () => { const c = await m.clone.mutateAsync({ id: agent.id, name: text.trim() }); router.push(`/agents/${c.id}`) }, "Agent cloned")}
                >
                  Clone
                </Button>
              </DialogFooter>
            </>
          )}
          {open === "retire" && (
            <>
              <DialogHeader>
                <DialogTitle>Retire {agent.name}?</DialogTitle>
                <DialogDescription>Retired agents reject new runs and can no longer be edited or published. History is kept. This cannot be undone.</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="ghost" onClick={() => setOpen(null)}>Cancel</Button>
                <Button variant="destructive" disabled={busy} onClick={() => run(() => m.transition.mutateAsync({ id: agent.id, action: "retire" }), "Agent retired")}>Retire</Button>
              </DialogFooter>
            </>
          )}
          {open === "delete" && (
            <>
              <DialogHeader>
                <DialogTitle>Delete {agent.name}?</DialogTitle>
                <DialogDescription>The agent disappears from lists and its name becomes available. Versions and run history are retained for audit.</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="ghost" onClick={() => setOpen(null)}>Cancel</Button>
                <Button variant="destructive" disabled={busy} onClick={() => run(async () => { await m.remove.mutateAsync(agent.id); router.push("/agents") }, "Agent deleted")}>Delete</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
