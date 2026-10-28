"use client"

import { Upload } from "lucide-react"
import { useParams, useRouter } from "next/navigation"
import { useRef, useState } from "react"
import { toast } from "sonner"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { DocumentsTable } from "@/components/knowledge/documents-table"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useDocuments, useKnowledgeBase, useKnowledgeMutations } from "@/hooks/use-api"
import { errorMessage } from "@/lib/api-client"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

const ACCEPT = ".pdf,.docx,.md,.markdown,.txt,.html,.htm,.csv,.json,.rst,.log,.yaml,.yml,.xml,.sql,.py,.js,.ts,.java,.go"

export default function KnowledgeBasePage() {
  const { baseId } = useParams<{ baseId: string }>()
  const { workspaceId, role } = useWorkspaceCtx()
  const kb = useKnowledgeBase(workspaceId, baseId)
  const docs = useDocuments(workspaceId, baseId)
  const m = useKnowledgeMutations(workspaceId)
  const router = useRouter()
  const fileRef = useRef<HTMLInputElement>(null)
  const [title, setTitle] = useState("")
  const [text, setText] = useState("")
  const [query, setQuery] = useState("")
  const write = can(role, "agents:write")

  if (kb.isPending) return <LoadingRows />
  if (kb.isError) return <ErrorState error={kb.error} onRetry={() => kb.refetch()} />
  const k = kb.data

  async function uploadFiles(files: FileList | null) {
    for (const file of Array.from(files ?? [])) {
      try {
        await m.upload.mutateAsync({ kbId: k.id, file })
        toast.success(`${file.name} queued for indexing`)
      } catch (e) {
        toast.error(`${file.name}: ${errorMessage(e)}`)
      }
    }
    if (fileRef.current) fileRef.current.value = ""
  }

  async function addText(e: React.FormEvent) {
    e.preventDefault()
    try {
      await m.addText.mutateAsync({ kbId: k.id, title: title.trim(), text })
      toast.success("Text queued for indexing")
      setTitle("")
      setText("")
    } catch (x) {
      toast.error(errorMessage(x))
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title={k.name} description={`${k.description ? k.description + " · " : ""}${k.embedding ? `Semantic search with ${k.embedding.model}` : "Built-in lexical search"} · ${k.doc_count} document${k.doc_count === 1 ? "" : "s"}, ${k.chunk_count} chunk${k.chunk_count === 1 ? "" : "s"}`}
        actions={write && (
          <Button variant="outline" onClick={async () => {
            if (!window.confirm(`Delete knowledge base "${k.name}" and all its documents? Agents using it must be updated before their next publish.`)) return
            try {
              await m.remove.mutateAsync(k.id)
              toast.success("Knowledge base deleted")
              router.push("/knowledge/bases")
            } catch (e) {
              toast.error(errorMessage(e))
            }
          }}>Delete</Button>
        )} />

      {write && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Upload files</CardTitle>
              <CardDescription>PDF, Word (.docx), Markdown, HTML, CSV, JSON and plain text. Scanned PDFs need OCR first.</CardDescription>
            </CardHeader>
            <CardContent>
              <input ref={fileRef} id="kb-files" type="file" multiple accept={ACCEPT} className="sr-only" onChange={(e) => uploadFiles(e.target.files)} />
              <Button type="button" onClick={() => fileRef.current?.click()} disabled={m.upload.isPending}>
                <Upload className="size-4" /> {m.upload.isPending ? "Uploading…" : "Choose files"}
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Paste text</CardTitle>
              <CardDescription>FAQs, policies, notes: anything you can paste.</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={addText} className="space-y-3">
                <div className="space-y-1.5">
                  <Label htmlFor="doc-title">Title</Label>
                  <Input id="doc-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Refund policy" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="doc-text">Text</Label>
                  <Textarea id="doc-text" rows={5} value={text} onChange={(e) => setText(e.target.value)} />
                </div>
                <Button type="submit" variant="outline" disabled={!title.trim() || !text.trim() || m.addText.isPending}>Add text</Button>
              </form>
            </CardContent>
          </Card>
        </div>
      )}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Documents</h2>
        {docs.isPending ? <LoadingRows /> : docs.isError ? <ErrorState error={docs.error} onRetry={() => docs.refetch()} /> : docs.data.items.length === 0 ? (
          <EmptyState title="No documents yet" description={write ? "Upload files or paste text above." : "Nothing has been added yet."} />
        ) : (
          <DocumentsTable docs={docs.data.items} workspaceId={workspaceId} write={write} />
        )}
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Test search</CardTitle>
          <CardDescription>See exactly which passages an agent would receive for a question.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); m.search.mutate({ kbId: k.id, query }) }}>
            <Input aria-label="Search query" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="How long do refunds take?" />
            <Button type="submit" disabled={!query.trim() || m.search.isPending}>Search</Button>
          </form>
          {m.search.isError && <p className="text-sm text-destructive">{errorMessage(m.search.error)}</p>}
          {m.search.data && (m.search.data.length === 0 ? <p className="text-sm text-muted-foreground">No matching passages.</p> : (
            <ol className="space-y-3" aria-label="Search results">
              {m.search.data.map((h) => (
                <li key={`${h.doc_id}-${h.chunk}`} className="rounded-md border p-3">
                  <p className="text-xs text-muted-foreground">{h.title} · passage {h.chunk + 1} · score {h.score.toFixed(3)}</p>
                  <p className="mt-1 line-clamp-6 text-sm whitespace-pre-wrap">{h.text}</p>
                </li>
              ))}
            </ol>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
