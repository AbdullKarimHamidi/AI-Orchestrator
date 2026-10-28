"use client"

import { useState } from "react"
import { toast } from "sonner"

import { ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { InvitePanel } from "@/components/security/invite-panel"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useMembers, useWorkspaceMutations } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"
import { fmtDate } from "@/lib/format"
import { roleSchema, type Role } from "@/lib/schemas"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

export default function UsersPage() {
  const { workspaceId, role, me } = useWorkspaceCtx()
  const userId = me.user.id
  const members = useMembers(workspaceId)
  const m = useWorkspaceMutations(workspaceId)
  const [email, setEmail] = useState("")
  const [newRole, setNewRole] = useState<Role>("developer")
  const [err, setErr] = useState<string | null>(null)
  const manage = can(role, "members:manage")

  async function add(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    try {
      await m.addMember.mutateAsync({ email, role: newRole })
      setEmail("")
      toast.success("Member added")
    } catch (x) {
      setErr(errorMessage(x))
    }
  }

  return (
    <div>
      <PageHeader title="Users" description="Workspace members and their roles. Every change is enforced and audited by the API." />
      {manage && <InvitePanel workspaceId={workspaceId} />}
      {manage && (
        <form onSubmit={add} className="mb-6 rounded-xl border p-4">
          <h2 className="mb-1 text-sm font-medium">Add an existing user directly</h2>
          <p className="mb-3 text-xs text-muted-foreground">Skips the invitation step for someone who already has an account on this server.</p>
          {err && <Alert variant="destructive" className="mb-3" role="alert"><AlertDescription>{err}</AlertDescription></Alert>}
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="m-email">Email</Label>
              <Input id="m-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="w-72" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-role">Role</Label>
              <select id="m-role" value={newRole} onChange={(e) => setNewRole(e.target.value as Role)} className="h-9 rounded-md border bg-background px-2 text-sm">
                {roleSchema.options.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <Button type="submit" disabled={m.addMember.isPending}>Add member</Button>
          </div>
        </form>
      )}
      {members.isPending ? <LoadingRows /> : members.isError ? <ErrorState error={members.error} onRetry={() => members.refetch()} /> : (
        <div className="rounded-xl border">
          <Table>
            <TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Email</TableHead><TableHead>Role</TableHead><TableHead>Joined</TableHead>{manage && <TableHead><span className="sr-only">Actions</span></TableHead>}</TableRow></TableHeader>
            <TableBody>
              {members.data.map((u) => (
                <TableRow key={u.user_id}>
                  <TableCell>{u.name}{u.user_id === userId && <span className="ml-1 text-xs text-muted-foreground">(you)</span>}</TableCell>
                  <TableCell className="text-sm">{u.email}</TableCell>
                  <TableCell>
                    {manage && u.user_id !== userId ? (
                      <select aria-label={`Role for ${u.email}`} value={u.role} className="h-8 rounded-md border bg-background px-2 text-sm"
                        onChange={async (e) => {
                          try {
                            await m.setRole.mutateAsync({ user_id: u.user_id, role: e.target.value as Role })
                            toast.success("Role updated")
                          } catch (x) {
                            toast.error(errorMessage(x))
                          }
                        }}>
                        {roleSchema.options.map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    ) : <span className="text-sm">{u.role}</span>}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{fmtDate(u.joined_at)}</TableCell>
                  {manage && (
                    <TableCell className="text-right">
                      {u.user_id !== userId && (
                        <Button size="sm" variant="ghost" className="text-destructive" onClick={async () => {
                          if (!window.confirm(`Remove ${u.email} from this workspace?`)) return
                          try {
                            await m.removeMember.mutateAsync(u.user_id)
                            toast.success("Member removed")
                          } catch (x) {
                            toast.error(errorMessage(x))
                          }
                        }}>Remove</Button>
                      )}
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
