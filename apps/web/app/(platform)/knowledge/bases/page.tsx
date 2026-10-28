"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { toast } from "sonner"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useKnowledgeBases, useKnowledgeMutations, useProviders } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"
import { fmtDate } from "@/lib/format"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

const EMBEDDING_KINDS = ["openai", "openai_compatible", "gemini"]
const DEFAULT_MODEL: Record<string, string> = { openai: "text-embedding-3-small", gemini: "gemini-embedding-001", openai_compatible: "" }
const selectCls = "h-9 w-full rounded-md border bg-background px-2 text-sm"

function CreateKnowledgeBase({ workspaceId }: { workspaceId: string | null }) {
  const providers = useProviders(workspaceId)
  const m = useKnowledgeMutations(workspaceId)
  const router = useRouter()
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [providerId, setProviderId] = useState("")
  const [model, setModel] = useState("")
  const embedders = (providers.data ?? []).filter((p) => EMBEDDING_KINDS.includes(p.kind))

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    try {
      const kb = await m.create.mutateAsync({ name: name.trim(), description: description.trim(), embedding: providerId ? { provider_id: providerId, model: model.trim() } : null })
      toast.success("Knowledge base created")
      router.push(`/knowledge/bases/${kb.id}`)
    } catch (x) {
      toast.error(errorMessage(x))
    }
  }

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>New knowledge base</CardTitle>
        <CardDescription>
          Embeddings: pick an OpenAI, Gemini or OpenAI-compatible provider for semantic search. Without one, the built-in lexical index is used (no external calls, keyword matching).
          The embedding model cannot be changed later because existing vectors would no longer match.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="kb-name">Name</Label>
            <Input id="kb-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Product handbook" required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="kb-desc">Description</Label>
            <Input id="kb-desc" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="kb-provider">Embedding provider</Label>
            <select id="kb-provider" className={selectCls} value={providerId} onChange={(e) => {
              setProviderId(e.target.value)
              const p = embedders.find((x) => x.id === e.target.value)
              setModel(p ? DEFAULT_MODEL[p.kind] ?? "" : "")
            }}>
              <option value="">Built-in lexical index</option>
              {embedders.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.kind})</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="kb-model">Embedding model</Label>
            <Input id="kb-model" value={model} onChange={(e) => setModel(e.target.value)} disabled={!providerId} placeholder={providerId ? "text-embedding-3-small" : "not needed"} className="font-mono text-sm" />
          </div>
          <div className="sm:col-span-2">
            <Button type="submit" disabled={!name.trim() || (!!providerId && !model.trim()) || m.create.isPending}>{m.create.isPending ? "Creating…" : "Create knowledge base"}</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

export default function KnowledgeBasesPage() {
  const { workspaceId, role } = useWorkspaceCtx()
  const kbs = useKnowledgeBases(workspaceId)
  const write = can(role, "agents:write")
  return (
    <div>
      <PageHeader title="Knowledge bases" description="Assign a knowledge base to an agent and every run retrieves the most relevant passages, adds them to the prompt and cites them in the output." />
      {write && <CreateKnowledgeBase workspaceId={workspaceId} />}
      {kbs.isPending ? <LoadingRows /> : kbs.isError ? <ErrorState error={kbs.error} onRetry={() => kbs.refetch()} /> : kbs.data.length === 0 ? (
        <EmptyState title="No knowledge bases yet" description={write ? "Create one above, then add documents." : "Ask a developer to create one."} />
      ) : (
        <div className="rounded-xl border">
          <Table>
            <TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Search</TableHead><TableHead className="text-right">Documents</TableHead><TableHead className="text-right">Chunks</TableHead><TableHead>Updated</TableHead></TableRow></TableHeader>
            <TableBody>
              {kbs.data.map((k) => (
                <TableRow key={k.id}>
                  <TableCell>
                    <Link href={`/knowledge/bases/${k.id}`} className="font-medium underline-offset-4 hover:underline">{k.name}</Link>
                    {k.description && <p className="max-w-md truncate text-xs text-muted-foreground">{k.description}</p>}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{k.embedding ? k.embedding.model : "lexical"}</TableCell>
                  <TableCell className="text-right tabular-nums">{k.doc_count}</TableCell>
                  <TableCell className="text-right tabular-nums">{k.chunk_count}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{fmtDate(k.updated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
