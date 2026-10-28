"use client"

import { useQueryClient } from "@tanstack/react-query"
import { cn } from "cn"
import { LogOut, Menu, Monitor, Moon, Sun } from "lucide-react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useTheme } from "next-themes"
import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react"

import { ErrorState, LoadingRows } from "@/components/common/states"
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { useMe } from "@/hooks/use-api"
import { api, ApiError, setWorkspaceId } from "@/lib/api-client"
import { breadcrumbsFor, NAV_SECTIONS } from "@/lib/nav"
import { useWorkspaceCtx, WorkspaceProvider } from "@/lib/workspace-context"

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname()
  return (
    <nav aria-label="Main" className="flex flex-col gap-5 p-3">
      {NAV_SECTIONS.map((s) => (
        <div key={s.title}>
          <p className="px-2 pb-1 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">{s.title}</p>
          <ul className="space-y-0.5">
            {s.items.map((item) => {
              const active = pathname === item.href || pathname.startsWith(item.href + "/")
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      active ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                    )}
                  >
                    <item.icon className="size-4 shrink-0" aria-hidden />
                    <span className="flex-1 truncate">{item.label}</span>
                    {item.status === "in_development" && <span className="rounded border px-1 text-[10px] text-muted-foreground">Soon</span>}
                    {item.status === "partial" && <span className="rounded border px-1 text-[10px] text-muted-foreground">Partial</span>}
                  </Link>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </nav>
  )
}

const noopSubscribe = () => () => {}

function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  // true on the client, false during SSR: avoids a hydration mismatch for the theme icon
  const mounted = useSyncExternalStore(noopSubscribe, () => true, () => false)
  const next = theme === "light" ? "dark" : theme === "dark" ? "system" : "light"
  const Icon = !mounted ? Monitor : theme === "light" ? Sun : theme === "dark" ? Moon : Monitor
  return (
    <Button variant="ghost" size="icon" onClick={() => setTheme(next)} aria-label={`Theme: ${mounted ? theme : "system"}. Switch to ${next}`}>
      <Icon className="size-4" />
    </Button>
  )
}

function Topbar({ onOpenNav }: { onOpenNav: () => void }) {
  const { me, workspaceId, switchWorkspace, role } = useWorkspaceCtx()
  const pathname = usePathname()
  const router = useRouter()
  const qc = useQueryClient()
  const crumbs = breadcrumbsFor(pathname)

  async function logout() {
    try {
      await api.post("/auth/logout", null)
    } finally {
      setWorkspaceId(null)
      qc.clear()
      router.replace("/login")
    }
  }

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b bg-background/95 px-4 backdrop-blur">
      <Button variant="ghost" size="icon" className="lg:hidden" onClick={onOpenNav} aria-label="Open navigation">
        <Menu className="size-4" />
      </Button>
      <Breadcrumb className="hidden min-w-0 flex-1 sm:block">
        <BreadcrumbList>
          {crumbs.map((c, i) => (
            <span key={c.href} className="contents">
              {i > 0 && <BreadcrumbSeparator />}
              <BreadcrumbItem>
                {i === crumbs.length - 1 ? <BreadcrumbPage>{c.label}</BreadcrumbPage> : <BreadcrumbLink render={<Link href={c.href} />}>{c.label}</BreadcrumbLink>}
              </BreadcrumbItem>
            </span>
          ))}
        </BreadcrumbList>
      </Breadcrumb>
      <div className="ml-auto flex items-center gap-2">
        {me.demo_mode && (
          <span className="hidden rounded-md border border-amber-400 px-2 py-0.5 text-xs font-medium text-amber-800 md:inline dark:text-amber-300" title="A Demo provider with synthetic output is available. Runs using it are labeled DEMO.">
            Demo mode
          </span>
        )}
        <label className="sr-only" htmlFor="ws-switch">
          Workspace
        </label>
        <select
          id="ws-switch"
          value={workspaceId}
          onChange={(e) => switchWorkspace(e.target.value)}
          className="h-8 max-w-44 rounded-md border bg-background px-2 text-sm"
        >
          {me.memberships.map((m) => (
            <option key={m.workspace_id} value={m.workspace_id}>
              {m.workspace_name}
            </option>
          ))}
        </select>
        <span className="hidden text-xs text-muted-foreground md:inline" title={me.user.email}>
          {me.user.name} · {role}
        </span>
        <ThemeToggle />
        <Button variant="ghost" size="icon" onClick={logout} aria-label="Sign out">
          <LogOut className="size-4" />
        </Button>
      </div>
    </header>
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  const me = useMe()
  const router = useRouter()
  const pathname = usePathname()
  const qc = useQueryClient()
  const [navOpen, setNavOpen] = useState(false)

  const unauthenticated = me.error instanceof ApiError && me.error.status === 401
  useEffect(() => {
    if (unauthenticated) router.replace(`/login?next=${encodeURIComponent(pathname)}`)
  }, [unauthenticated, router, pathname])

  if (me.isPending || unauthenticated) {
    return (
      <div className="mx-auto max-w-5xl p-8">
        <LoadingRows rows={5} />
      </div>
    )
  }
  if (me.isError) {
    return (
      <div className="mx-auto max-w-xl p-8">
        <ErrorState error={me.error} onRetry={() => me.refetch()} />
      </div>
    )
  }

  return (
    <WorkspaceProvider me={me.data} onSwitch={() => qc.invalidateQueries()}>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-background focus:px-3 focus:py-2">
        Skip to content
      </a>
      <div className="flex min-h-screen">
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 overflow-y-auto border-r bg-sidebar lg:block">
          <Link href="/dashboard" className="flex h-14 items-center gap-2 border-b px-5 font-semibold">
            <span className="grid size-6 place-items-center rounded bg-primary text-[11px] text-primary-foreground">O</span>
            Orchestrator
          </Link>
          <Nav />
        </aside>
        <Sheet open={navOpen} onOpenChange={setNavOpen}>
          <SheetContent side="left" className="w-64 p-0">
            <SheetTitle className="border-b px-5 py-4">Orchestrator</SheetTitle>
            <Nav onNavigate={() => setNavOpen(false)} />
          </SheetContent>
        </Sheet>
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar onOpenNav={() => setNavOpen(true)} />
          <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 lg:px-8">
            {children}
          </main>
        </div>
      </div>
    </WorkspaceProvider>
  )
}
