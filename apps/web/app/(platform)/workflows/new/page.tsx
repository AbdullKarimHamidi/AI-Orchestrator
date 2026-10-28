"use client"

import { useRouter } from "next/navigation"
import { toast } from "sonner"

import { PageHeader } from "@/components/common/states"
import { newStep } from "@/components/workflows/steps"
import { WorkflowEditor } from "@/components/workflows/workflow-editor"
import { useWorkflowMutations } from "@/hooks/use-modules"
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
  return { steps: [answer, check, done, fallback], max_step_executions: 50 }
})()

export default function NewWorkflowPage() {
  const { workspaceId } = useWorkspaceCtx()
  const m = useWorkflowMutations(workspaceId)
  const router = useRouter()
  return (
    <div>
      <PageHeader title="New workflow" description="Starts from a small template: an agent answers, a condition checks the answer, and a transform formats the reply. Pick the agent, then save." />
      <WorkflowEditor initial={{ name: "", description: "", definition: STARTER }} submitLabel="Create workflow"
        onSubmit={async (d) => {
          const w = await m.create.mutateAsync(d)
          toast.success("Workflow created")
          router.push(`/workflows/${w.id}`)
        }} />
    </div>
  )
}
