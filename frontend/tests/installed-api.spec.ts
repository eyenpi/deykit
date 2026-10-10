import { expect, test } from "@playwright/test";

test("installed shell recovers a lost authored-demo response without duplicate writes", async ({
  page,
}, testInfo) => {
  const demoPath = testInfo.outputPath("installed-demo");
  const markupName = "<img src=x onerror=window.__xss=1>";
  const operationIds: string[] = [];
  const demoResponses: Array<{ status: number; replayed: boolean }> = [];
  let demoRegistrationId: string | undefined;
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
    const status = committed.status();
    expect(status).toBe(200);
    const body = await committed.json();
    demoRegistrationId = body.data.registration.registration_id;
    demoResponses.push({ status, replayed: body.data.demo.replayed });
    if (!droppedCommittedResponse) {
      droppedCommittedResponse = true;
      await route.abort("connectionreset");
      return;
    }
    await route.fulfill({ response: committed });
  });

  const shell = await page.goto("/");
  expect(shell?.status()).toBe(200);
  expect(shell?.headers()["content-security-policy"]).toContain(
    "frame-ancestors 'none'",
  );
  await expect(
    page.getByRole("heading", { name: "Welcome to deykit." }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("initial.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: "Try support demo" }).click();
  const pathField = page.getByLabel("Project folder path");
  await pathField.fill(demoPath);
  await page
    .getByRole("button", { name: "Try support demo", exact: true })
    .click();
  await expect(page.getByRole("dialog").getByRole("alert")).toBeVisible();
  await expect(pathField).toHaveValue(demoPath);
  await page.screenshot({
    path: testInfo.outputPath("error.png"),
    fullPage: true,
  });

  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Reconnect" })
    .click();
  await expect(pathField).toHaveValue(demoPath);
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("reconnect.png"),
    fullPage: true,
  });

  await page
    .getByRole("button", { name: "Try support demo", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Sandbox", exact: true }),
  ).toBeVisible();
  await expect(page.getByText(demoPath, { exact: true })).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("open-demo.png"),
    fullPage: true,
  });

  expect(
    typeof capability === "string" && /^[A-Za-z0-9_-]{43}$/.test(capability),
  ).toBe(true);
  expect(demoRegistrationId).toBeTruthy();
  const sessionCapability = capability as string;
  const registrationId = demoRegistrationId as string;
  const origin = new URL(page.url()).origin;
  const authorizedHeaders = {
    Origin: origin,
    "X-Deykit-Capability": sessionCapability,
  };

  const unauthorized = await page.request.get(
    `/api/v1/projects/${registrationId}/overview`,
    { headers: { Origin: origin } },
  );
  expect(unauthorized.status()).toBe(403);
  expect((await unauthorized.json()).error.code).toBe("local_access_denied");

  const demoRegistration = await page.request.get(
    `/api/v1/projects/${registrationId}`,
    { headers: authorizedHeaders },
  );
  expect(demoRegistration.status()).toBe(200);
  expect((await demoRegistration.json()).data.registration_id).toBe(
    registrationId,
  );
  const demoOverview = await page.request.get(
    `/api/v1/projects/${registrationId}/overview`,
    { headers: authorizedHeaders },
  );
  expect(demoOverview.status()).toBe(200);
  expect((await demoOverview.json()).data.registration.project.name).toBe(
    "Sandbox",
  );
  const demoValidated = await page.request.post(
    `/api/v1/projects/${registrationId}/validate`,
    { headers: authorizedHeaders, data: { schema_version: 1 } },
  );
  expect(demoValidated.status()).toBe(200);

  const createdPath = testInfo.outputPath("Created project");
  const createProject = await page.request.post("/api/v1/projects/register", {
    headers: authorizedHeaders,
    data: {
      schema_version: 1,
      operation_id: "installed-create-project",
      action: "create",
      path: createdPath,
      name: markupName,
    },
  });
  expect(createProject.status()).toBe(200);
  const createdRegistration = (await createProject.json()).data;
  const createdId = createdRegistration.registration_id as string;
  const createdProjectId = createdRegistration.project.id as string;

  const reopened = await page.request.post("/api/v1/projects/register", {
    headers: authorizedHeaders,
    data: {
      schema_version: 1,
      operation_id: "installed-open-project",
      action: "open",
      path: createdPath,
    },
  });
  expect(reopened.status()).toBe(200);
  expect((await reopened.json()).data).toMatchObject({
    registration_id: createdId,
    project: { id: createdProjectId, name: markupName },
  });

  const createdOverview = await page.request.get(
    `/api/v1/projects/${createdId}/overview`,
    { headers: authorizedHeaders },
  );
  expect(createdOverview.status()).toBe(200);
  expect((await createdOverview.json()).data).toMatchObject({
    registration: { registration_id: createdId },
    decisions: [],
    datasets: [],
  });
  const createdValidated = await page.request.post(
    `/api/v1/projects/${createdId}/validate`,
    { headers: authorizedHeaders, data: { schema_version: 1 } },
  );
  expect(createdValidated.status()).toBe(200);
  const recent = await page.request.get("/api/v1/projects/recent", {
    headers: authorizedHeaders,
  });
  expect(recent.status()).toBe(200);
  expect((await recent.json()).data.items).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ path: createdPath, name: markupName }),
      expect.objectContaining({ path: demoPath, name: "Sandbox" }),
    ]),
  );

  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Welcome to deykit." }),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: "Projects", exact: true })
    .click();
  const openMarkupProject = page.getByRole("button", {
    name: `Open project folder: ${markupName}`,
  });
  await expect(openMarkupProject).toBeVisible();
  await openMarkupProject.click();
  await page.getByRole("button", { name: "Open project", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: markupName, exact: true }),
  ).toBeVisible();
  await expect(page.locator("img")).toHaveCount(0);
  expect(
    await page.evaluate(() => (window as Window & { __xss?: unknown }).__xss),
  ).toBeUndefined();
  await page.screenshot({
    path: testInfo.outputPath("escaped-project-name.png"),
    fullPage: true,
  });

  expect(operationIds).toHaveLength(2);
  expect(operationIds[0]).toBe(operationIds[1]);
  expect(demoResponses).toEqual([
    { status: 200, replayed: false },
    { status: 200, replayed: true },
  ]);
  expect(
    await page.evaluate(() => [localStorage.length, sessionStorage.length]),
  ).toEqual([0, 0]);
  expect(
    await page.evaluate(
      () => (document as Document & { cookie: string }).cookie,
    ),
  ).toBe("");
  expect(
    await page.evaluate(() => (window as Window & { __xss?: unknown }).__xss),
  ).toBeUndefined();
  await expect(page.locator("img")).toHaveCount(0);
  expect(page.url()).not.toContain("?");
  expect(
    requestUrls.every(
      (url) => new URL(url).origin === new URL(page.url()).origin,
    ),
  ).toBe(true);
  expect(page.url()).not.toContain(sessionCapability);
  expect(requestUrls.every((url) => !url.includes(sessionCapability))).toBe(
    true,
  );
  expect(consoleMessages.join("\n")).not.toContain(sessionCapability);
});
