import { defineConfig } from "@playwright/test";


export default defineConfig({
  testDir: ".",
  testMatch: "**/*.spec.ts",
  outputDir: "test-results",
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL:
      process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8080",
    trace: "retain-on-failure",
  },
});
