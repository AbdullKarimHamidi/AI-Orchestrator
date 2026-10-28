import { AuthForm } from "@/components/layout/auth-form"

export const metadata = { title: "Sign in" }

/** Static page: the `?next=` redirect target is read on the client at submit time, so the form
 * is never re-mounted after hydration (which would discard what the user already typed). */
export default function LoginPage() {
  return <AuthForm mode="login" />
}
