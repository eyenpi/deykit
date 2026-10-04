import { expect, test } from "@playwright/test";
test("native modal traps focus, closes on Escape and restores the opener", async ({
  page,
}) => {
  await page.goto("/");
  await page.screenshot({ path: "test-results/start.png", fullPage: true });
  const opener = page.getByRole("button", { name: /Create project/ });
  await opener.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  for (let i = 0; i < 9; i++) {
    await page.keyboard.press("Tab");
    expect(
      await dialog.evaluate((element) =>
        element.contains(document.activeElement),
      ),
    ).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(opener).toBeFocused();
});
test("unavailable project action preserves text and focuses the error", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Open project/ }).click();
  await page.getByLabel("Project folder path").fill("/tmp/Exact folder");
  await page.getByRole("button", { name: "Open project", exact: true }).click();
  await expect(page.getByLabel("Project folder path")).toHaveValue(
    "/tmp/Exact folder",
  );
  await expect(page.getByRole("dialog").getByRole("alert")).toBeFocused();
});
test("staged source requires Save or Discard, and prediction reveal resets", async ({
  page,
}) => {
  await page.goto("/tests/fixtures.html");
  const opener = page.getByRole("button", { name: "Edit input" });
  await opener.click();
  const source = '{"integer":9007199254740993,"decimal":0.1234567890123456789,';
  await page.getByLabel("JSON source").fill(source);
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("heading", { name: "Save your changes?" }),
  ).toBeFocused();
  await page.getByRole("button", { name: "Keep editing" }).click();
  await expect(page.getByLabel("JSON source")).toHaveValue(source);
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(opener).toBeFocused();
  await expect(page.getByRole("status")).toHaveText("Saved");
  await opener.click();
  await expect(page.getByLabel("JSON source")).toHaveValue(source);
  await page.getByLabel("JSON source").fill("discard this");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Discard changes" }).click();
  await opener.click();
  await expect(page.getByLabel("JSON source")).toHaveValue(source);
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Reveal prediction" }).click();
  await expect(page.getByText("Authored prediction a")).toBeVisible();
  await page.getByRole("button", { name: "Next case" }).click();
  await expect(page.getByText("Authored prediction b")).toHaveCount(0);
});
test("narrow and enlarged text layouts do not overflow the page", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");
  await page.evaluate(() => {
    document.documentElement.style.fontSize = "28px";
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Menu" }).click();
  await expect(
    page.getByRole("navigation", { name: "Workspace", exact: true }),
  ).toBeVisible();
});
