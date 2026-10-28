import { Suspense } from "react"

import { InviteView } from "@/components/auth/invite-view"
import { Skeleton } from "@/components/ui/skeleton"

export const metadata = { title: "Invitation" }

/** The token is runtime data, so the prerendered shell is only the skeleton. */
export default function InvitePage() {
  return (
    <Suspense fallback={<Skeleton className="h-72 w-full max-w-sm" />}>
      <InviteView />
    </Suspense>
  )
}
