import { InDevelopment } from "@/components/common/states"

export default function Page() {
  return (
    <InDevelopment
      title="Evaluations: Runs"
      summary="Offline evaluation of agent versions against datasets."
      planned={["Datasets of input/expected-output cases", "Evaluation runs executed by the worker against a pinned agent version", "Scorers: exact match, JSON-schema validity, regex, LLM-as-judge with a pinned judge model", "Side-by-side comparison of two versions with per-case diffs"]}
      related={[
        { href: "/agents", label: "Agents and version compare (available)" },
      ]}
    />
  )
}
