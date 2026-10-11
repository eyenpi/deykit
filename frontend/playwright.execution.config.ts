import { defineConfig } from "@playwright/test";

const baseURL = process.env.DEYKIT_INSTALLED_API_URL;
if (!baseURL)
  throw new Error("Set DEYKIT_INSTALLED_API_URL to the installed server origin.");
const installedOrigin = new URL(baseURL);
if (
  installedOrigin.protocol !== "http:" ||
  !["127.0.0.1", "localhost", "[::1]"].includes(installedOrigin.hostname)
)
  throw new Error("DEYKIT_INSTALLED_API_URL must point to the installed loopback server.");

export default defineConfig({
  testDir: "./tests",
  testMatch: "installed-execution.spec.ts",
  outputDir: "./test-results/installed-execution",
  workers: 1,
  retries: 0,
  timeout: 180_000,
  maxFailures: 1,
  use: { baseURL, headless: true },
  projects: [{ name: "installed-chromium", use: { browserName: "chromium" } }],
});
