# Implementation Prompt: AI-Orchestrator Project Creator and Supervised Parallel AI Teams

You are a senior staff-level full-stack engineer, distributed-systems architect, product designer, and test engineer working directly in the existing AI-Orchestrator repository. Implement this as a production-quality extension of the current codebase—not as a mockup, demo-only page, disconnected prototype, or rewrite.

## First: inspect and preserve

Before editing, inspect the repository, current workflows, agent lifecycle, provider gateway, durable run queue, worker, SSE run events, MongoDB repositories/indexes, RBAC, workspace isolation, frontend design system, CI, and tests. Reuse existing abstractions. Do not replace MongoDB, FastAPI, Next.js, the worker, or the existing agent/run model. Preserve existing routes and behavior unless a verified defect requires a targeted fix.

Never claim a feature works unless it is connected end-to-end and verified by tests. Never hide errors behind successful UI states.

## Product outcome

Build a Project Creator where a user can describe a project, choose existing AI agents to plan it, review and revise planning documents, then configure a team of any practical size to work on implementation in parallel. Three configurable supervisor agents must continuously evaluate progress against the approved plan and coordinate corrective work. The user must remain able to steer the work at any time.

## A. Workflow Studio redesign and reliability

- Upgrade the visual hierarchy, spacing, node cards, route indicators, step-type badges, editor/preview layout, empty states, responsive layout, and accessibility.
- Keep visual editing and JSON editing synchronized. Invalid JSON must never silently replace the last valid definition.
- Show actionable validation errors at the top and near relevant steps. Validate missing references, duplicate IDs, reserved IDs, invalid routes, unpublishable agents, and invalid tool/knowledge references.
- Preserve immutable published versions, optimistic concurrency, draft-vs-published behavior, worker-based execution, cancellation, retries, SSE events, and run inspection.
- Improve workflow listing with search, meaningful status and version visibility, and clear empty/loading/error states.
- Test add/edit/reorder/remove steps, conditions and branch routes, JSON parse errors, validation, save conflicts, publish, execution, failure display, and mobile keyboard navigation.

## B. Project Creator user journey

1. Create a project with name, detailed idea, constraints, desired stack, target users, and acceptance criteria.
2. Select one or two existing published planning agents. Show model/provider readiness and clear reasons when an agent cannot run.
3. Queue planning agents concurrently using the existing durable queue. Never run long model requests synchronously inside an HTTP request.
4. Save generated outputs as durable project documents. The UI must poll/stream run status, prevent duplicate documents, and distinguish queued, running, completed, failed, and cancelled.
5. Provide a document workspace: select, create, edit, autosave or explicitly save, compare revisions, add comments/feedback, request revisions, and approve/reopen documents. Never overwrite an approved version without preserving the previous version.
6. The user may add feedback at any point. Planning agents must receive the current idea, approved plan, relevant documents, latest edits, and feedback for every revision.
7. Keep project history: document versions, user decisions, agent runs, supervisor decisions, tasks, changes, and test evidence.

## C. Configurable specialist teams

- Let the user create any number of named teams and assign as many existing agents as desired.
- Example team configurations: 5 UI/UX agents, 5 frontend agents, 5 backend/database agents, 3 QA/log/error-fixing agents, plus security, performance, DevOps, documentation, or custom teams.
- Each team has purpose, selected agents, parallelism cap, allowed scope, output contract, and acceptance criteria.
- Team size and concurrency are separate settings. Respect per-workspace budgets, provider limits, rate limits, and global concurrency caps.
- A team manager agent breaks the approved plan into small tasks, assigns each task to a specific specialist, tracks dependencies, and reassigns blocked work.
- Tasks need durable status, attempts, lease/claim semantics, dependencies, timestamps, logs, output/artifacts, errors, review status, and cancellation/retry controls.
- Agents must receive a stable shared project context and the precise task scope, but must not be able to modify unrelated tasks or project configuration.

## D. Parallel execution and code-change safety

- Use the existing worker/run infrastructure where possible; add a durable scheduler rather than spawning untracked background asyncio tasks from request handlers.
- Run independent tasks concurrently, while tasks with dependencies wait. Make the concurrency cap visible to the user.
- For code tasks, each agent must produce a scoped patch or work in an isolated branch/worktree. Do not allow concurrent writes to the same files without a conflict strategy.
- Integrate results through a review stage: detect conflicts, run formatting/type checks/tests, and require approval for risky changes or external side effects.
- Keep artifacts, diffs, logs, and test evidence available to the user.
- Add bounded retries, idempotency, stale-worker recovery, cancellation, timeout, spend limits, and protection from infinite supervisor loops.
- Do not mark a task complete because an agent says it is complete; require verifiable output and acceptance checks.

