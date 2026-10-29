# Project Creator and Supervised Parallel Teams

## Product goal

Turn AI-Orchestrator into a user-directed AI project delivery workspace. Preserve existing agent, workflow, provider, run, and workspace contracts. Project-specific state belongs in MongoDB and is always scoped to the authenticated workspace.

## User journey

1. Create a project with a name, plain-language idea, constraints, and expected outcome.
2. Select one or two already-published planning agents. They run concurrently against the same project brief.
3. Review generated planning documents. Edit the content, add feedback, and ask the planning agents to revise it. Keep revision history and approval state so a user can see what changed.
4. Configure any number of specialist teams. Each team has a purpose, a list of selected agents, a concurrency limit, and task boundaries. Examples: five UI/UX agents, five backend/database agents, and three QA/log-fixing agents.
5. Assign the project to the team and start execution only after the user approves the plan.
6. Show a live board for queued, running, blocked, review-needed, completed, and failed work. Users can pause, retry, reassign, or cancel tasks.

## Supervisor responsibilities

- **Project supervisor:** compares implementation evidence against the approved plan and acceptance criteria; records drift and proposes corrective tasks.
- **Coordination supervisor:** balances the queue, respects dependencies, prevents duplicate ownership, detects stalled tasks, and routes work to the right team.
- **Quality supervisor:** reviews tests, logs, error reports, and changed files; failed checks create corrective tasks instead of silently passing.

Supervisors are agents selected by the user, not hidden hard-coded model calls. The platform must show their input, decisions, task creation, and results.

## Parallel execution and safety invariants

- Use the existing durable worker queue and run/event system; do not run long model calls inside HTTP request handlers.
- Persist each task, assigned agent, attempt, status, dependencies, output, and timestamps in MongoDB.
- Enforce workspace isolation for projects, documents, tasks, agents, and run references.
- Use optimistic concurrency for project/document editing and lease/claim semantics for tasks.
- Never allow two tasks to write the same file concurrently without an explicit dependency or conflict-resolution strategy. Prefer isolated worktrees/patches and a review/integration stage for code changes.
- A task must declare its output contract, allowed scope, acceptance criteria, and evidence. Supervisors should check evidence, not rely only on an agent's self-report.
- Limit team parallelism, model spend, task retries, and total project budget. Provide pause/cancel controls.
- User edits and feedback are durable inputs to every subsequent revision. Do not overwrite approved documents without creating a new revision.
- A supervisor can suggest or queue corrective work, but destructive changes and external side effects require policy checks and explicit approval where configured.

## Workflow Studio quality goals

- Make the step sequence and branching easy to scan; clearly distinguish agent, tool, knowledge, transform, and condition nodes.
- Keep visual and JSON editors synchronized and show parse/validation errors without losing the last valid draft.
- Validate all step references and publishability before publishing; explain each problem next to the relevant step.
- Provide a clear execution preview, route labels, loop guard, accessible controls, responsive behavior, and an actionable empty state.
- Keep current run streaming, worker execution, workflow versioning, and published-vs-draft semantics intact.

## Delivery phases

### Phase 1 — durable project planning
- Workspace-scoped project CRUD and revision checks.
- Choose one or two published planning agents.
- Queue planning runs concurrently through the existing worker queue.
- Poll run state and persist completed outputs as reviewable documents.
- Edit documents and save feedback/status in MongoDB.

### Phase 2 — configurable specialist execution
- Durable task/team models, dependency graph, scheduler, leases, retries, cancellation, and audit events.
- Configurable parallelism and per-agent assignments.
- Output patches/artifacts and conflict-safe integration.

### Phase 3 — supervisory feedback loop
- Three configurable supervisory roles.
- Periodic plan-vs-evidence checks, log/test review, drift detection, corrective task creation, and bounded retry loops.
- Human approval gates and complete decision traces.

### Phase 4 — verification and polish
- Unit/integration/API/UI/e2e tests, permission and tenant-isolation tests, concurrency tests, failure-injection tests, accessibility checks, and production build.
- Test real provider-backed runs separately from deterministic/demo-mode tests. Report unavailable external dependencies rather than marking them passed.

## Acceptance checklist

- Project creation rejects unpublished or cross-workspace agent IDs.
- One or two planning agents are queued concurrently and their outputs become documents once, without duplicate document creation on repeated reads.
- Feedback and document edits persist across reloads and stale revisions return a conflict.
- Every project/task/document/run lookup is workspace-scoped.
- Workflow visual/JSON editing, step reorder/remove, graph validation, publish, run, and error states have automated regression coverage.
- A green test result is required before a feature is called complete.
