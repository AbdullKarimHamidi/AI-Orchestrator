"use client"

import { ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useRoles } from "@/hooks/use-api"
import { useWorkspaceCtx } from "@/lib/workspace-context"

export default function RolesPage() {
  const { workspaceId } = useWorkspaceCtx()
  const roles = useRoles(workspaceId)
  if (roles.isPending) return <LoadingRows />
  if (roles.isError) return <ErrorState error={roles.error} />
  const perms = Array.from(new Set(roles.data.flatMap((r) => r.permissions))).sort()
  return (
    <div>
      <PageHeader title="Roles" description="The built-in permission matrix, read live from the API. FastAPI enforces it on every protected endpoint." />
      <div className="overflow-x-auto rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Permission</TableHead>
              {roles.data.map((r) => <TableHead key={r.role} className="text-center capitalize">{r.role}</TableHead>)}
            </TableRow>
          </TableHeader>
          <TableBody>
            {perms.map((p) => (
              <TableRow key={p}>
                <TableCell className="font-mono text-xs">{p}</TableCell>
                {roles.data.map((r) => (
                  <TableCell key={r.role} className="text-center">
                    {r.permissions.includes(p) ? <span aria-label="granted">✓</span> : <span aria-label="not granted" className="text-muted-foreground">–</span>}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
