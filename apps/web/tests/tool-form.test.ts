import { describe, expect, it } from "vitest"

import { buildToolBody } from "@/components/tools/tool-form"

const base = {
  name: "get_weather", description: "Weather for a city", method: "GET", url: "https://api.example.com/w/{city}", timeout: "",
  schema: '{"type":"object","properties":{"city":{"type":"string"}}}', headers: [{ key: "Accept", value: "application/json" }, { key: " ", value: "x" }],
  secrets: [{ key: "Authorization", value: "Bearer s" }], replaceSecrets: true,
}

describe("buildToolBody", () => {
  it("builds an HTTP tool body", () => {
    const body = buildToolBody(base, "http")
    expect(body).toMatchObject({
      name: "get_weather", headers: { Accept: "application/json" }, secret_headers: { Authorization: "Bearer s" },
      http: { method: "GET", url: "https://api.example.com/w/{city}", timeout_seconds: null },
    })
  })

  it("omits secret headers unless they are being replaced", () => {
    expect(buildToolBody({ ...base, replaceSecrets: false }, "http")).not.toHaveProperty("secret_headers")
  })

  it("rejects bad names, schemas and URLs", () => {
    expect(buildToolBody({ ...base, name: "1bad" }, "http")).toMatch(/Name/)
    expect(buildToolBody({ ...base, schema: "{" }, "http")).toMatch(/not valid JSON/)
    expect(buildToolBody({ ...base, schema: '{"type":"string"}' }, "http")).toMatch(/type "object"/)
    expect(buildToolBody({ ...base, url: "ftp://x" }, "http")).toMatch(/URL/)
  })

  it("does not require a URL for MCP tools", () => {
    const body = buildToolBody({ ...base, url: "" }, "mcp")
    expect(typeof body).toBe("object")
    expect(body).not.toHaveProperty("http")
  })
})
