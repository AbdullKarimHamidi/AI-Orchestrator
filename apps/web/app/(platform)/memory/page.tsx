import { InDevelopment } from "@/components/common/states"

export default function Page() {
  return (
    <InDevelopment
      title="Memory"
      summary="Long-term conversation memory for agents."
      planned={["Per-agent, per-end-user memory scopes with retention limits", "Explicit read/write memory tools and deletion requests"]}
      related={[
        { href: "/agents", label: "Agents (available)" },
      ]}
    />
  )
}
