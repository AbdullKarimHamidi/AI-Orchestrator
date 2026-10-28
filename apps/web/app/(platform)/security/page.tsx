import { LinkCards } from "@/components/common/link-cards"
import { PageHeader } from "@/components/common/states"

export default function SecurityPage() {
  return (
    <div>
      <PageHeader title="Security" description="Access control for this workspace. Sessions use HttpOnly cookies with CSRF protection; passwords are hashed with Argon2id; provider keys are encrypted at rest." />
      <LinkCards items={[
        { href: "/security/users", title: "Users", description: "Members and role assignments." },
        { href: "/security/roles", title: "Roles", description: "Permission matrix for owner, administrator, developer, operator, viewer." },
        { href: "/security/audit", title: "Audit log", description: "Who changed what, and when." },
        { href: "/settings/api-keys", title: "API keys", description: "Role-scoped keys for calling agents from your own apps." },
      ]} />
      <h2 className="mt-8 mb-2 text-sm font-medium">Not implemented yet</h2>
      <ul className="list-disc pl-5 text-sm text-muted-foreground">
        <li>SSO (OIDC/SAML) and MFA</li>
        <li>Custom roles and a session management UI</li>
      </ul>
    </div>
  )
}
