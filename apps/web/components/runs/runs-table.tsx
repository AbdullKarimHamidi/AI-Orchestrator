import Link from "next/link"

import { DemoBadge, StatusBadge } from "@/components/common/status-badge"
import { EmptyState } from "@/components/common/states"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { fmtMs, fmtRelative, fmtUsd } from "@/lib/format"
import type { Run } from "@/lib/schemas"

export function RunsTable({ runs, hideAgent, emptyText = "No runs yet." }: { runs: Run[]; hideAgent?: boolean; emptyText?: string }) {
  if (runs.length === 0) return <EmptyState title={emptyText} />
  return (
    <div className="rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Run</TableHead>
            {!hideAgent && <TableHead>Agent / workflow</TableHead>}
            <TableHead>Status</TableHead>
            <TableHead>Version</TableHead>
            <TableHead className="text-right">Duration</TableHead>
            <TableHead className="text-right">Tokens</TableHead>
            <TableHead className="text-right">Cost</TableHead>
            <TableHead>Created</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((r) => (
            <TableRow key={r.id}>
              <TableCell>
                <Link href={`/runs/${r.id}`} className="font-mono text-xs hover:underline">{r.id.slice(0, 14)}…</Link>
                {r.demo && <span className="ml-2"><DemoBadge /></span>}
              </TableCell>
              {!hideAgent && (
                <TableCell className="text-sm">
                  {r.agent_name}
                  {r.kind === "workflow" && <span className="ml-1.5 rounded border px-1 text-[10px] text-muted-foreground">workflow</span>}
                  {r.eval_run_id && <span className="ml-1.5 rounded border px-1 text-[10px] text-muted-foreground">eval</span>}
                </TableCell>
              )}
              <TableCell><StatusBadge status={r.status} /></TableCell>
              <TableCell className="text-sm">{r.source === "draft" ? "draft" : `v${r.agent_version}`}</TableCell>
              <TableCell className="text-right text-sm tabular-nums">{fmtMs(r.duration_ms)}</TableCell>
              <TableCell className="text-right text-sm tabular-nums">{r.usage.input_tokens + r.usage.output_tokens}</TableCell>
              <TableCell className="text-right text-sm tabular-nums">{fmtUsd(r.usage.cost_usd)}</TableCell>
              <TableCell className="text-sm text-muted-foreground">{fmtRelative(r.created_at)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
