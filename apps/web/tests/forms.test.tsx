import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }))

import { agentFormSchema, toAgentInput, toFormValues } from "@/components/agents/agent-form"
import { AuthForm, registerSchema } from "@/components/layout/auth-form"
import { providerFormSchema } from "@/components/models/provider-dialog"
import { workspaceFormSchema } from "@/lib/schemas/forms"

import { axeViolations } from "./a11y"

const wrap = (ui: React.ReactNode) => <QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>

describe("auth form", () => {
  it("shows validation errors and does not call the API for invalid input", async () => {
    const f = vi.spyOn(globalThis, "fetch")
    render(wrap(<AuthForm mode="register" />))
    await userEvent.type(screen.getByLabelText("Email"), "not-an-email")
    await userEvent.type(screen.getByLabelText("Password"), "short")
    await userEvent.click(screen.getByRole("button", { name: "Create account" }))
    expect(await screen.findByText("Enter a valid email")).toBeInTheDocument()
    expect(screen.getByText("Use at least 12 characters")).toBeInTheDocument()
    expect(screen.getByText("Name is required")).toBeInTheDocument()
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true")
    // only the public "is registration open?" lookup may run; nothing is submitted
    expect(f.mock.calls.filter(([url]) => String(url) !== "/api/v1/auth/config")).toHaveLength(0)
  })

  it("surfaces server errors from the API", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ error: { code: "INVALID_CREDENTIALS", message: "Invalid email or password" } }), { status: 401 }))
    render(wrap(<AuthForm mode="login" />))
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com")
    await userEvent.type(screen.getByLabelText("Password"), "whatever-password")
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }))
    expect(await screen.findByText("Invalid email or password")).toBeInTheDocument()
  })

  it("never submits credentials via GET (method=post guards pre-hydration submits)", () => {
    const { container } = render(wrap(<AuthForm mode="login" />))
    expect(container.querySelector("form")).toHaveAttribute("method", "post")
  })

  it("has no axe violations", async () => {
    const { container } = render(wrap(<AuthForm mode="register" />))
    expect(await axeViolations(container)).toEqual([])
  })

  it("register schema enforces password length", () => {
    expect(registerSchema.safeParse({ name: "A", email: "a@b.co", password: "x".repeat(11), workspace_name: "W" }).success).toBe(false)
    expect(registerSchema.safeParse({ name: "A", email: "a@b.co", password: "x".repeat(12), workspace_name: "W" }).success).toBe(true)
  })
})

describe("agent form schema", () => {
  const valid = { ...toFormValues("Agent", ""), provider_id: "prv_1", model: "demo-echo" }

  it("accepts defaults and converts to the API shape", () => {
    const parsed = agentFormSchema.safeParse(valid)
    expect(parsed.success).toBe(true)
    const input = toAgentInput({ ...valid, temperature: "0.5", input_schema: '{"type":"object"}' })
    expect(input.config.params).toEqual({ temperature: 0.5, top_p: null, max_output_tokens: 1024 })
    expect(input.config.input_schema).toEqual({ type: "object" })
    expect(input.config.limits.timeout_seconds).toBe(120)
  })

  it("rejects bad numbers, invalid JSON schema, and missing model", () => {
    const r = agentFormSchema.safeParse({ ...valid, temperature: "3", input_schema: "[1]", model: " ", timeout_seconds: "1" })
    expect(r.success).toBe(false)
    const paths = r.error!.issues.map((i) => i.path.join("."))
    expect(paths).toEqual(expect.arrayContaining(["temperature", "input_schema", "model", "timeout_seconds"]))
  })

  it("round-trips an existing config without losing tool and knowledge assignments", () => {
    const base = toAgentInput(valid).config
    const withTools = { ...base, tool_ids: ["tool_1"], knowledge_base_ids: ["kb_1"] }
    const again = toAgentInput(toFormValues("Agent", "", withTools), withTools)
    expect(again.config.tool_ids).toEqual(["tool_1"])
    expect(again.config.knowledge_base_ids).toEqual(["kb_1"])
  })
})

describe("provider and workspace schemas", () => {
  it("requires an API key for hosted providers and a base URL for compatible ones", () => {
    const base = { name: "P", api_key: "", base_url: "", allowed_models: "", timeout_seconds: "60" }
    expect(providerFormSchema.safeParse({ ...base, kind: "openai" }).success).toBe(false)
    expect(providerFormSchema.safeParse({ ...base, kind: "openai", api_key: "sk-x" }).success).toBe(true)
    expect(providerFormSchema.safeParse({ ...base, kind: "openai_compatible" }).success).toBe(false)
    expect(providerFormSchema.safeParse({ ...base, kind: "openai_compatible", base_url: "http://localhost:11434/v1" }).success).toBe(true)
  })

  it("validates the budget field", () => {
    expect(workspaceFormSchema.safeParse({ name: "W", budget: "" }).success).toBe(true)
    expect(workspaceFormSchema.safeParse({ name: "W", budget: "12.50" }).success).toBe(true)
    expect(workspaceFormSchema.safeParse({ name: "W", budget: "-1" }).success).toBe(false)
    expect(workspaceFormSchema.safeParse({ name: "W", budget: "abc" }).success).toBe(false)
  })
})

describe("invitation and closed registration", () => {
  it("hides the workspace field and locks the email when registering from an invitation", async () => {
    render(wrap(<AuthForm mode="register" invite={{ token: "tok_abcdefghij", email: "new@example.com", role: "developer", workspace_name: "Acme", expires_at: "2030-01-01T00:00:00Z", has_account: false }} />))
    expect(screen.getByText("Join Acme as developer.")).toBeInTheDocument()
    expect(screen.queryByLabelText("Workspace name")).not.toBeInTheDocument()
    expect(screen.getByLabelText("Email")).toHaveValue("new@example.com")
    expect(screen.getByLabelText("Email")).toHaveAttribute("readonly")
  })

  it("explains that registration is closed", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({ registration_open: false, demo_mode: true }), { status: 200 }))
    render(wrap(<AuthForm mode="register" />))
    expect(await screen.findByText("Registration is closed")).toBeInTheDocument()
  })
})
