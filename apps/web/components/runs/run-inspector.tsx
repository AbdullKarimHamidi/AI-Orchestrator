"use client"

import Link from "next/link"
import { toast } from "sonner"

import { DemoBadge, StatusBadge } from "@/components/common/status-badge"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useRunMutations } from "@/hooks/use-api"
import { useRunStream } from "@/hooks/use-run-stream"
import { errorMessage } from "@/lib/api-client"
import { fmtDate, fmtMs, fmtUsd } from "@/lib/format"
import { TERMINAL_STATUSES, type Run } from "@/lib/schemas"
import { can, useWorkspaceCtx } from "@/lib/workspace-context"

import { RunTimeline } from "./run-timeline"

type StepOut = { text?: string; duration_ms?: number; result?: boolean; agent_name?: string; tool?: string; count?: number }

function WorkflowSteps({ run }: { run: Run }) {
  const path = (Array.isArray(run.output?.path) ? run.output.path : []) as string[]
  const steps = (run.output?.steps ?? {}) as Record<string, StepOut>
  if (path.length === 0) return null
  return (
    <div className="mt-4">
      <p className="text-sm font-medium">Executed steps</p>
      <ol className="mt-1 space-y-2" aria-label="Executed steps">
        {path.map((id, i) => {
          const s = steps[id] ?? {}
          return (
            <li key={`${id}-${i}`} className="rounded-md border p-2">
              <div className="flex flex-wrap items-baseline gap-2 text-sm">
                <span className="font-mono text-xs text-muted-foreground">{i + 1}.</span>
                <span className="font-mono text-xs font-medium">{id}</span>
                {s.agent_name && <span className="text-xs text-muted-foreground">agent {s.agent_name}</span>}
                {s.tool && <span className="text-xs text-muted-foreground">tool {s.tool}</span>}
                {s.result !== undefined && <span className="text-xs">condition: <span className="font-medium">{String(s.result)}</span></span>}
                {s.duration_ms !== undefined && <span className="ml-auto text-xs text-muted-foreground">{fmtMs(s.duration_ms)}</span>}
              </div>
              {s.result === undefined && s.text && <p className="mt-1 line-clamp-3 text-xs whitespace-pre-wrap text-muted-foreground">{s.text}</p>}
            </li>
          )
        })}
      </ol>
    </div>
  )
}

export function RunInspector({ run, compact }: { run: Run; compact?: boolean }) {
  const { workspaceId, role } = useWorkspaceCtx()
  const { events, state } = useRunStream(run.id, workspaceId)
  const { cancel } = useRunMutations(workspaceId)
  const active = !TERMINAL_STATUSES.includes(run.status)
  const text = typeof run.output?.text === "string" ? run.output.text : null
  const citations = (Array.isArray(run.output?.citations) ? run.output.citations : []) as { n: number; kb_id: string; title: string; excerpt: string }[]

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
      <div className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={run.status} />
          {run.demo && <DemoBadge />}
          {run.cancel_requested && active && <span className="text-sm text-muted-foreground">Cancellation requested…</span>}
          {active && can(role, "runs:cancel") && !run.cancel_requested && (
            <Button
              size="sm"
              variant="outline"
              className="ml-auto"
              onClick={async () => {
                try {
                  await cancel.mutateAsync(run.id)
                  toast.success("Cancellation sent to the worker")
                } catch (e) {
                  toast.error(errorMessage(e))
                }
              }}
            >
              Cancel run
            </Button>
          )}
        </div>
        {run.error && (
          <Alert variant="destructive">
            <AlertTitle>{run.error.code}</AlertTitle>
            <AlertDescription>{run.error.message}</AlertDescription>
          </Alert>
        )}
        <Card>
          <CardHeader><CardTitle>Output</CardTitle></CardHeader>
          <CardContent>
            {text !== null ? (
              <>
                <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 text-sm whitespace-pre-wrap">{text}</pre>
                {run.output?.provider_kind !== undefined && (
                  <p className="mt-2 text-xs text-muted-foreground">Served by {String(run.output?.provider_kind)} / {String(run.output?.model)} ({String(run.output?.slot)})</p>
                )}
                {run.kind === "workflow" && <WorkflowSteps run={run} />}
                {run.output?.structured !== undefined && (
                  <pre className="mt-3 overflow-auto rounded-md border p-3 text-xs">{JSON.stringify(run.output.structured, null, 2)}</pre>
                )}
                {citations.length > 0 && (
                  <div className="mt-4">
                    <p className="text-sm font-medium">Sources</p>
                    <ol className="mt-1 space-y-1 text-sm" aria-label="Sources">
                      {citations.map((c) => (
                        <li key={c.n}>
                          <span className="font-mono text-xs">[{c.n}]</span>{" "}
                          <Link href={`/knowledge/bases/${c.kb_id}`} className="underline-offset-4 hover:underline">{c.title}</Link>
                          <span className="block text-xs text-muted-foreground line-clamp-2">{c.excerpt}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">{active ? "The worker is processing this run…" : "No output."}</p>
            )}
          </CardContent>
        </Card>
        {!compact && (
          <Card>
            <CardHeader><CardTitle>Input</CardTitle></CardHeader>
            <CardContent><pre className="overflow-auto rounded-md bg-muted p-3 text-xs">{JSON.stringify(run.input, null, 2)}</pre></CardContent>
          </Card>
        )}
      </div>
      <div className="space-y-4">
        <Card>
          <CardHeader><CardTitle>Details</CardTitle></CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
              <dt className="text-muted-foreground">{run.kind === "workflow" ? "Workflow" : "Agent"}</dt><dd>{run.agent_name}</dd>
              <dt className="text-muted-foreground">Config</dt><dd>{run.source === "draft" ? "draft snapshot" : `v${run.agent_version}`}</dd>
              {run.eval_run_id && <><dt className="text-muted-foreground">Evaluation</dt><dd><Link href="/evaluations/runs" className="underline-offset-4 hover:underline">{run.eval_run_id.slice(0, 14)}…</Link></dd></>}
              <dt className="text-muted-foreground">Attempt</dt><dd>{run.attempt} / {run.max_attempts}</dd>
              <dt className="text-muted-foreground">Timeout</dt><dd>{run.timeout_seconds}s</dd>
              <dt className="text-muted-foreground">Duration</dt><dd>{fmtMs(run.duration_ms)}</dd>
              <dt className="text-muted-foreground">Tokens</dt><dd>{run.usage.input_tokens} in / {run.usage.output_tokens} out</dd>
              <dt className="text-muted-foreground">Cost</dt><dd>{fmtUsd(run.usage.cost_usd)}</dd>
              <dt className="text-muted-foreground">Created</dt><dd>{fmtDate(run.created_at)}</dd>
            </dl>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              Events <span className="text-xs font-normal text-muted-foreground">stream: {state}</span>
            </CardTitle>
          </CardHeader>
          <CardContent><RunTimeline events={events} live={active} /></CardContent>
        </Card>
      </div>
    </div>
  )
}
