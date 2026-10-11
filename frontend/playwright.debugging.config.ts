import { defineConfig } from "@playwright/test";

const baseURL = process.env.DEYKIT_INSTALLED_API_URL;
if (!baseURL)
  throw new Error("Set DEYKIT_INSTALLED_API_URL to the installed server origin.");

export default defineConfig({
  testDir: "./tests",
  testMatch: "installed-debugging.spec.ts",
  outputDir: "./test-results/installed-debugging",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  maxFailures: 1,
  timeout: 570_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL,
    headless: true,
    actionTimeout: 12_000,
    navigationTimeout: 15_000,
    trace: "off",
    video: "off",
  },
  projects: [{ name: "installed-debugging-chromium", use: { browserName: "chromium" } }],
});
