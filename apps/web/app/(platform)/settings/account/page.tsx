"use client"

import { useState } from "react"
import { toast } from "sonner"

import { PageHeader } from "@/components/common/states"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAccountMutations } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"
import { useWorkspaceCtx } from "@/lib/workspace-context"

export default function AccountPage() {
  const { me, switchWorkspace } = useWorkspaceCtx()
  const m = useAccountMutations()
  const [current, setCurrent] = useState("")
  const [next, setNext] = useState("")
  const [confirm, setConfirm] = useState("")
  const [pwErr, setPwErr] = useState<string | null>(null)
  const [wsName, setWsName] = useState("")

  async function changePassword(e: React.FormEvent) {
    e.preventDefault()
    setPwErr(null)
    if (next.length < 12) return setPwErr("Use at least 12 characters")
    if (next !== confirm) return setPwErr("The new passwords do not match")
    try {
      await m.changePassword.mutateAsync({ current_password: current, new_password: next })
      setCurrent("")
      setNext("")
      setConfirm("")
      toast.success("Password changed. Your other sessions were signed out.")
    } catch (x) {
      setPwErr(errorMessage(x))
    }
  }

  async function createWorkspace(e: React.FormEvent) {
    e.preventDefault()
    try {
      const updated = await m.createWorkspace.mutateAsync(wsName)
      const created = updated.memberships.find((x) => x.workspace_name === wsName && x.role === "owner")
      setWsName("")
      toast.success("Workspace created")
      if (created) switchWorkspace(created.workspace_id)
    } catch (x) {
      toast.error(errorMessage(x))
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      <PageHeader title="Account" description={`Signed in as ${me.user.email}`} />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Change password</CardTitle>
          <CardDescription>All your other sessions are signed out after the change.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={changePassword} className="space-y-3">
            {pwErr && <Alert variant="destructive" role="alert"><AlertDescription>{pwErr}</AlertDescription></Alert>}
            <div className="space-y-1.5">
              <Label htmlFor="pw-current">Current password</Label>
              <Input id="pw-current" type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pw-new">New password</Label>
              <Input id="pw-new" type="password" autoComplete="new-password" required minLength={12} value={next} onChange={(e) => setNext(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pw-confirm">Repeat new password</Label>
              <Input id="pw-confirm" type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </div>
            <Button type="submit" disabled={m.changePassword.isPending}>Change password</Button>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">New workspace</CardTitle>
          <CardDescription>Workspaces keep agents, providers, runs and members fully separate, for example one per client or project.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={createWorkspace} className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="ws-new">Name</Label>
              <Input id="ws-new" required maxLength={120} value={wsName} onChange={(e) => setWsName(e.target.value)} className="w-64" />
            </div>
            <Button type="submit" disabled={m.createWorkspace.isPending}>Create workspace</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
