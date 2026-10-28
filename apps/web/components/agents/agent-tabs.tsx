"use client"

import { cn } from "cn"
import Link from "next/link"
import { usePathname } from "next/navigation"

export function AgentTabs({ id }: { id: string }) {
  const pathname = usePathname()
  const tabs = [
    { href: `/agents/${id}`, label: "Overview" },
    { href: `/agents/${id}/edit`, label: "Edit draft" },
    { href: `/agents/${id}/versions`, label: "Versions" },
    { href: `/agents/${id}/test`, label: "Test console" },
  ]
  return (
    <nav aria-label="Agent sections" className="mb-6 flex gap-1 overflow-x-auto border-b">
      {tabs.map((t) => {
        const active = pathname === t.href
        return (
          <Link key={t.href} href={t.href} aria-current={active ? "page" : undefined} className={cn("-mb-px border-b-2 px-3 py-2 text-sm whitespace-nowrap", active ? "border-primary font-medium" : "border-transparent text-muted-foreground hover:text-foreground")}>
            {t.label}
          </Link>
        )
      })}
    </nav>
  )
}
