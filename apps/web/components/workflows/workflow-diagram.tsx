import { cn } from "cn"
import { ArrowDown, CircleStop, Play } from "lucide-react"

import type { WorkflowDefinition } from "@/lib/schemas"

import { edgesOf, STEP_META } from "./steps"

function detail(def: WorkflowDefinition, i: number, names: Record<string, string>): string {
  const s = def.steps[i]
  switch (s.type) {
    case "agent":
      return `${names[s.agent_id ?? ""] ?? s.agent_id ?? "no agent"} ← ${s.message}`
    case "tool":
      return `${names[s.tool_id ?? ""] ?? s.tool_id ?? "no tool"}(${Object.keys(s.arguments).join(", ")})`
    case "knowledge":
      return `${s.knowledge_base_ids.map((k) => names[k] ?? k).join(", ") || "no knowledge base"} · top ${s.top_k}`
    case "transform":
      return s.template
    case "condition":
      return s.condition ? `${s.condition.left} ${s.condition.op.replace("_", " ")} ${s.condition.right}` : ""
  }
}

/** Vertical flow of a workflow: one card per step, with its outgoing routes. `path` highlights
 * the steps an actual run executed, in order. */
export function WorkflowDiagram({ definition, names = {}, path }: { definition: WorkflowDefinition; names?: Record<string, string>; path?: string[] }) {
  const visited = new Set(path ?? [])
  return (
    <ol className="space-y-1" aria-label="Workflow steps">
      <li className="flex items-center gap-2 text-xs font-medium text-muted-foreground"><Play className="size-3.5" aria-hidden /> Start: input.message</li>
      {definition.steps.map((s, i) => {
        const Meta = STEP_META[s.type]
        const edges = edgesOf(definition, i)
        const order = path ? path.indexOf(s.id) : -1
        return (
          <li key={s.id}>
            <ArrowDown className="mx-3 my-0.5 size-3.5 text-muted-foreground" aria-hidden />
            <div className={cn("rounded-lg border bg-card p-3", path && (visited.has(s.id) ? "border-emerald-500 ring-1 ring-emerald-500/30" : "opacity-60"))}>
              <div className="flex flex-wrap items-center gap-2">
                <Meta.icon className="size-4 text-muted-foreground" aria-hidden />
                <span className="font-mono text-xs">{s.id}</span>
                <span className="text-sm font-medium">{s.name || Meta.label}</span>
                <span className="rounded border px-1.5 text-[11px] text-muted-foreground">{Meta.label}</span>
                {order >= 0 && <span className="ml-auto rounded bg-emerald-100 px-1.5 text-[11px] font-medium text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">step {order + 1}</span>}
              </div>
              <p className="mt-1 line-clamp-2 font-mono text-xs break-all text-muted-foreground">{detail(definition, i, names)}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {edges.map((e) => (
                  <span key={e.label} className="rounded-md bg-muted px-1.5 py-0.5 text-[11px]">
                    {e.label} → <span className="font-mono">{e.target}</span>
                  </span>
                ))}
              </div>
            </div>
          </li>
        )
      })}
      <li>
        <ArrowDown className="mx-3 my-0.5 size-3.5 text-muted-foreground" aria-hidden />
        <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground"><CircleStop className="size-3.5" aria-hidden /> End: output is the last step&apos;s text</span>
      </li>
    </ol>
  )
}
