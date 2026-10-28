import Link from "next/link"

import { Badge } from "@/components/ui/badge"

export function LinkCards({ items }: { items: { href: string; title: string; description: string; inDevelopment?: boolean }[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((i) => (
        <Link key={i.href} href={i.href} className="rounded-xl border p-4 transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
          <div className="flex items-center gap-2 font-medium">{i.title}{i.inDevelopment && <Badge variant="outline">In development</Badge>}</div>
          <p className="mt-1 text-sm text-muted-foreground">{i.description}</p>
        </Link>
      ))}
    </div>
  )
}
