import { describe, expect, it, vi } from "vitest"
import { z } from "zod"

import { api, ApiError, errorMessage, setWorkspaceId, streamUrl } from "@/lib/api-client"

function mockFetch(status: number, body: unknown) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  )
}

describe("api client", () => {
  it("sends workspace and CSRF headers on mutations, and only workspace on GET", async () => {
    document.cookie = "orch_csrf=tok123; path=/"
    setWorkspaceId("ws_abc")
    const f = mockFetch(200, { ok: true })
    await api.post("/agents", z.object({ ok: z.boolean() }), { name: "x" })
    const [url, init] = f.mock.calls[0]
    expect(url).toBe("/api/v1/agents")
    const h = init!.headers as Record<string, string>
    expect(h["X-CSRF-Token"]).toBe("tok123")
    expect(h["X-Workspace-Id"]).toBe("ws_abc")
    expect(init!.credentials).toBe("same-origin")
    expect(JSON.parse(init!.body as string)).toEqual({ name: "x" })

    f.mockClear()
    f.mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))
    await api.get("/agents", z.object({ ok: z.boolean() }), { query: { q: "a b", status: undefined } })
    const [url2, init2] = f.mock.calls[0]
    expect(url2).toBe("/api/v1/agents?q=a+b")
    expect((init2!.headers as Record<string, string>)["X-CSRF-Token"]).toBeUndefined()
  })

  it("maps the backend error envelope to ApiError", async () => {
    mockFetch(404, { error: { code: "WORKSPACE_NOT_FOUND", message: "Workspace not found", details: {}, correlation_id: "c1" } })
    const err = await api.get("/agents", z.any()).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(404)
    expect(err.code).toBe("WORKSPACE_NOT_FOUND")
    expect(err.correlationId).toBe("c1")
    expect(errorMessage(err)).toBe("Workspace not found")
  })

  it("rejects responses that violate the contract", async () => {
    mockFetch(200, { id: 5 })
    const err = await api.get("/x", z.object({ id: z.string() })).catch((e) => e)
    expect(err.code).toBe("CONTRACT_MISMATCH")
  })

  it("reports network failures clearly", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"))
    const err = await api.get("/x", z.any()).catch((e) => e)
    expect(err.code).toBe("NETWORK_ERROR")
  })

  it("handles 204 responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }))
    await expect(api.delete("/agents/a1")).resolves.toBeUndefined()
  })

  it("puts the workspace into SSE URLs because EventSource cannot set headers", () => {
    setWorkspaceId("ws_9")
    expect(streamUrl("/runs/r1/stream", 3)).toBe("/api/v1/runs/r1/stream?after=3&workspace_id=ws_9")
  })
})