## E. Three configurable supervisory agents

The user chooses existing published agents for these roles, with clear prompts, tools, permissions, and cadence:

1. **Plan Compliance Supervisor** compares current tasks, outputs, diffs, tests, and milestones against the approved documents. It identifies drift and proposes concrete corrective tasks.
2. **Team Coordination Supervisor** checks assignment coverage, workload, blocked/stale tasks, dependencies, duplicate work, and safe parallelism. It routes tasks to the relevant team manager.
3. **Quality and Reliability Supervisor** inspects test results, logs, exceptions, security findings, regressions, and output quality. It creates targeted fixes and requires failed checks to be rerun.

Supervisors must operate on persisted evidence, explain their decisions, and create traceable corrective tasks. They must not rewrite approved plans or silently expand scope. The user can pause supervisors, change their instructions, approve/reject corrective tasks, and stop a project. Bound review cycles and escalate to the user when agents disagree or repeat failures.

## F. API, persistence, and security

- Keep every project, document, task, run, artifact, and agent assignment scoped to the authenticated workspace. Test cross-workspace access denial for every endpoint.
- Use Pydantic request/response schemas, Zod validation, repository/service/router separation, audit records, and optimistic revision checks.
- Add MongoDB indexes and validators idempotently; handle concurrent updates and duplicate requests safely.
- Apply RBAC permissions consistently to project creation, document editing, task assignment, run creation, approval, cancellation, and supervisor configuration.
- Never expose provider secrets, credentials, raw exception internals, or another workspace's data.
- Make migrations/backward compatibility explicit. Do not change existing stored data formats without a migration path.

## G. UI/UX

- Use the existing design system and light/dark themes. Keep the application consistent rather than introducing a disconnected visual language.
- Create an intuitive project overview, project detail workspace, document editor, team builder, task board, activity timeline, supervisor panel, and review/approval queue.
- Show team/task status, active agent runs, concurrency, blocked dependencies, errors, latest test results, plan drift, and corrective actions.
- Provide responsive desktop/mobile layouts, keyboard navigation, accessible labels, confirmation for destructive actions, clear empty/loading/error states, and optimistic feedback only when the server confirms success.
- Make user feedback available while work is running, and record whether a change affects the plan, a document, or active tasks.

## H. Required testing before declaring complete

Run and fix all relevant checks:
- API: Ruff, schema tests, service/repository tests, API integration tests, workspace isolation/RBAC tests, concurrency/idempotency tests, task scheduler tests, worker lease/recovery tests, supervisor loop-bound tests.
- Web: typecheck, lint, Vitest, component/accessibility tests, form validation tests, error/loading/empty-state tests.
- End-to-end: create project → run two planning agents concurrently → inspect/edit/approve documents → configure teams → create dependent tasks → run independent tasks in parallel → inject a failure → supervisor detects it → corrective task runs → tests pass → project completion is evidence-based.
- Verify workflow create/edit/validate/publish/run/history and regression test existing features.
- Test with a deterministic provider for repeatability, and separately document any real-provider tests that require external credentials.
- Run production build and E2E tests. Fix regressions before calling the work done. Summarize exact commands and results; never fabricate passing checks.

## Delivery discipline

Implement in small, reviewable phases while keeping the branch usable:
1. Workflow Studio reliability and visual polish.
2. Durable Project Creator, planning runs, editable/versioned documents, and user feedback.
3. Team/task scheduler with safe parallel execution and task board.
4. Three supervisory agents, evidence-based plan drift detection, and bounded corrective loops.
5. End-to-end, security, accessibility, concurrency, and failure-injection tests.

Create and work on a feature branch; never commit directly to main. Preserve unrelated user changes. Do not commit secrets or real .env files. Open a pull request for review. If the repository connection cannot run local commands, use CI and clearly report any tests that remain unverified.

## Definition of done

The feature is done only when the complete user journey works against the real API and MongoDB, state survives reloads, parallelism is durable and bounded, document revisions/feedback persist, supervisor decisions are auditable, tasks are verified by evidence, security and regression tests pass, and CI is green. Anything not yet implemented must be clearly labeled as planned—not presented as functional.
