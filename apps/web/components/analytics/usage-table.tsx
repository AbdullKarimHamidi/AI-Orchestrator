import { EmptyState } from "@/components/common/states"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { fmtInt, fmtMs, fmtUsd } from "@/lib/format"
import type { Provider } from "@/lib/schemas"
import type { z } from "zod"
import type { usageRowSchema } from "@/lib/schemas"

export function UsageTable({ rows, providers }: { rows: z.infer<typeof usageRowSchema>[]; providers: Provider[] }) {
  if (rows.length === 0) return <EmptyState title="No provider calls in this window" />
  const name = (id: string) => providers.find((p) => p.id === id)?.name ?? id
  return (
    <div className="rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Provider</TableHead><TableHead>Model</TableHead>
            <TableHead className="text-right">Calls</TableHead><TableHead className="text-right">Errors</TableHead>
            <TableHead className="text-right">Tokens in / out</TableHead><TableHead className="text-right">Avg latency</TableHead>
            <TableHead className="text-right">Cost</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.provider_id + r.model}>
              <TableCell>{name(r.provider_id)}</TableCell>
              <TableCell className="font-mono text-xs">{r.model}</TableCell>
              <TableCell className="text-right tabular-nums">{fmtInt(r.calls)}</TableCell>
              <TableCell className="text-right tabular-nums">{fmtInt(r.errors)}</TableCell>
              <TableCell className="text-right tabular-nums">{fmtInt(r.input_tokens)} / {fmtInt(r.output_tokens)}</TableCell>
              <TableCell className="text-right tabular-nums">{fmtMs(r.avg_latency_ms === null ? null : Math.round(r.avg_latency_ms))}</TableCell>
              <TableCell className="text-right tabular-nums">{fmtUsd(r.cost_usd)}{r.unpriced > 0 && <span className="ml-1 text-xs text-muted-foreground" title="Calls without a configured price are counted at $0">({r.unpriced} unpriced)</span>}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
