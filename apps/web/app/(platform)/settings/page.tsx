import { LinkCards } from "@/components/common/link-cards"
import { PageHeader } from "@/components/common/states"

export default function SettingsPage() {
  return (
    <div>
      <PageHeader title="Settings" />
      <LinkCards items={[
        { href: "/settings/workspace", title: "Workspace", description: "Name and monthly spend budget enforced before every run." },
        { href: "/settings/account", title: "Account", description: "Change your password and create additional workspaces." },
        { href: "/settings/api-keys", title: "API keys", description: "Call agents from your own code with a role-scoped key." },
        { href: "/settings/billing", title: "Billing", description: "Plans and invoices.", inDevelopment: true },
      ]} />
    </div>
  )
}
