import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ThemeToggle } from "@/components/theme-toggle"
import { loginDestination } from "@/lib/auth-navigation"

const setTheme = vi.fn()

vi.mock("next-themes", () => ({
  useTheme: () => ({ resolvedTheme: "light", setTheme }),
}))

describe("dashboard behavior", () => {
  beforeEach(() => setTheme.mockClear())

  it("uses a safe convert destination after login", () => {
    expect(loginDestination("")).toBe("/convert/")
    expect(loginDestination("?next=%2Fsettings%2F")).toBe("/settings/")
    expect(loginDestination("?next=%2F%2Fevil.example")).toBe("/convert/")
  })

  it("switches from the default light theme to dark mode", async () => {
    const user = userEvent.setup()
    render(<ThemeToggle />)

    await user.click(screen.getByRole("button", { name: "Use dark theme" }))

    expect(setTheme).toHaveBeenCalledWith("dark")
  })
})
