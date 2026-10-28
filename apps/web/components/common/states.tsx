import { AlertTriangle, Construction, Inbox } from "lucide-react"
import Link from "next/link"
import type { ReactNode } from "react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { buttonVariants } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { ApiError, errorMessage } from "@/lib/api-client"

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed px-6 py-14 text-center">
      <Inbox className="mb-3 size-8 text-muted-foreground" aria-hidden />
      <h2 className="font-medium">{title}</h2>
      {description && <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const cid = error instanceof ApiError ? error.correlationId : undefined
  return (
    <Alert variant="destructive" role="alert">
      <AlertTriangle aria-hidden />
      <AlertTitle>Could not load data</AlertTitle>
      <AlertDescription>
        <p>{errorMessage(error)}</p>
        {cid && <p className="mt-1 font-mono text-xs">Reference: {cid}</p>}
        {onRetry && (
          <button type="button" onClick={onRetry} className="mt-2 underline underline-offset-4">
            Try again
          </button>
        )}
      </AlertDescription>
    </Alert>
  )
}

export function LoadingRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  )
}

export function InDevelopment({ title, summary, planned, related }: { title: string; summary: string; planned: string[]; related?: { href: string; label: string }[] }) {
  return (
    <div>
      <PageHeader title={title} description={summary} />
      <div className="rounded-xl border bg-card p-6">
        <div className="mb-4 flex items-center gap-2">
          <Construction className="size-5 text-amber-600 dark:text-amber-400" aria-hidden />
          <Badge variant="outline">In development</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          This module is not implemented yet. No controls are shown here on purpose: nothing on this page pretends to work.
          The design is specified in the architecture blueprint and API contract in this repository.
        </p>
        <h2 className="mt-5 text-sm font-medium">Planned scope</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          {planned.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
        {related && related.length > 0 && (
          <div className="mt-5 flex flex-wrap gap-2">
            {related.map((r) => (
              <Link key={r.href} href={r.href} className={buttonVariants({ variant: "outline", size: "sm" })}>
                {r.label}
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
