"use client"

import { Copy } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useInvitations, useTeamMutations } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"
import { fmtDate } from "@/lib/format"
import { roleSchema, type Role } from "@/lib/schemas"

export async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success("Copied to clipboard")
  } catch {
    toast.error("Copy failed; select the text and copy it manually")
  }
}

/** Single-use invitation links. No email service is needed: the link is shown once to the
 * inviter, who sends it however the team communicates. */
export function InvitePanel({ workspaceId }: { workspaceId: string }) {
  const invitations = useInvitations(workspaceId)
  const t = useTeamMutations(workspaceId)
  const [email, setEmail] = useState("")
  const [role, setRole] = useState<Role>("developer")
  const [err, setErr] = useState<string | null>(null)
  const [link, setLink] = useState<{ email: string; url: string } | null>(null)

  async function invite(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    try {
      const inv = await t.invite.mutateAsync({ email, role })
      setLink({ email: inv.email, url: inv.url })
      setEmail("")
    } catch (x) {
      setErr(errorMessage(x))
    }
  }

  return (
    <section className="mb-6 rounded-xl border p-4" aria-labelledby="invite-h">
      <h2 id="invite-h" className="mb-1 text-sm font-medium">Invite a teammate</h2>
      <p className="mb-3 text-xs text-muted-foreground">Creates a single-use link for that email address. New people register with it; people who already have an account sign in and accept it. Links expire after 7 days by default.</p>
      {err && <Alert variant="destructive" className="mb-3" role="alert"><AlertDescription>{err}</AlertDescription></Alert>}
      <form onSubmit={invite} className="flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="inv-email">Email</Label>
          <Input id="inv-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="w-72" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="inv-role">Role</Label>
          <select id="inv-role" value={role} onChange={(e) => setRole(e.target.value as Role)} className="h-9 rounded-md border bg-background px-2 text-sm">
            {roleSchema.options.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <Button type="submit" disabled={t.invite.isPending}>Create invitation link</Button>
      </form>
      {link && (
        <div className="mt-4 rounded-lg border border-emerald-500/50 bg-emerald-500/5 p-3" role="status">
          <p className="mb-2 text-sm">Send this link to <strong>{link.email}</strong>. It is shown only once.</p>
          <div className="flex gap-2">
            <Input readOnly value={link.url} aria-label="Invitation link" className="font-mono text-xs" onFocus={(e) => e.target.select()} />
            <Button type="button" variant="outline" onClick={() => copyText(link.url)} aria-label="Copy invitation link"><Copy className="size-4" /></Button>
          </div>
        </div>
      )}
      {invitations.data && invitations.data.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-2 text-xs font-medium text-muted-foreground uppercase">Pending invitations</h3>
          <Table>
            <TableHeader><TableRow><TableHead>Email</TableHead><TableHead>Role</TableHead><TableHead>Expires</TableHead><TableHead><span className="sr-only">Actions</span></TableHead></TableRow></TableHeader>
            <TableBody>
              {invitations.data.map((i) => (
                <TableRow key={i.id}>
                  <TableCell className="text-sm">{i.email}</TableCell>
                  <TableCell className="text-sm">{i.role}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{fmtDate(i.expires_at)}</TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="ghost" className="text-destructive" onClick={async () => {
                      try {
                        await t.revokeInvite.mutateAsync(i.id)
                        toast.success("Invitation revoked")
                      } catch (x) {
                        toast.error(errorMessage(x))
                      }
                    }}>Revoke</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  )
}
