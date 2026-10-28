"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useQueryClient } from "@tanstack/react-query"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState, useSyncExternalStore } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuthConfig } from "@/hooks/use-api"
import { api, errorMessage, setWorkspaceId } from "@/lib/api-client"
import { meSchema, type InvitationInfo } from "@/lib/schemas"

export const loginSchema = z.object({
  email: z.email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
})

export const registerSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(120),
  email: z.email("Enter a valid email"),
  password: z.string().min(12, "Use at least 12 characters").max(256),
  workspace_name: z.string().trim().min(1, "Workspace name is required").max(120),
})

/** Registering through an invitation joins the inviting workspace, so no workspace name is asked. */
export const inviteRegisterSchema = registerSchema.extend({ workspace_name: z.string() })

type Mode = "login" | "register"
type Values = z.infer<typeof registerSchema>

function Field({ id, label, error, ...props }: { id: string; label: string; error?: string } & React.ComponentProps<typeof Input>) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} aria-invalid={!!error} aria-describedby={error ? `${id}-err` : undefined} {...props} />
      {error && (
        <p id={`${id}-err`} className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}

const noopSubscribe = () => () => {}

export interface InviteContext extends InvitationInfo {
  token: string
}

export function AuthForm({ mode, invite }: { mode: Mode; invite?: InviteContext }) {
  // The page is prerendered. Until React hydrates, a click would trigger a native form submit;
  // keep the button disabled until then, and use method="post" so credentials can never end
  // up in the URL, browser history, or access logs.
  const hydrated = useSyncExternalStore(noopSubscribe, () => true, () => false)
  const router = useRouter()
  const qc = useQueryClient()
  const [serverError, setServerError] = useState<string | null>(null)
  const authConfig = useAuthConfig(mode === "register" && !invite)
  const schema = mode === "login" ? loginSchema : invite ? inviteRegisterSchema : registerSchema
  const form = useForm<Values>({
    resolver: zodResolver(schema as typeof registerSchema),
    defaultValues: { name: "", email: invite?.email ?? "", password: "", workspace_name: "" },
  })
  const { errors, isSubmitting } = form.formState

  async function onSubmit(values: Values) {
    setServerError(null)
    try {
      const body =
        mode === "login"
          ? { email: values.email, password: values.password }
          : invite
            ? { name: values.name, email: values.email, password: values.password, invite_token: invite.token }
            : values
      let me = await api.post(`/auth/${mode}`, meSchema, body)
      if (invite && mode === "login") me = await api.post(`/auth/invitations/${invite.token}/accept`, meSchema)
      const joined = invite ? me.memberships.find((m) => m.workspace_name === invite.workspace_name) : undefined
      setWorkspaceId((joined ?? me.memberships[0])?.workspace_id ?? null)
      qc.setQueryData(["me"], me)
      const next = new URLSearchParams(window.location.search).get("next")
      // only same-origin paths: blocks open redirects such as ?next=//evil.example
      const dest = next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/dashboard"
      router.replace(dest)
    } catch (e) {
      setServerError(errorMessage(e))
    }
  }

  if (mode === "register" && !invite && authConfig.data && !authConfig.data.registration_open) {
    return (
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">Registration is closed</CardTitle>
          <CardDescription>This server only accepts new accounts by invitation. Ask a workspace administrator to send you an invitation link.</CardDescription>
        </CardHeader>
        <CardContent>
          <Link className="text-sm underline underline-offset-4" href="/login">Back to sign in</Link>
        </CardContent>
      </Card>
    )
  }

  const description = invite
    ? `Join ${invite.workspace_name} as ${invite.role}.`
    : mode === "login" ? "Access your orchestration workspace." : "You will become the owner of a new workspace."

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-xl">{mode === "login" ? "Sign in" : "Create your account"}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <form method="post" onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          {serverError && (
            <Alert variant="destructive" role="alert">
              <AlertDescription>{serverError}</AlertDescription>
            </Alert>
          )}
          {mode === "register" && <Field id="name" label="Your name" autoComplete="name" error={errors.name?.message} {...form.register("name")} />}
          <Field id="email" label="Email" type="email" autoComplete="email" readOnly={!!invite} error={errors.email?.message} {...form.register("email")} />
          <Field id="password" label="Password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} error={errors.password?.message} {...form.register("password")} />
          {mode === "register" && !invite && <Field id="workspace_name" label="Workspace name" error={errors.workspace_name?.message} {...form.register("workspace_name")} />}
          <Button type="submit" className="w-full" disabled={!hydrated || isSubmitting}>
            {isSubmitting ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </Button>
          {!invite && <p className="text-center text-sm text-muted-foreground">
            {mode === "login" ? (
              <>
                No account? <Link className="underline underline-offset-4" href="/register">Register</Link>
              </>
            ) : (
              <>
                Already registered? <Link className="underline underline-offset-4" href="/login">Sign in</Link>
              </>
            )}
          </p>}
        </form>
      </CardContent>
    </Card>
  )
}
