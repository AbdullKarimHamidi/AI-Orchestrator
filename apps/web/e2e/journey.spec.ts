import { expect, test } from "@playwright/test"

/**
 * The 10-step journey from the engineering brief, executed against the real stack in demo mode
 * (no paid provider needed). Steps 6–7 build a workflow around the published agent and run it.
 */
test("enterprise journey (demo mode)", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`
  const agentName = `E2E agent ${Date.now()}`
  let agentId = ""
  let runId = ""
  // API assertions reuse the browser session cookie; the workspace header mirrors what the UI sends.
  const apiGet = async (path: string) => {
    const ws = await page.evaluate(() => window.localStorage.getItem("orch.workspace_id"))
    const res = await page.request.get(`/api/v1${path}`, { headers: { "X-Workspace-Id": ws ?? "" } })
    expect(res.ok(), `${path} -> ${res.status()}`).toBeTruthy()
    return res.json()
  }

  await test.step("1. user authenticates (register, sign out, sign in)", async () => {
    await page.goto("/register")
    await page.getByLabel("Your name").fill("E2E User")
    await page.getByLabel("Email").fill(email)
    await page.getByLabel("Password").fill("correct-horse-battery-staple")
    await page.getByLabel("Workspace name").fill("E2E Workspace")
    await page.getByRole("button", { name: "Create account" }).click()
    await expect(page).toHaveURL(/\/dashboard/)
    await page.getByRole("button", { name: /sign out/i }).click()
    await expect(page).toHaveURL(/\/login/)
    await page.getByLabel("Email").fill(email)
    await page.getByLabel("Password").fill("correct-horse-battery-staple")
    await page.getByRole("button", { name: "Sign in" }).click()
    await expect(page).toHaveURL(/\/dashboard/)
  })

  await test.step("2. user has a selected workspace", async () => {
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible()
    const ws = page.locator("#ws-switch")
    await expect(ws).toBeVisible()
    await expect(ws.locator("option:checked")).toHaveText("E2E Workspace")
  })

  await test.step("3–4. user creates an agent and configures a supported model", async () => {
    await page.goto("/models")
    await expect(page.getByText("Demo (synthetic, no real model)")).toBeVisible()
    await page.goto("/agents/new")
    await page.getByLabel("Name", { exact: true }).fill(agentName)
    await page.locator("#models-primary-provider").selectOption({ label: "Demo (synthetic, no real model) (demo)" })
    await page.locator("#models-primary-model").fill("demo-echo")
    // invalid input is rejected client-side before reaching the API
    await page.getByLabel("Temperature (0–2)").fill("5")
    await page.getByRole("button", { name: "Create agent" }).click()
    await expect(page.getByText("Must be between 0 and 2")).toBeVisible()
    await page.getByLabel("Temperature (0–2)").fill("0.2")
    await page.getByRole("button", { name: "Create agent" }).click()
    await expect(page).toHaveURL(/\/agents\/agt_/)
    agentId = page.url().split("/agents/")[1].split(/[/?#]/)[0]
    await expect(page.getByRole("heading", { name: agentName })).toBeVisible()
  })

  await test.step("5. user tests the agent (draft) and sees live events", async () => {
    await page.goto(`/agents/${agentId}/test`)
    await page.getByLabel("Message").fill("hello from playwright")
    await page.getByRole("button", { name: "Run" }).click()
    await expect(page.getByText(/Echo: hello from playwright/)).toBeVisible()
    await expect(page.getByLabel("Run events").getByText("run.completed")).toBeVisible()
  })

  await test.step("10a. user publishes v1", async () => {
    await page.goto(`/agents/${agentId}`)
    await page.getByRole("button", { name: "Publish v1" }).click()
    await page.getByRole("dialog").getByRole("button", { name: "Publish" }).click()
    await expect(page.getByText("Version published")).toBeVisible()
  })

  await test.step("10b. editing the draft does not change published v1", async () => {
    await page.goto(`/agents/${agentId}/edit`)
    await page.getByLabel("System prompt").fill("A different draft prompt")
    await page.getByRole("button", { name: "Save draft" }).click()
    await expect(page).toHaveURL(new RegExp(`/agents/${agentId}$`))
    const versions = await apiGet(`/agents/${agentId}/versions`)
    expect(versions).toHaveLength(1)
    expect(versions[0].config.system_prompt).not.toBe("A different draft prompt")
  })

  await test.step("6–7. user builds a workflow around the published agent and runs it", async () => {
    await page.goto("/workflows/new")
    await page.getByLabel("Name", { exact: true }).fill(`${agentName} pipeline`)
    await page.locator("#step-0-agent").selectOption(agentId)
    await page.getByRole("button", { name: "Create workflow" }).click()
    await expect(page).toHaveURL(/\/workflows\/wfl_/)
    await page.getByRole("button", { name: "Publish" }).click()
    await expect(page.getByText("Published a new version")).toBeVisible()
    await page.getByLabel("Message", { exact: true }).fill("workflow from playwright")
    await page.getByRole("button", { name: "Run workflow" }).click()
    await expect(page.getByLabel("Executed steps")).toBeVisible()
    await expect(page.getByLabel("Executed steps").getByText("answer")).toBeVisible()
  })

  await test.step("8. user runs published v1 and inspects events and results", async () => {
    await page.goto(`/agents/${agentId}/test`)
    await page.getByLabel(/Published v1/).check()
    await page.getByLabel("Message").fill("reproducible?")
    await page.getByRole("button", { name: "Run" }).click()
    await expect(page.getByText(/Echo: reproducible\?/)).toBeVisible()
    await page.goto("/runs")
    await page.getByRole("row", { name: new RegExp(agentName) }).filter({ hasNotText: "workflow" }).getByRole("link", { name: /^run_/ }).first().click()
    await expect(page).toHaveURL(/\/runs\/run_/)
    runId = page.url().split("/runs/")[1]
    await expect(page.getByText("Executed configuration (snapshot)")).toBeVisible()
    await expect(page.locator("dt", { hasText: "Config" }).locator("+ dd")).toHaveText("v1")
    const run = await apiGet(`/runs/${runId}`)
    expect(run.agent_version).toBe(1)
    expect(run.config.system_prompt).not.toBe("A different draft prompt")
  })

  await test.step("9. user reviews usage and cost", async () => {
    await page.goto("/models")
    await expect(page.getByRole("cell", { name: "demo-echo" })).toBeVisible()
    await page.goto("/dashboard")
    await expect(page.getByText(/used the Demo provider/)).toBeVisible()
    await page.goto("/security/audit")
    await expect(page.getByText("agent.publish").first()).toBeVisible()
  })
})
