import { InDevelopment } from "@/components/common/states"

export default function Page() {
  return (
    <InDevelopment
      title="Billing"
      summary="Plans, invoices, and payment methods."
      planned={["Plan and seat management", "Invoices and payment provider integration", "Today, spend is controlled by the workspace monthly budget in Workspace settings"]}
      related={[
        { href: "/settings/workspace", label: "Workspace budget (available)" },
        { href: "/analytics", label: "Usage analytics (available)" },
      ]}
    />
  )
}
