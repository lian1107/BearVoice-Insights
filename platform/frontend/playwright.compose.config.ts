import { defineConfig, devices } from "@playwright/test";


export default defineConfig({
  testDir: "./e2e",
  testMatch: "real-compose.spec.ts",
  reporter: "line",
  use: {
    baseURL: process.env.BEARVOICE_COMPOSE_URL ?? "http://127.0.0.1:4173",
    screenshot: "on",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "compose-chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
});
