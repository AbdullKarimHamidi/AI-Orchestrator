"use client"

import { Plus, Trash2 } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type { Tool } from "@/lib/schemas"

const METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"] as const
const NAME_RE = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/
const selectCls = "h-9 rounded-md border bg-background px-2 text-sm"

const EXAMPLE_SCHEMA = JSON.stringify({ type: "object", properties: { city: { type: "string", description: "City name" } }, required: ["city"] }, null, 2)

type Row = { key: string; value: string }

/** Validates and converts the form state into the API body. Returns an error message instead when invalid. */
export function buildToolBody(v: {
  name: string; description: string; method: string; url: string; timeout: string; schema: string
  headers: Row[]; secrets: Row[]; replaceSecrets: boolean
}, kind: "http" | "mcp"): Record<string, unknown> | string {
  if (!NAME_RE.test(v.name)) return "Name: start with a letter; letters, digits, _ and - only (max 64)"
  if (!v.description.trim()) return "Description is required: the model reads it to decide when to call the tool"
  let input_schema: unknown
  try {
    input_schema = JSON.parse(v.schema || "{}")
  } catch {
    return "Input schema is not valid JSON"
  }
  if (typeof input_schema !== "object" || input_schema === null || Array.isArray(input_schema) || ((input_schema as { type?: string }).type ?? "object") !== "object")
    return "Input schema must be a JSON Schema object with type \"object\""
  const toObj = (rows: Row[]) => Object.fromEntries(rows.filter((r) => r.key.trim()).map((r) => [r.key.trim(), r.value]))
  const body: Record<string, unknown> = { name: v.name, description: v.description.trim(), input_schema, headers: toObj(v.headers) }
  if (v.replaceSecrets) body.secret_headers = toObj(v.secrets)
  if (kind === "http") {
    if (!/^https?:\/\/.+/.test(v.url)) return "URL must start with http:// or https://"
    body.http = { method: v.method, url: v.url.trim(), timeout_seconds: v.timeout.trim() ? Number(v.timeout) : null }
  }
  return body
}

function Rows({ label, rows, setRows, secret }: { label: string; rows: Row[]; setRows: (r: Row[]) => void; secret?: boolean }) {
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium">{label}</legend>
      {rows.map((r, i) => (
        <div key={i} className="flex gap-2">
          <Input aria-label={`${label} name ${i + 1}`} placeholder="Header-Name" value={r.key} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)))} className="w-48" />
          <Input aria-label={`${label} value ${i + 1}`} type={secret ? "password" : "text"} autoComplete="off" placeholder={secret ? "secret value" : "value"} value={r.value} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
          <Button type="button" variant="ghost" size="icon" aria-label={`Remove ${label} ${i + 1}`} onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>
        </div>
      ))}
      <Button type="button" size="sm" variant="outline" onClick={() => setRows([...rows, { key: "", value: "" }])}><Plus className="size-4" /> Add</Button>
    </fieldset>
  )
}

export function ToolForm({ tool, submitLabel, onSubmit }: { tool?: Tool; submitLabel: string; onSubmit: (body: Record<string, unknown>) => Promise<void> }) {
  const kind = tool?.kind ?? "http"
  const [name, setName] = useState(tool?.name ?? "")
  const [description, setDescription] = useState(tool?.description ?? "")
  const [method, setMethod] = useState<string>(tool?.http?.method ?? "GET")
  const [url, setUrl] = useState(tool?.http?.url ?? "")
  const [timeout, setTimeout_] = useState(tool?.http?.timeout_seconds?.toString() ?? "")
  const [schema, setSchema] = useState(tool ? JSON.stringify(tool.input_schema, null, 2) : EXAMPLE_SCHEMA)
  const [headers, setHeaders] = useState<Row[]>(Object.entries(tool?.headers ?? {}).map(([key, value]) => ({ key, value })))
  const [secrets, setSecrets] = useState<Row[]>(tool ? [] : [{ key: "Authorization", value: "" }])
  const [replaceSecrets, setReplaceSecrets] = useState(!tool)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    const body = buildToolBody({ name, description, method, url, timeout, schema, headers, secrets, replaceSecrets }, kind)
    if (typeof body === "string") return setErr(body)
    if (!tool) body.kind = kind
    setBusy(true)
    try {
      await onSubmit(body)
    } catch (x) {
      setErr(x instanceof Error ? x.message : "Save failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-6" noValidate>
      {err && <Alert variant="destructive" role="alert"><AlertDescription>{err}</AlertDescription></Alert>}
      <Card>
        <CardHeader>
          <CardTitle>What the model sees</CardTitle>
          <CardDescription>The name, description and argument schema are sent to the model. Describe clearly when the tool should be used.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="t-name">Name</Label>
            <Input id="t-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="get_weather" className="max-w-sm font-mono" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="t-desc">Description</Label>
            <Textarea id="t-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Returns the current weather for a city. Use it when the user asks about weather." />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="t-schema">Arguments (JSON Schema)</Label>
            <Textarea id="t-schema" rows={8} className="font-mono text-xs" value={schema} onChange={(e) => setSchema(e.target.value)} />
          </div>
        </CardContent>
      </Card>
      {kind === "http" ? (
        <Card>
          <CardHeader>
            <CardTitle>HTTP request</CardTitle>
            <CardDescription>
              Put arguments in the URL as <code>{"{name}"}</code>. Remaining arguments go to the query string (GET/DELETE) or the JSON body (POST/PUT/PATCH).
              Private network addresses are blocked unless the server sets TOOLS_ALLOW_PRIVATE_NETWORKS=true.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="t-method">Method</Label>
                <select id="t-method" value={method} onChange={(e) => setMethod(e.target.value)} className={selectCls}>
                  {METHODS.map((m) => <option key={m}>{m}</option>)}
                </select>
              </div>
              <div className="min-w-72 flex-1 space-y-1.5">
                <Label htmlFor="t-url">URL</Label>
                <Input id="t-url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://api.example.com/weather/{city}" className="font-mono text-sm" />
              </div>
              <div className="w-28 space-y-1.5">
                <Label htmlFor="t-timeout">Timeout (s)</Label>
                <Input id="t-timeout" inputMode="decimal" value={timeout} onChange={(e) => setTimeout_(e.target.value)} placeholder="30" />
              </div>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>MCP server</CardTitle>
            <CardDescription>Imported from <span className="font-mono">{tool?.mcp?.server_url}</span> (remote tool <span className="font-mono">{tool?.mcp?.tool_name}</span>).</CardDescription>
          </CardHeader>
        </Card>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Headers</CardTitle>
          <CardDescription>Secret headers (API keys, tokens) are encrypted at rest and never shown again or sent to the model.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <Rows label="Headers" rows={headers} setRows={setHeaders} />
          {tool && !replaceSecrets ? (
            <div className="space-y-2">
              <p className="text-sm">Secret headers: {tool.secret_header_names.length ? tool.secret_header_names.join(", ") : "none"}</p>
              <Button type="button" size="sm" variant="outline" onClick={() => { setReplaceSecrets(true); setSecrets([{ key: "", value: "" }]) }}>Replace secret headers</Button>
            </div>
          ) : (
            <Rows label="Secret headers" rows={secrets} setRows={setSecrets} secret />
          )}
        </CardContent>
      </Card>
      <div className="flex justify-end gap-2">
        <Link href="/tools" className={buttonVariants({ variant: "ghost" })}>Cancel</Link>
        <Button type="submit" disabled={busy}>{busy ? "Saving…" : submitLabel}</Button>
      </div>
    </form>
  )
}
