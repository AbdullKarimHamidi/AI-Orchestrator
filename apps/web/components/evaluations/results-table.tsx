import Link from "next/link"

import { StatusBadge } from "@/components/common/status-badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { fmtMs } from "@/lib/format"
import type { EvalResult } from "@/lib/schemas"

export function Verdict({ r }: { r: EvalResult | null }) {
  if (!r) return <span className="text-xs text-muted-foreground">missing</span>
  if (r.passed === null) return <StatusBadge status={r.status} />
  return r.passed
    ? <span className="rounded-md bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">pass</span>
    : <span className="rounded-md bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800 dark:bg-red-950 dark:text-red-200">fail</span>
}

export function ResultsTable({ results }: { results: EvalResult[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow><TableHead>Case</TableHead><TableHead>Input</TableHead><TableHead>Expected</TableHead><TableHead>Output</TableHead><TableHead>Result</TableHead><TableHead className="text-right">Latency</TableHead></TableRow>
        </TableHeader>
        <TableBody>
          {results.map((r) => (
            <TableRow key={r.case_id}>
              <TableCell className="font-mono text-xs"><Link href={`/runs/${r.run_id}`} className="hover:underline">{r.case_id}</Link></TableCell>
              <TableCell className="max-w-48 text-sm"><p className="line-clamp-2">{r.input}</p></TableCell>
              <TableCell className="max-w-40 text-sm"><p className="line-clamp-2">{r.expected || "—"}</p></TableCell>
              <TableCell className="max-w-72 text-xs text-muted-foreground"><p className="line-clamp-3">{r.output ?? "—"}</p></TableCell>
              <TableCell><Verdict r={r} /><p className="mt-1 max-w-48 text-xs text-muted-foreground">{r.reason}</p></TableCell>
              <TableCell className="text-right text-sm tabular-nums">{fmtMs(r.latency_ms)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
