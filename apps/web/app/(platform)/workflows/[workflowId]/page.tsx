import { InDevelopment } from "@/components/common/states"

export default function Page() {
  return (
    <InDevelopment
      title="Workflows detail"
      summary="Multi-step graphs that combine LLM calls, agents, tools, conditions, and human approvals, executed by the worker."
      planned={["React Flow editor with start/end, LLM, agent, tool, condition (JSON-Logic), transform (sandboxed Jinja), parallel/join, retry/fallback, delay, human approval, knowledge retrieval, and structured-output nodes", "Server-side graph validation against companions/workflow-definition.schema.json (reachability, cycles only through a bounded loop controller)", "Immutable workflow versions with publish/rollback", "Worker-side executor with per-node events streamed into the existing run inspector"]}
      related={[
        { href: "/agents", label: "Agents (available)" },
        { href: "/runs", label: "Runs (available)" },
      ]}
    />
  )
}
