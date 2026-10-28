import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { EmptyState, ErrorState, InDevelopment } from "@/components/common/states"
import { DemoBadge, StatusBadge } from "@/components/common/status-badge"
import { RunTimeline } from "@/components/runs/run-timeline"
import { RunsTable } from "@/components/runs/runs-table"
import { ApiError } from "@/lib/api-client"
import { breadcrumbsFor, NAV_SECTIONS } from "@/lib/nav"
import type { Run } from "@/lib/schemas"
import { can } from "@/lib/workspace-context"

import { axeViolations } from "./a11y"

const run: Run = {
  id: "run_0123456789abcdef", agent_id: "agt_1", agent_name: "Support bot", agent_version: 2, source: "published",
  status: "completed", demo: true, input: { message: "hi" }, output: { text: "[DEMO] hi" }, error: null,
  usage: { input_tokens: 10, output_tokens: 5, cost_usd: 0 }, attempt: 1, max_attempts: 2, timeout_seconds: 120,
  cancel_requested: false, created_at: new Date().toISOString(), started_at: null, finished_at: null, duration_ms: 1500,
  config: {},
} as unknown as Run

describe("status and demo badges", () => {
  it("renders human-readable status", () => {
    render(<StatusBadge status="waiting_for_approval" />)
    expect(screen.getByText("waiting for approval")).toBeInTheDocument()
  })
  it("labels demo output", () => {
    render(<DemoBadge />)
    expect(screen.getByText("DEMO")).toHaveAttribute("title", expect.stringContaining("No model was called"))
  })
})

describe("states", () => {
  it("InDevelopment renders no interactive controls besides navigation links", async () => {
    const { container } = render(<InDevelopment title="Tools" summary="s" planned={["a", "b"]} related={[{ href: "/models", label: "Models" }]} />)
    expect(screen.getByText("In development")).toBeInTheDocument()
    expect(container.querySelectorAll("button, input, select, textarea")).toHaveLength(0)
    expect(screen.getByRole("link", { name: "Models" })).toHaveAttribute("href", "/models")
    expect(await axeViolations(container)).toEqual([])
  })
  it("ErrorState shows the API message and correlation id", () => {
    render(<ErrorState error={new ApiError(500, "INTERNAL", "Boom", {}, "corr-1")} />)
    expect(screen.getByText(/Boom/)).toBeInTheDocument()
    expect(screen.getByText(/corr-1/)).toBeInTheDocument()
  })
  it("EmptyState renders title", () => {
    render(<EmptyState title="Nothing here" />)
    expect(screen.getByText("Nothing here")).toBeInTheDocument()
  })
})

describe("runs", () => {
  it("table links to the run inspector and shows demo marker", async () => {
    const { container } = render(<RunsTable runs={[run]} />)
    expect(screen.getByRole("link")).toHaveAttribute("href", "/runs/run_0123456789abcdef")
    expect(screen.getByText("DEMO")).toBeInTheDocument()
    expect(screen.getByText("v2")).toBeInTheDocument()
    expect(screen.getByText("Support bot")).toBeInTheDocument()
    expect(await axeViolations(container)).toEqual([])
  })
  it("timeline summarises model events", () => {
    render(<RunTimeline events={[
      { seq: 1, type: "model.error", ts: new Date().toISOString(), data: { slot: "primary", kind: "timeout", message: "took too long", will_fallback: true } },
      { seq: 2, type: "model.response", ts: new Date().toISOString(), data: { slot: "fallback_1", input_tokens: 3, output_tokens: 4, latency_ms: 20, priced: false } },
    ] as never} />)
    expect(screen.getByText(/primary: timeout — took too long · trying fallback/)).toBeInTheDocument()
    expect(screen.getByText(/fallback_1: 3 in \/ 4 out · 20 ms · unpriced/)).toBeInTheDocument()
  })
})

describe("navigation and permissions", () => {
  it("every nav entry declares an honest status", () => {
    for (const s of NAV_SECTIONS) for (const i of s.items) expect(["available", "partial", "in_development"]).toContain(i.status)
  })
  it("breadcrumbs", () => {
    expect(breadcrumbsFor("/agents/agt_1/versions").map((c) => c.label)).toEqual(["Agents", "agt_1", "Versions"])
  })
  it("display-only RBAC mirror matches key backend rules", () => {
    expect(can("viewer", "agents:write")).toBe(false)
    expect(can("developer", "agents:write")).toBe(true)
    expect(can("operator", "runs:cancel")).toBe(true)
    expect(can("developer", "members:manage")).toBe(false)
    expect(can("owner", "members:manage")).toBe(true)
  })
})
