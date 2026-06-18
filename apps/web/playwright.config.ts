import { defineConfig, devices } from "@playwright/test"

export default defineConfig({
  testDir: "./tests/e2e",
  webServer: process.env.MAILTUBE_E2E_URL
    ? undefined
    : {
        command: "python3 -m http.server 4173 --directory out",
        url: "http://127.0.0.1:4173/login/",
        reuseExistingServer: true,
      },
  use: {
    baseURL: process.env.MAILTUBE_E2E_URL ?? "http://127.0.0.1:4173",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["iPhone 13"] } },
  ],
})
