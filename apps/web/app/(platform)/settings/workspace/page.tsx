"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useEffect } from "react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import type { z } from "zod"

import { ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useWorkspace, useWorkspaceMutations } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"
import { workspaceFormSchema } from "@/lib/schemas/forms"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

type Values = z.infer<typeof workspaceFormSchema>

export default function WorkspaceSettingsPage() {
  const { workspaceId, role } = useWorkspaceCtx()
  const ws = useWorkspace(workspaceId)
  const { update } = useWorkspaceMutations(workspaceId)
  const editable = can(role, "workspace:update")
  const form = useForm<Values>({ resolver: zodResolver(workspaceFormSchema), defaultValues: { name: "", budget: "" } })
  useEffect(() => {
    if (ws.data) form.reset({ name: ws.data.name, budget: ws.data.monthly_budget_usd == null ? "" : String(ws.data.monthly_budget_usd) })
  }, [ws.data, form])

  if (ws.isPending) return <LoadingRows />
  if (ws.isError) return <ErrorState error={ws.error} />
  const { errors, isSubmitting, isDirty } = form.formState

  return (
    <div className="max-w-xl">
      <PageHeader title="Workspace settings" />
      <Card>
        <CardContent>
          <form noValidate className="space-y-4" onSubmit={form.handleSubmit(async (v) => {
            try {
              await update.mutateAsync({ name: v.name, monthly_budget_usd: v.budget === "" ? null : Number(v.budget) })
              toast.success("Workspace updated")
            } catch (e) {
              toast.error(errorMessage(e))
            }
          })}>
            <fieldset disabled={!editable} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="ws-name">Name</Label>
                <Input id="ws-name" aria-invalid={!!errors.name} {...form.register("name")} />
                {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ws-budget">Monthly budget (USD)</Label>
                <Input id="ws-budget" inputMode="decimal" aria-invalid={!!errors.budget} aria-describedby="ws-budget-help" {...form.register("budget")} />
                <p id="ws-budget-help" className="text-xs text-muted-foreground">When month-to-date spend reaches this amount, new runs are rejected with BUDGET_EXCEEDED. Empty means no workspace limit.</p>
                {errors.budget && <p className="text-xs text-destructive">{errors.budget.message}</p>}
              </div>
            </fieldset>
            {editable ? <Button type="submit" disabled={isSubmitting || !isDirty}>Save</Button> : <p className="text-sm text-muted-foreground">Your role ({role}) cannot change workspace settings.</p>}
          </form>
          <p className="mt-4 font-mono text-xs text-muted-foreground">Workspace ID: {ws.data.id}</p>
        </CardContent>
      </Card>
    </div>
  )
}
