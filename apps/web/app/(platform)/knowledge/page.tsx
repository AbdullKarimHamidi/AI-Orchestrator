import Link from "next/link"

import { PageHeader } from "@/components/common/states"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const LINKS = [
  { href: "/knowledge/bases", title: "Knowledge bases", text: "Collections of documents an agent can search. Upload PDF, Word, Markdown, HTML, CSV, JSON or text." },
  { href: "/knowledge/documents", title: "Documents", text: "Every document across knowledge bases, with its ingestion status." },
]

export default function KnowledgePage() {
  return (
    <div>
      <PageHeader title="Knowledge" description="Give agents your own content. Documents are chunked and embedded by the worker; at run time the most relevant passages are added to the prompt and cited in the output." />
      <div className="grid gap-4 sm:grid-cols-2">
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href} className="rounded-xl transition-colors hover:bg-muted/50">
            <Card className="h-full bg-transparent">
              <CardHeader><CardTitle>{l.title}</CardTitle><CardDescription>{l.text}</CardDescription></CardHeader>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
