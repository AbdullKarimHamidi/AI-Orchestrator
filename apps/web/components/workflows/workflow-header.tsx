"use client"

import { cn } from "cn"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useState } from "react"
import { toast } from "sonner"

import { PageHeader } from "@/components/common/states"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useWorkflowMutations } from "@/hooks/use-modules"
import { errorMessage } from "@/lib/api-client"
import type { Workflow } from "@/lib/schemas"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

export function WorkflowHeader({ workflow: w }: { workflow: Workflow }) {
  const { workspaceId, role } = useWorkspaceCtx()
  const m = useWorkflowMutations(workspaceId)
  const pathname = usePathname()
  const router = useRouter()
  const [note, setNote] = useState("")
  const base = `/workflows/${w.id}`
  const tabs = [{ href: base, label: "Overview" }, { href: `${base}/edit`, label: "Edit" }, { href: `${base}/runs`, label: "Runs" }]
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn()
      toast.success(ok)
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }
  return (
    <>
      <PageHeader
        title={w.name}
        description={w.description || undefined}
        actions={
          <>
            <StatusBadge status={w.status} />
            <span className="text-sm text-muted-foreground">{w.published_version ? `published v${w.published_version}` : "never published"}{w.draft_dirty && w.published_version ? " · draft has changes" : ""}</span>
            {can(role, "agents:publish") && w.status !== "archived" && (
              <form className="flex gap-1" onSubmit={(e) => { e.preventDefault(); act(() => m.publish.mutateAsync({ id: w.id, note }), "Published a new version").then(() => setNote("")) }}>
                <label htmlFor="wf-note" className="sr-only">Version note</label>
                <Input id="wf-note" placeholder="Version note" value={note} onChange={(e) => setNote(e.target.value)} className="h-8 w-40" />
                <Button size="sm" type="submit" disabled={m.publish.isPending || (!w.draft_dirty && !!w.published_version)}>Publish</Button>
              </form>
            )}
            {can(role, "agents:publish") && (
              <Button size="sm" variant="outline" onClick={() => act(() => m.archive.mutateAsync({ id: w.id, archived: w.status !== "archived" }), w.status === "archived" ? "Restored" : "Archived")}>
                {w.status === "archived" ? "Restore" : "Archive"}
              </Button>
            )}
            {can(role, "agents:write") && (
              <Button size="sm" variant="ghost" className="text-destructive" onClick={() => {
                if (!window.confirm(`Delete workflow "${w.name}"? Its run history is kept.`)) return
                act(async () => { await m.remove.mutateAsync(w.id); router.push("/workflows") }, "Workflow deleted")
              }}>Delete</Button>
            )}
          </>
        }
      />
      <nav aria-label="Workflow sections" className="mb-5 flex gap-1 border-b">
        {tabs.map((t) => (
          <Link key={t.href} href={t.href} aria-current={pathname === t.href ? "page" : undefined}
            className={cn("-mb-px border-b-2 px-3 py-2 text-sm", pathname === t.href ? "border-primary font-medium" : "border-transparent text-muted-foreground hover:text-foreground")}>
            {t.label}
          </Link>
        ))}
      </nav>
    </>
  )
}
