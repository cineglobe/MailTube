import { expect, test } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"

test("login is keyboard-accessible", async ({ page }) => {
  await page.goto("/login/")
  await expect(
    page.getByRole("heading", { name: /your media stays yours/i })
  ).toBeVisible()
  await page.getByLabel("Username").focus()
  await expect(page.getByLabel("Username")).toBeFocused()
  await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible()
  const results = await new AxeBuilder({ page }).analyze()
  expect(
    results.violations.filter((violation) =>
      ["critical", "serious"].includes(violation.impact ?? "")
    )
  ).toEqual([])
})

test("one successful login opens the dashboard and theme toggle works", async ({
  page,
}) => {
  const session = {
    username: "admin",
    csrf_token: "test-csrf",
    expires_at: "2099-01-01T00:00:00Z",
  }
  await page.route("**/api/v1/auth/login", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(session),
    })
  })
  await page.route("**/api/v1/auth/session", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(session),
    })
  })

  await page.goto("/login/")
  await page.getByLabel("Password").fill("correct horse battery")
  await page.getByRole("button", { name: /sign in/i }).click()

  await expect(page).toHaveURL(/\/convert\/$/)
  await expect(
    page.getByRole("heading", { name: /turn a link into a file/i })
  ).toBeVisible()

  await page.getByRole("button", { name: "Use dark theme" }).click()
  await expect(page.locator("html")).toHaveClass(/dark/)
  await expect(
    page.getByRole("button", { name: "Use light theme" })
  ).toBeVisible()
})
