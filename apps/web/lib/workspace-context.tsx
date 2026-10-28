"use client"

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react"

import { getWorkspaceId, setWorkspaceId } from "@/lib/api-client"
import type { Me, Role } from "@/lib/schemas"

interface WorkspaceCtx {
  me: Me
  workspaceId: string
  workspaceName: string
  role: Role
  switchWorkspace: (id: string) => void
}

const Ctx = createContext<WorkspaceCtx | null>(null)

/** Workspace selection is UI state only. The server re-verifies membership and derives the
 * role on every request; `role` here is used to hide controls, never to grant access. */
export function WorkspaceProvider({ me, children, onSwitch }: { me: Me; children: ReactNode; onSwitch?: () => void }) {
  const initial = (() => {
    const stored = getWorkspaceId()
    const m = me.memberships.find((x) => x.workspace_id === stored) ?? me.memberships[0]
    if (m) setWorkspaceId(m.workspace_id)
    return m?.workspace_id ?? ""
  })()
  const [workspaceId, setWs] = useState(initial)
  const switchWorkspace = useCallback(
    (id: string) => {
      setWorkspaceId(id)
      setWs(id)
      onSwitch?.()
    },
    [onSwitch],
  )
  const value = useMemo(() => {
    const m = me.memberships.find((x) => x.workspace_id === workspaceId) ?? me.memberships[0]
    return { me, workspaceId: m?.workspace_id ?? "", workspaceName: m?.workspace_name ?? "", role: (m?.role ?? "viewer") as Role, switchWorkspace }
  }, [me, workspaceId, switchWorkspace])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useWorkspaceCtx(): WorkspaceCtx {
  const v = useContext(Ctx)
  if (!v) throw new Error("useWorkspaceCtx must be used inside WorkspaceProvider")
  return v
}

const PERMS: Record<Role, string[]> = {
  viewer: ["read"],
  operator: ["read", "runs:create", "runs:cancel"],
  developer: ["read", "runs:create", "runs:cancel", "agents:write", "agents:publish"],
  administrator: ["read", "runs:create", "runs:cancel", "agents:write", "agents:publish", "providers:write", "members:manage", "workspace:update", "audit:read", "api_keys:manage"],
  owner: ["read", "runs:create", "runs:cancel", "agents:write", "agents:publish", "providers:write", "members:manage", "workspace:update", "audit:read", "api_keys:manage"],
}

/** Display-only mirror of the backend RBAC matrix (apps/api/app/services/rbac.py). */
export function can(role: Role, perm: string): boolean {
  return PERMS[role]?.includes(perm) ?? false
}
