import Link from "next/link"

import { PageHeader } from "@/components/common/states"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const LINKS = [
  { href: "/integrations/mcp", title: "MCP servers", text: "Discover the tools a remote MCP server offers and import the ones you trust." },
  { href: "/tools/new", title: "HTTP APIs", text: "Turn any REST endpoint (CRM, tickets, internal services) into a tool an agent can call." },
  { href: "/models", title: "Model providers", text: "OpenAI, Anthropic, Gemini or any OpenAI-compatible server, with fallbacks and budgets." },
  { href: "/settings/api-keys", title: "API keys", text: "Call agents from your own apps and scripts with a workspace API key." },
]

export default function IntegrationsPage() {
  return (
    <div>
      <PageHeader title="Integrations" description="Connect the platform to your systems." />
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
