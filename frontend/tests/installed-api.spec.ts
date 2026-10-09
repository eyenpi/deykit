import { expect, test } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

test("installed shell recovers a lost authored-demo response without duplicate writes", async ({
  page,
}, testInfo) => {
  const root = mkdtempSync(join(tmpdir(), "deykit-installed-api-"));
  const demoPath = join(root, "<img src=x onerror=window.__xss=1>");
  const operationIds: string[] = [];
  const demoResponses: Array<{ status: number; replayed: boolean }> = [];
  const requestUrls: string[] = [];
  const consoleMessages: string[] = [];
  let capability: string | undefined;
  let droppedCommittedResponse = false;

  page.on("request", (request) => requestUrls.push(request.url()));
  page.on("console", (message) => consoleMessages.push(message.text()));
  page.on("response", async (response) => {
    if (response.url().endsWith("/api/v1/session/bootstrap")) {
      const body = await response.json().catch(() => undefined);
      if (typeof body?.data?.capability === "string")
        capability = body.data.capability;
    }
  });

  await page.route("**/api/v1/projects/demo", async (route) => {
    const request = route.request();
    operationIds.push(request.postDataJSON().operation_id);
    const committed = await route.fetch({ headers: request.headers() });
    const body = await committed.json();
    demoResponses.push({ status: committed.status(), replayed: body.data.demo.replayed });
    if (!droppedCommittedResponse) {
      droppedCommittedResponse = true;
      await route.abort("connectionreset");
      return;
    }
    await route.fulfill({ response: committed });
  });

  const shell = await page.goto("/");
  expect(shell?.status()).toBe(200);
  expect(shell?.headers()["content-security-policy"]).toContain("frame-ancestors 'none'");
  await expect(page.getByRole("heading", { name: "Welcome to deykit." })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("initial.png"), fullPage: true });

  await page.getByRole("button", { name: "Try support demo" }).click();
  const pathField = page.getByLabel("Project folder path");
  await pathField.fill(demoPath);
  await page.getByRole("button", { name: "Try support demo", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toBeVisible();
  await expect(pathField).toHaveValue(demoPath);
  await page.screenshot({ path: testInfo.outputPath("error.png"), fullPage: true });

  await page.getByRole("dialog").getByRole("button", { name: "Reconnect" }).click();
  await expect(pathField).toHaveValue(demoPath);
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("reconnect.png"), fullPage: true });

  await page.getByRole("button", { name: "Try support demo", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sandbox", exact: true })).toBeVisible();
  await expect(page.getByText(demoPath, { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("open-demo.png"), fullPage: true });

  expect(operationIds).toHaveLength(2);
  expect(operationIds[0]).toBe(operationIds[1]);
  expect(demoResponses).toEqual([
    { status: 200, replayed: false },
    { status: 200, replayed: true },
  ]);
  expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([
    0,
    0,
  ]);
  expect(await page.evaluate(() => (document as Document & { cookie: string }).cookie)).toBe("");
  expect(await page.evaluate(() => (window as Window & { __xss?: unknown }).__xss)).toBeUndefined();
  await expect(page.locator("img")).toHaveCount(0);
  expect(page.url()).not.toContain("?");
  expect(
    requestUrls.every((url) => new URL(url).origin === new URL(page.url()).origin),
  ).toBe(true);
  if (capability) {
    expect(page.url()).not.toContain(capability);
    expect(requestUrls.every((url) => !url.includes(capability))).toBe(true);
    expect(consoleMessages.join("\n")).not.toContain(capability);
  }
});
