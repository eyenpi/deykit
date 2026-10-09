import { defineConfig } from "@playwright/test";

const baseURL = process.env.DEYKIT_INSTALLED_API_URL;
if (!baseURL) throw new Error("Set DEYKIT_INSTALLED_API_URL to the installed server origin.");

export default defineConfig({
  testDir: "./tests",
  testMatch: "installed-api.spec.ts",
  outputDir: "./test-results/installed-api",
  use: { baseURL, headless: true },
  projects: [{ name: "installed-chromium", use: { browserName: "chromium" } }],
});
