import { expect, test } from "@playwright/test"

/** Team onboarding through the UI: invite link, invitee registration, API key, password change. */
test("team onboarding (invite, API key, password)", async ({ page, browser }) => {
  const stamp = Date.now()
  const owner = `owner-${stamp}@example.com`
  const mate = `mate-${stamp}@example.com`
  const pw = "correct-horse-battery-staple"

  await test.step("owner registers", async () => {
    await page.goto("/register")
    await page.getByLabel("Your name").fill("Owner")
    await page.getByLabel("Email").fill(owner)
    await page.getByLabel("Password").fill(pw)
    await page.getByLabel("Workspace name").fill("Team WS")
    await page.getByRole("button", { name: "Create account" }).click()
    await expect(page).toHaveURL(/\/dashboard/)
  })

  let link = ""
  await test.step("owner creates an invitation link", async () => {
    await page.goto("/security/users")
    await page.locator("#inv-email").fill(mate)
    await page.locator("#inv-role").selectOption("developer")
    await page.getByRole("button", { name: "Create invitation link" }).click()
    const field = page.getByLabel("Invitation link", { exact: true })
    await expect(field).toBeVisible()
    link = await field.inputValue()
    expect(link).toContain("/invite/")
    await expect(page.getByRole("cell", { name: mate })).toBeVisible()
  })

  await test.step("teammate registers through the link and lands in the workspace", async () => {
    const ctx = await browser.newContext()
    const p2 = await ctx.newPage()
    await p2.goto(new URL(link).pathname)
    await expect(p2.getByText("Join Team WS as developer.")).toBeVisible()
    await expect(p2.getByLabel("Workspace name")).toHaveCount(0)
    await p2.getByLabel("Your name").fill("Mate")
    await p2.getByLabel("Password").fill(pw)
    await p2.getByRole("button", { name: "Create account" }).click()
    await expect(p2).toHaveURL(/\/dashboard/)
    await expect(p2.locator("#ws-switch option:checked")).toHaveText("Team WS")
    await ctx.close()
  })

  await test.step("owner creates an API key that works without a browser session", async () => {
    await page.goto("/settings/api-keys")
    await page.getByLabel("Name").fill("e2e key")
    await page.getByRole("button", { name: "Create key" }).click()
    const key = await page.getByLabel("New API key").inputValue()
    expect(key).toMatch(/^orch_/)
    const res = await page.request.get("/api/v1/agents", { headers: { Authorization: `Bearer ${key}` } })
    expect(res.status()).toBe(200)
  })

  await test.step("owner changes the password", async () => {
    await page.goto("/settings/account")
    await page.getByLabel("Current password").fill(pw)
    await page.getByLabel("New password", { exact: true }).fill("another-long-password")
    await page.getByLabel("Repeat new password").fill("another-long-password")
    await page.getByRole("button", { name: "Change password" }).click()
    await expect(page.getByText(/Password changed/)).toBeVisible()
  })
})
