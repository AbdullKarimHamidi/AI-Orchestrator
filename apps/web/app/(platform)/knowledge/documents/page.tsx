"use client"

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/common/states"
import { DocumentsTable } from "@/components/knowledge/documents-table"
import { useDocuments, useKnowledgeBases } from "@/hooks/use-api"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

export default function DocumentsPage() {
  const { workspaceId, role } = useWorkspaceCtx()
  const docs = useDocuments(workspaceId)
  const kbs = useKnowledgeBases(workspaceId)
  const kbNames = Object.fromEntries((kbs.data ?? []).map((k) => [k.id, k.name]))
  return (
    <div>
      <PageHeader title="Documents" description="All documents across knowledge bases. Ingestion runs in the worker; this list refreshes while documents are processing." />
      {docs.isPending ? <LoadingRows /> : docs.isError ? <ErrorState error={docs.error} onRetry={() => docs.refetch()} /> : docs.data.items.length === 0 ? (
        <EmptyState title="No documents yet" description="Open a knowledge base to upload files or paste text." />
      ) : (
        <DocumentsTable docs={docs.data.items} workspaceId={workspaceId} write={can(role, "agents:write")} kbNames={kbNames} />
      )}
    </div>
  )
}
