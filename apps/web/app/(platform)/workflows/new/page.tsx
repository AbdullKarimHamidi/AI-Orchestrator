"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"
import { toast } from "sonner"

import { PageHeader } from "@/components/common/states"
import { newStep } from "@/components/workflows/steps"
import { WorkflowEditor } from "@/components/workflows/workflow-editor"
import { useWorkflowMutations } from "@/hooks/use-modules"
import type { WorkflowStep } from "@/lib/schemas"
import { useWorkspaceCtx } from "@/lib/workspace-context"

const STARTER = (() => {
  const answer = { ...newStep("agent", []), id: "answer", name: "Draft an answer" }
  const check = {
    ...newStep("condition", [answer]), id: "check", name: "Did the agent answer?",
    condition: { left: "{{ steps.answer.text }}", op: "not_empty" as const, right: "", case_sensitive: false },
    on_false: "fallback",
  }
  const done = { ...newStep("transform", [answer, check]), id: "format", name: "Format the reply", template: "{{ steps.answer.text }}", next: "end" }
  const fallback = { ...newStep("transform", [answer, check, done]), id: "fallback", name: "Fallback reply", template: "Sorry, no answer was produced for: {{ input.message }}" }
  return { steps: [answer, check, done, fallback], max_step_executions: 50, max_delegations: 200 }
})()

/** A lead supervisor with two sub-team supervisors, each leading three agents: an AI organisation. */
const TEAM_STARTER = (() => {
  const steps: WorkflowStep[] = []
  const add = (s: WorkflowStep) => { steps.push(s); return s }
  const director = add({ ...newStep("supervisor", steps), id: "director", name: "Project director", role: "Owns the whole project and delivers the final result.", max_rounds: 3, position: { x: 900, y: 0 } })
  const teams: [string, string, string, [string, string][]][] = [
    ["engineering", "Engineering lead", "Leads the engineers: architecture, code and tests.", [
      ["architect", "Designs the structure, data model and interfaces."], ["developer", "Writes the code."], ["tester", "Reviews the code and writes tests."]]],
    ["product", "Product lead", "Leads product work: requirements, UX and documentation.", [
      ["analyst", "Turns the idea into clear requirements and user stories."], ["designer", "Designs screens, flows and copy."], ["writer", "Writes the documentation and README."]]],
  ]
  teams.forEach(([id, name, role, members], t) => {
    const lead = add({ ...newStep("supervisor", steps), id, name, role, max_rounds: 2, position: { x: 450 + t * 900, y: 200 } })
    members.forEach(([mid, mrole], i) => {
      const m = add({ ...newStep("agent", steps), id: mid, name: mid[0].toUpperCase() + mid.slice(1), role: mrole, position: { x: 150 + t * 900 + i * 300, y: 400 } })
      lead.delegates.push(m.id)
    })
    director.delegates.push(lead.id)
  })
  director.next = "end"
  return { steps, max_step_executions: 50, max_delegations: 200 }
})()

const TEMPLATES = [
  { id: "team", label: "Agent organisation", help: "A director supervises two team leads who each delegate to three agents. Pick an agent for every node.", definition: TEAM_STARTER },
  { id: "simple", label: "Simple flow", help: "An agent answers, a condition checks the answer, and a transform formats the reply.", definition: STARTER },
] as const

export default function NewWorkflowPage() {
  const { workspaceId } = useWorkspaceCtx()
  const m = useWorkflowMutations(workspaceId)
  const router = useRouter()
  const [template, setTemplate] = useState<(typeof TEMPLATES)[number]["id"]>("team")
  const chosen = TEMPLATES.find((t) => t.id === template)!
  return (
    <div>
      <PageHeader title="New workflow" description="Start from a template, then pick an agent for each node and connect them on the canvas." />
      <div className="mb-4 grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Template">
        {TEMPLATES.map((t) => (
          <button key={t.id} type="button" role="radio" aria-checked={template === t.id} onClick={() => setTemplate(t.id)}
            className={`rounded-xl border p-4 text-left transition ${template === t.id ? "border-primary bg-accent ring-2 ring-primary/20" : "hover:bg-accent/50"}`}>
            <p className="font-medium">{t.label}</p>
            <p className="mt-1 text-sm text-muted-foreground">{t.help}</p>
          </button>
        ))}
      </div>
      <WorkflowEditor key={template} initial={{ name: "", description: "", definition: chosen.definition }} submitLabel="Create workflow"
        onSubmit={async (d) => {
          const w = await m.create.mutateAsync(d)
          toast.success("Workflow created")
          router.push(`/workflows/${w.id}`)
        }} />
    </div>
  )
}
