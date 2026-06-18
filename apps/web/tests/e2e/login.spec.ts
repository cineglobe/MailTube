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
