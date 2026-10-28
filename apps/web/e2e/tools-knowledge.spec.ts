import { expect, test } from "@playwright/test"

/** Knowledge base → agent with retrieval → cited answer; plus HTTP tool registration. Demo mode, no external calls. */
test("knowledge-grounded agent and tool registry", async ({ page }) => {
  const stamp = Date.now()
  const kbName = `Handbook ${stamp}`

  await test.step("register", async () => {
    await page.goto("/register")
    await page.getByLabel("Your name").fill("KB User")
    await page.getByLabel("Email").fill(`kb-${stamp}@example.com`)
    await page.getByLabel("Password").fill("correct-horse-battery-staple")
    await page.getByLabel("Workspace name").fill("KB WS")
    await page.getByRole("button", { name: "Create account" }).click()
    await expect(page).toHaveURL(/\/dashboard/)
  })

  await test.step("create a knowledge base and index a pasted document", async () => {
    await page.goto("/knowledge/bases")
    await page.getByLabel("Name", { exact: true }).fill(kbName)
    await page.getByRole("button", { name: "Create knowledge base" }).click()
    await expect(page.getByRole("heading", { name: kbName })).toBeVisible()
    await page.getByLabel("Title").fill("Refund policy")
    await page.getByLabel("Text", { exact: true }).fill("Refunds are processed within 14 days of the return arriving at our warehouse.\n\nShipping is free for orders over 50 euros.")
    await page.getByRole("button", { name: "Add text" }).click()
    await expect(page.getByRole("cell", { name: /^Refund policy/ })).toBeVisible()
    await expect(page.getByText("ready", { exact: true })).toBeVisible({ timeout: 30_000 })
    await page.getByLabel("Search query").fill("how long do refunds take")
    await page.getByRole("button", { name: "Search" }).click()
    await expect(page.getByLabel("Search results").getByText(/within 14 days/)).toBeVisible()
  })

  await test.step("an agent with the knowledge base answers with citations", async () => {
    await page.goto("/agents/new")
    await page.getByLabel("Name", { exact: true }).fill(`Support ${stamp}`)
    await page.locator("#models-primary-model").fill("demo-echo")
    await page.getByLabel(kbName).check()
    await page.getByRole("button", { name: "Create agent" }).click()
    await expect(page.getByRole("heading", { name: `Support ${stamp}` })).toBeVisible()
    const agentId = page.url().split("/agents/")[1].split(/[/?#]/)[0]
    await page.goto(`/agents/${agentId}/test`)
    await page.getByLabel("Message").fill("When do I get my refund?")
    await page.getByRole("button", { name: "Run" }).click()
    await expect(page.getByText(/Retrieved context/)).toBeVisible({ timeout: 30_000 })
    await expect(page.getByLabel("Sources").getByRole("link", { name: "Refund policy" })).toBeVisible()
    await expect(page.getByLabel("Run events").getByText("knowledge.retrieved")).toBeVisible()
  })

  await test.step("register an HTTP tool and assign it to the agent", async () => {
    await page.goto("/tools/new")
    await page.getByLabel("Name", { exact: true }).fill("get_weather")
    await page.getByLabel("Description", { exact: true }).fill("Current weather for a city")
    await page.getByLabel("URL", { exact: true }).fill("https://api.example.com/weather/{city}")
    await page.getByRole("button", { name: "Create tool" }).click()
    await expect(page.getByRole("heading", { name: "get_weather" })).toBeVisible()
    await page.goto("/tools")
    await expect(page.getByRole("link", { name: "get_weather" })).toBeVisible()
    await page.goto("/agents/new")
    await expect(page.getByLabel(/get_weather/)).toBeVisible()
  })
})
