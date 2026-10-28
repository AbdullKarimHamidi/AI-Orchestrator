import { Suspense } from "react"

import { LoadingRows } from "@/components/common/states"
import { AppShell } from "@/components/layout/app-shell"

/** The shell is fully client-rendered (session, workspace, and URL are runtime data), so the
 * static prerender is just this skeleton; everything else streams in on the client. */
export default function PlatformLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="mx-auto max-w-5xl p-8"><LoadingRows rows={5} /></div>}>
      <AppShell>{children}</AppShell>
    </Suspense>
  )
}
