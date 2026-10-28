"use client"

import { useQuery } from "@tanstack/react-query"
import Link from "next/link"
import { useParams } from "next/navigation"

import { AuthForm } from "@/components/layout/auth-form"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { api, errorMessage } from "@/lib/api-client"
import { invitationInfoSchema } from "@/lib/schemas"

/** Invitation landing page. New people register (joining the workspace); existing accounts sign
 * in and the invitation is accepted right after. The token in the URL is the credential. */
export function InviteView() {
  const { token } = useParams<{ token: string }>()
  const info = useQuery({
    queryKey: ["invitation", token],
    queryFn: () => api.get(`/auth/invitations/${encodeURIComponent(token)}`, invitationInfoSchema),
    retry: false,
  })

  if (info.isPending) return <Skeleton className="h-72 w-full max-w-sm" />
  if (info.isError) {
    return (
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">Invitation unavailable</CardTitle>
          <CardDescription>{errorMessage(info.error)}</CardDescription>
        </CardHeader>
        <CardContent>
          <Link className="text-sm underline underline-offset-4" href="/login">Go to sign in</Link>
        </CardContent>
      </Card>
    )
  }
  return <AuthForm mode={info.data.has_account ? "login" : "register"} invite={{ ...info.data, token }} />
}
