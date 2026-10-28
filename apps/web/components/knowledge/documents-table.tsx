"use client"

import { RefreshCw, Trash2 } from "lucide-react"
import Link from "next/link"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useKnowledgeMutations } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"
import { fmtDate } from "@/lib/format"
import type { KnowledgeDocument } from "@/lib/schemas"

const STATUS: Record<KnowledgeDocument["status"], "default" | "secondary" | "destructive" | "outline"> = {
  ready: "default", processing: "secondary", queued: "outline", failed: "destructive",
}

function fmtBytes(n: number): string {
  return n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`
}

export function DocumentsTable({ docs, workspaceId, write, kbNames }: { docs: KnowledgeDocument[]; workspaceId: string | null; write: boolean; kbNames?: Record<string, string> }) {
  const m = useKnowledgeMutations(workspaceId)
  return (
    <div className="rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Document</TableHead>
            {kbNames && <TableHead>Knowledge base</TableHead>}
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Chunks</TableHead>
            <TableHead>Added</TableHead>
            {write && <TableHead className="w-24"><span className="sr-only">Actions</span></TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {docs.map((d) => (
            <TableRow key={d.id}>
              <TableCell>
                <span className="font-medium">{d.title}</span>
                <p className="text-xs text-muted-foreground">{d.filename ?? "pasted text"} · {fmtBytes(d.bytes)}</p>
                {d.error && <p className="text-xs text-destructive">{d.error}</p>}
              </TableCell>
              {kbNames && <TableCell><Link href={`/knowledge/bases/${d.kb_id}`} className="text-sm underline-offset-4 hover:underline">{kbNames[d.kb_id] ?? d.kb_id}</Link></TableCell>}
              <TableCell><Badge variant={STATUS[d.status]}>{d.status}</Badge></TableCell>
              <TableCell className="text-right tabular-nums">{d.chunk_count}</TableCell>
              <TableCell className="text-sm text-muted-foreground">{fmtDate(d.created_at)}</TableCell>
              {write && (
                <TableCell className="text-right">
                  <Button variant="ghost" size="icon" aria-label={`Reindex ${d.title}`} disabled={d.status === "queued" || d.status === "processing"}
                    onClick={() => m.reindex.mutate(d.id, { onSuccess: () => toast.success("Queued for reindexing"), onError: (e) => toast.error(errorMessage(e)) })}>
                    <RefreshCw className="size-4" />
                  </Button>
                  <Button variant="ghost" size="icon" aria-label={`Delete ${d.title}`}
                    onClick={() => {
                      if (!window.confirm(`Delete "${d.title}"? Agents will no longer find its content.`)) return
                      m.removeDoc.mutate(d.id, { onSuccess: () => toast.success("Document deleted"), onError: (e) => toast.error(errorMessage(e)) })
                    }}>
                    <Trash2 className="size-4" />
                  </Button>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
