"use client"

import { cn } from "cn"
import { Download } from "lucide-react"
import Link from "next/link"
import { toast } from "sonner"

import { ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useBilling, useBillingMutations, useStatements } from "@/hooks/use-modules"
import { errorMessage } from "@/lib/api-client"
import { fmtDate, fmtInt, fmtUsd } from "@/lib/format"
import type { Statement } from "@/lib/schemas"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

function Meter({ label, used, limit, unit }: { label: string; used: number; limit: number | null; unit: string }) {
  const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0
  return (
    <div>
      <div className="flex justify-between text-sm"><span>{label}</span><span className="tabular-nums">{fmtInt(used)} {limit ? `/ ${fmtInt(limit)}` : ""} {unit}</span></div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={limit ?? used} aria-valuenow={used}>
        <div className={cn("h-full", pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-amber-500" : "bg-primary")} style={{ width: limit ? `${pct}%` : "0%" }} />
      </div>
      {!limit && <p className="mt-1 text-xs text-muted-foreground">No limit on this plan</p>}
    </div>
  )
}

function downloadCsv(rows: Statement[], workspace: string) {
  const header = ["period", "runs", "model_calls", "input_tokens", "output_tokens", "model_cost_usd", "plan_fee_usd", "total_usd"]
  const lines = [header.join(","), ...rows.map((r) => [r.period, r.runs, r.model_calls, r.input_tokens, r.output_tokens, r.model_cost_usd, r.plan_fee_usd, r.total_usd].join(","))]
  const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }))
  const a = document.createElement("a")
  a.href = url
  a.download = `${workspace.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-statements.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export default function BillingPage() {
  const { workspaceId, workspaceName, role } = useWorkspaceCtx()
  const billing = useBilling(workspaceId)
  const statements = useStatements(workspaceId, 12)
  const { changePlan } = useBillingMutations(workspaceId)
  const editable = can(role, "workspace:update")
  if (billing.isPending) return <LoadingRows />
  if (billing.isError) return <ErrorState error={billing.error} onRetry={() => billing.refetch()} />
  const b = billing.data
  return (
    <div>
      <PageHeader title="Billing and plan" description="The plan sets the seats and monthly runs this workspace may use; the API enforces both. Statements combine the plan fee with model spend recorded for every call. No payment processor is connected: statements are for internal chargeback." />
      <div className="mb-6 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{b.plan.name} plan</CardTitle>
            <CardDescription>{b.plan.description} Current period {fmtDate(b.period_start)} – {fmtDate(b.period_end)} (UTC).</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5 sm:grid-cols-2">
            <Meter label="Runs this month" used={b.runs_used} limit={b.plan.runs_per_month} unit="runs" />
            <Meter label="Seats (members + pending invites)" used={b.seats_used} limit={b.plan.seats} unit="seats" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>This month</CardTitle></CardHeader>
          <CardContent className="space-y-1.5 text-sm">
            <div className="flex justify-between"><span>Plan fee</span><span className="tabular-nums">{fmtUsd(b.plan.price_usd)}</span></div>
            <div className="flex justify-between"><span>Model spend</span><span className="tabular-nums">{fmtUsd(b.model_cost_usd)}</span></div>
            <div className="flex justify-between border-t pt-1.5 font-medium"><span>Total so far</span><span className="tabular-nums">{fmtUsd(b.plan.price_usd + b.model_cost_usd)}</span></div>
            <p className="pt-2 text-xs text-muted-foreground">
              Spend cap: {b.monthly_budget_usd === null ? "none" : fmtUsd(b.monthly_budget_usd)} · <Link href="/settings/workspace" className="underline">change budget</Link>
            </p>
          </CardContent>
        </Card>
      </div>

      <h2 className="mb-2 font-medium">Plans</h2>
      <div className="mb-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {b.plans.map((p) => {
          const current = p.id === b.plan.id
          return (
            <div key={p.id} className={cn("flex flex-col rounded-xl border p-4", current && "border-primary ring-1 ring-primary")}>
              <div className="flex items-baseline justify-between"><span className="font-medium">{p.name}</span><span className="text-lg font-semibold tabular-nums">{p.price_usd ? `$${p.price_usd}` : "$0"}<span className="text-xs font-normal text-muted-foreground">/mo</span></span></div>
              <p className="mt-1 flex-1 text-sm text-muted-foreground">{p.description}</p>
              <ul className="mt-3 space-y-0.5 text-sm">
                <li>{p.seats ? `${p.seats} seats` : "Unlimited seats"}</li>
                <li>{p.runs_per_month ? `${fmtInt(p.runs_per_month)} runs / month` : "Unlimited runs"}</li>
              </ul>
              <Button className="mt-4" variant={current ? "secondary" : "outline"} disabled={current || !editable || changePlan.isPending}
                onClick={async () => {
                  try {
                    await changePlan.mutateAsync(p.id)
                    toast.success(`Switched to ${p.name}`)
                  } catch (x) {
                    toast.error(errorMessage(x))
                  }
                }}>
                {current ? "Current plan" : editable ? `Switch to ${p.name}` : "Admins can change plans"}
              </Button>
            </div>
          )
        })}
      </div>

      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-medium">Monthly statements</h2>
        {statements.data && <Button size="sm" variant="outline" onClick={() => downloadCsv(statements.data, workspaceName)}><Download className="size-4" /> Download CSV</Button>}
      </div>
      {statements.isPending ? <LoadingRows /> : statements.isError ? <ErrorState error={statements.error} /> : (
        <div className="rounded-xl border">
          <Table>
            <TableHeader><TableRow><TableHead>Month</TableHead><TableHead className="text-right">Runs</TableHead><TableHead className="text-right">Model calls</TableHead><TableHead className="text-right">Tokens in / out</TableHead><TableHead className="text-right">Model spend</TableHead><TableHead className="text-right">Plan fee</TableHead><TableHead className="text-right">Total</TableHead></TableRow></TableHeader>
            <TableBody>
              {statements.data.map((s) => (
                <TableRow key={s.period}>
                  <TableCell className="font-medium">{s.period}{s.current && <span className="ml-2 text-xs font-normal text-muted-foreground">in progress</span>}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmtInt(s.runs)}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmtInt(s.model_calls)}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmtInt(s.input_tokens)} / {fmtInt(s.output_tokens)}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmtUsd(s.model_cost_usd)}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmtUsd(s.plan_fee_usd)}</TableCell>
                  <TableCell className="text-right font-medium tabular-nums">{fmtUsd(s.total_usd)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
