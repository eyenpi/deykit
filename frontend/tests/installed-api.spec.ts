import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { writeFile } from "node:fs/promises";

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
  expect((await demoRegistration.json()).data.registration_id).toBe(registrationId);
  const demoOverview = await page.request.get(
    `/api/v1/projects/${registrationId}/overview`,
    { headers: authorizedHeaders },
  );
  expect(demoOverview.status()).toBe(200);
  expect((await demoOverview.json()).data.registration.project.name).toBe("Sandbox");
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
  await expect(page.getByRole("heading", { name: "Welcome to deykit." })).toBeVisible();
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
  expect(page.url()).not.toContain(sessionCapability);
  expect(requestUrls.every((url) => !url.includes(sessionCapability))).toBe(true);
  expect(consoleMessages.join("\n")).not.toContain(sessionCapability);
});

test("installed browser authors exact decision source and previews imports through real APIs", async ({
  page,
}, testInfo) => {
  const projectName = "M10 authoring acceptance";
  let decisionName = "Precise source decision";
  const projectPath = testInfo.outputPath("authoring-project");
  const apiResponses: string[] = [];
  let importCommitBody: Record<string, unknown> | undefined;
  let capability: string | undefined;
  page.on("request", (request) => {
    apiResponses.push(request.url());
    if (request.url().endsWith("/imports/commit"))
      importCommitBody = request.postDataJSON() as Record<string, unknown>;
  });
  page.on("response", async (response) => {
    if (response.url().endsWith("/api/v1/session/bootstrap")) {
      const body = await response.json().catch(() => undefined);
      if (typeof body?.data?.capability === "string")
        capability = body.data.capability;
    }
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Welcome to deykit." })).toBeVisible();
  await page.getByRole("button", { name: "Create project" }).click();
  await page.getByLabel("Project name").fill(projectName);
  await page.getByLabel("Project folder path").fill(projectPath);
  await page.getByRole("dialog").getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible();

  await page.getByRole("button", { name: "Create dataset" }).click();
  await page.getByLabel("Dataset name").fill("Imported before decision");
  await page.getByRole("dialog").getByRole("button", { name: "Create dataset" }).click();
  await expect(page.getByRole("heading", { name: "Examples" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("examples-before-decision.png"), fullPage: true });

  await page.getByRole("button", { name: "Project examples", exact: true }).click();
  await page.getByRole("button", { name: "Import examples" }).click();
  await page.getByLabel("Import source text").fill("id,input\nseed-1,first imported input\n");
  const mappingBodies: Array<Record<string, unknown>> = [];
  let firstMappingSource: string | undefined;
  let finalMappingSource: string | undefined;
  let releaseFirstMapping!: () => void;
  let reportFirstMapping!: () => void;
  let reportSecondMapping!: () => void;
  const firstMappingGate = new Promise<void>((resolve) => { releaseFirstMapping = resolve; });
  const firstMappingStarted = new Promise<void>((resolve) => { reportFirstMapping = resolve; });
  const secondMappingFinished = new Promise<void>((resolve) => { reportSecondMapping = resolve; });
  let mappingCall = 0;
  await page.route("**/authoring/mapping-transform", async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    mappingBodies.push(body);
    mappingCall += 1;
    if (mappingCall === 1) {
      reportFirstMapping();
      await firstMappingGate;
    }
    const response = await route.fetch();
    const responseBody = await response.json();
    const nextSource = responseBody.data.mapping_source as string;
    if (mappingCall === 1) firstMappingSource = nextSource;
    if (mappingCall === 2) {
      finalMappingSource = nextSource;
      reportSecondMapping();
    }
    await route.fulfill({ response });
  });
  const previewBodies: Array<Record<string, unknown>> = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/imports/preview"))
      previewBodies.push(request.postDataJSON() as Record<string, unknown>);
  });
  await expect(page.getByLabel("input column")).toBeVisible();
  await page.getByLabel("id column").fill("id");
  await page.getByLabel("id column").press("Tab");
  await firstMappingStarted;
  await page.getByLabel("input column").fill("input");
  await page.getByLabel("input column").press("Tab");
  await expect(page.getByRole("button", { name: "Preview all rows" })).toBeDisabled();
  expect(mappingBodies).toHaveLength(1);
  releaseFirstMapping();
  await secondMappingFinished;
  expect(mappingBodies).toHaveLength(2);
  expect(mappingBodies[1].mapping_source).toBe(firstMappingSource);
  await expect(page.getByLabel("id column")).toHaveValue("id");
  await expect(page.getByLabel("input column")).toHaveValue("input");
  await expect(page.getByRole("button", { name: "Preview all rows" })).toBeEnabled();
  await page.getByRole("button", { name: "Preview all rows" }).click();
  await expect.poll(() => previewBodies.length).toBe(1);
  expect(previewBodies[0].mapping_source).toBe(finalMappingSource);
  await expect(page.getByRole("heading", { name: "Import review" })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "1 rows · 1 valid · 0 rejected" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("import-before-decision.png"), fullPage: true });
  await page.getByRole("button", { name: "Import cases" }).click();
  await expect(page.getByRole("button", { name: "seed-1", exact: true })).toBeVisible();
  const initialImportHash = new URL(page.url()).hash;
  const registrationId = initialImportHash.match(/^#\/p\/([A-Za-z0-9_-]+)/)?.[1] as string;
  const datasetId = new URLSearchParams(initialImportHash.split("?")[1] ?? "").get("dataset") as string;

  await page.getByRole("button", { name: projectName, exact: true }).click();
  await page.getByRole("button", { name: "Create decision" }).click();
  await page.getByLabel("Decision name").fill(decisionName);
  await page.getByRole("dialog").getByRole("button", { name: "Create decision" }).click();
  await expect(page.getByLabel("Question")).toBeVisible();
  const schemaSource =
    '{"type":"object","properties":{"large":{"const":9007199254740993},"fraction":{"multipleOf":0.1234567890123456789}}}';
  await page.getByLabel("Advanced JSON Schema source").fill(schemaSource);
  await page.getByLabel("Advanced JSON Schema source").press("Tab");
  await expect(page.locator(".document-title-row [role=status]")).toHaveText("Draft saved");
  await page.screenshot({ path: testInfo.outputPath("decision-json-schema.png"), fullPage: true });

  const registrationMatch = new URL(page.url()).hash.match(/^#\/p\/([A-Za-z0-9_-]+)/);
  const decisionMatch = new URL(page.url()).hash.match(/\/d\/([A-Za-z0-9_-]+)/);
  expect(registrationMatch).not.toBeNull();
  expect(decisionMatch).not.toBeNull();
  expect(capability).toMatch(/^[A-Za-z0-9_-]{43}$/);
  const origin = new URL(page.url()).origin;
  expect(registrationMatch?.[1]).toBe(registrationId);
  const decisionId = decisionMatch?.[1] as string;
  const stored = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    { headers: { Origin: origin, "X-Deykit-Capability": capability as string } },
  );
  expect(stored.status()).toBe(200);
  const decision = (await stored.json()).data;
  expect(decision.draft.record.editor_source).toContain(schemaSource);

  const cliSource = decision.draft.record.editor_source.replace(
    '"instructions": ""',
    '"instructions": "CLI winner"',
  );
  const browserSource = decision.draft.record.editor_source.replace(
    '"instructions": ""',
    '"instructions": "Browser losing edit"',
  );
  expect(cliSource).not.toBe(decision.draft.record.editor_source);
  expect(browserSource).not.toBe(decision.draft.record.editor_source);
  const cliSourcePath = testInfo.outputPath("cli-winner-source.json");
  await writeFile(cliSourcePath, cliSource, "utf8");
  let releaseBrowserSave!: () => void;
  let reportBrowserSaveStarted!: () => void;
  const browserSaveStarted = new Promise<void>((resolve) => { reportBrowserSaveStarted = resolve; });
  const holdBrowserSave = new Promise<void>((resolve) => { releaseBrowserSave = resolve; });
  let heldFirstSave = false;
  await page.route("**/api/v1/projects/*/decisions/*/draft", async (route) => {
    if (route.request().method() === "PUT" && !heldFirstSave) {
      heldFirstSave = true;
      reportBrowserSaveStarted();
      await holdBrowserSave;
    }
    await route.continue();
  });
  await page.getByText("Advanced editor source", { exact: true }).click();
  const sourceEditor = page.getByLabel("Decision source");
  await sourceEditor.fill(browserSource);
  await browserSaveStarted;
  const cliResult = execFileSync(
    "deykit",
    [
      "--project", projectPath,
      "--json",
      "decision", "edit", decisionId,
      "--file", cliSourcePath,
      "--if-hash", decision.draft.etag,
      "--operation-id", "m10-browser-cli-etag-winner",
    ],
    { encoding: "utf8" },
  );
  expect(cliResult).toContain("m10-browser-cli-etag-winner");
  releaseBrowserSave();
  await expect(page.getByRole("button", { name: "Review current and reapply my source" })).toBeVisible();
  await expect(sourceEditor).toHaveValue(browserSource);
  const raceWinner = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    { headers: { Origin: origin, "X-Deykit-Capability": capability as string } },
  );
  expect((await raceWinner.json()).data.draft.record.editor_source).toBe(cliSource);
  await page.getByRole("button", { name: "Review current and reapply my source" }).click();
  await expect(page.locator(".document-title-row [role=status]")).toHaveText("Draft saved");
  const reapplied = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    { headers: { Origin: origin, "X-Deykit-Capability": capability as string } },
  );
  const reappliedDraft = (await reapplied.json()).data.draft;
  expect(reappliedDraft.record.editor_source).toBe(browserSource);

  decisionName = "Precise source decision renamed";
  const renameBodies: Array<Record<string, unknown>> = [];
  await page.route(`**/decisions/${decisionId}/rename`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    renameBodies.push(route.request().postDataJSON() as Record<string, unknown>);
    const response = await route.fetch();
    if (renameBodies.length === 1) {
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
      return;
    }
    await route.fulfill({ response });
  });
  const renameResponse = page.waitForResponse((response) =>
    response.url().endsWith("/rename") && response.request().method() === "POST",
  );
  await page.getByLabel("Decision name").fill(decisionName);
  await page.getByLabel("Decision name").press("Tab");
  expect((await renameResponse).status()).toBe(200);
  await expect(page.getByRole("button", { name: "Retry same rename" })).toBeVisible();
  await page.getByRole("button", { name: "Retry same rename" }).click();
  await expect(page.getByLabel("Decision name")).toHaveValue(decisionName);
  expect(renameBodies).toHaveLength(2);
  expect(renameBodies[1]).toEqual(renameBodies[0]);
  await page.unroute(`**/decisions/${decisionId}/rename`);
  const renamed = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    { headers: { Origin: origin, "X-Deykit-Capability": capability as string } },
  );
  expect((await renamed.json()).data.decision.record.name).toBe(decisionName);

  const revisionSaveBodies: Array<Record<string, unknown>> = [];
  await page.route(`**/decisions/${decisionId}/revisions`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    revisionSaveBodies.push(route.request().postDataJSON() as Record<string, unknown>);
    const response = await route.fetch();
    if (revisionSaveBodies.length === 1) {
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
      return;
    }
    await route.fulfill({ response });
  });
  await page.getByLabel("Version note (optional)").fill("Source preservation baseline");
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  await expect(page.getByRole("button", { name: "Retry same version save" })).toBeVisible();
  await page.getByRole("button", { name: "Retry same version save" }).click();
  await expect(page.getByRole("status").filter({ hasText: /^Saved version / })).toBeVisible();
  expect(revisionSaveBodies).toHaveLength(2);
  expect(revisionSaveBodies[1]).toEqual(revisionSaveBodies[0]);
  await page.unroute(`**/decisions/${decisionId}/revisions`);
  const firstRevisionPage = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}/revisions?limit=50`,
    { headers: { Origin: origin, "X-Deykit-Capability": capability as string } },
  );
  const firstRevisionId = (await firstRevisionPage.json()).data.items[0].revision.record.id as string;
  const firstRevision = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}/revisions/${firstRevisionId}`,
    { headers: { Origin: origin, "X-Deykit-Capability": capability as string } },
  );
  const firstRevisionEditorSource = (await firstRevision.json()).data.revision.editor_source as string;

  await page.getByRole("button", { name: "+ Add option" }).click();
  const optionNames = page.getByLabel("Option name");
  await expect(optionNames).toHaveCount(3);
  await optionNames.nth(2).fill("Option C");
  const addTransform = page.waitForResponse((response) =>
    response.url().endsWith("/editor-transform") && response.request().method() === "POST",
  );
  const addDraftSave = page.waitForResponse((response) =>
    response.url().endsWith("/draft") && response.request().method() === "PUT",
  );
  await optionNames.nth(2).press("Tab");
  await addTransform;
  await addDraftSave;
  const renameTransform = page.waitForResponse((response) =>
    response.url().endsWith("/editor-transform") && response.request().method() === "POST",
  );
  const renameDraftSave = page.waitForResponse((response) =>
    response.url().endsWith("/draft") && response.request().method() === "PUT",
  );
  await page.getByLabel("Option name").nth(1).fill("Renamed Option B");
  await page.getByLabel("Option name").nth(1).press("Tab");
  await renameTransform;
  await renameDraftSave;
  const reorderTransform = page.waitForResponse((response) =>
    response.url().endsWith("/editor-transform") && response.request().method() === "POST",
  );
  const reorderDraftSave = page.waitForResponse((response) =>
    response.url().endsWith("/draft") && response.request().method() === "PUT",
  );
  await page.getByRole("button", { name: "Move Option C up" }).click();
  await reorderTransform;
  await reorderDraftSave;
  const transformedDecision = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    { headers: { Origin: origin, "X-Deykit-Capability": capability as string } },
  );
  const transformedSource = (await transformedDecision.json()).data.draft.record.editor_source as string;
  expect(transformedSource).toContain("9007199254740993");
  expect(transformedSource).toContain("0.1234567890123456789");
  await expect(page.locator(".option-list > li")).toContainText(["Option A", "Option C", "Renamed Option B"]);
  await page.getByLabel("Version note (optional)").fill("Stable option identity and order");
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: /^Saved version / })).toBeVisible();

  await page.getByRole("button", { name: "Version history" }).click();
  await expect(page.getByRole("heading", { name: "Version history" })).toBeVisible();
  const revisionRows = page.getByRole("table", { name: "Saved decision versions" }).getByRole("row");
  await expect(revisionRows).toHaveCount(3);
  const baselineRow = revisionRows.nth(2);
  await baselineRow.getByRole("button", { name: "Compare to latest" }).click();
  await expect(page.getByLabel("Difference from latest")).toContainText("Option order changed: Yes");
  await expect(page.getByLabel("Difference from latest")).toContainText("Added option IDs:");
  await baselineRow.getByRole("button", { name: "Inspect" }).click();
  await page.getByText("Exact saved editor source", { exact: true }).click();
  const savedEditor = page.getByLabel("Saved editor source");
  await expect(savedEditor).toContainText("9007199254740993");
  await expect(savedEditor).toContainText("0.1234567890123456789");
  await baselineRow.getByRole("button", { name: "Restore to draft…" }).click();
  const restoreDialog = page.getByRole("dialog", { name: "Restore this version to the draft?" });
  await expect(restoreDialog).toBeVisible();
  await expect(restoreDialog.getByLabel("Editor source to restore")).toHaveValue(firstRevisionEditorSource);
  const uncertainRestoreRequests: Array<Record<string, unknown>> = [];
  let firstRestoreStatus: number | undefined;
  await page.route(`**/decisions/${decisionId}/restore-revision`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    uncertainRestoreRequests.push(route.request().postDataJSON() as Record<string, unknown>);
    const response = await route.fetch();
    if (uncertainRestoreRequests.length === 1) {
      firstRestoreStatus = response.status();
      await route.abort("failed");
      return;
    }
    await route.fulfill({ response });
  });
  await restoreDialog.getByRole("button", { name: "Restore to draft", exact: true }).click();
  await expect(page.getByRole("button", { name: "Retry the same restore request" })).toBeVisible();
  await expect(restoreDialog.getByLabel("Editor source to restore")).toHaveValue(firstRevisionEditorSource);
  const restoreHashBeforeBack = page.url();
  await page.goBack();
  await expect(restoreDialog).toBeVisible();
  expect(page.url()).toBe(restoreHashBeforeBack);
  await page.getByRole("button", { name: "Retry the same restore request" }).click();
  await expect(page.getByRole("heading", { name: decisionName })).toBeVisible();
  expect(firstRestoreStatus).toBe(200);
  expect(uncertainRestoreRequests).toHaveLength(2);
  expect(uncertainRestoreRequests[1]).toEqual(uncertainRestoreRequests[0]);
  await page.unroute(`**/decisions/${decisionId}/restore-revision`);

  await page.getByRole("button", { name: "Version history" }).click();
  await expect(page.getByRole("heading", { name: "Version history" })).toBeVisible();
  const refreshedRevisionRows = page.getByRole("table", { name: "Saved decision versions" }).getByRole("row");
  await refreshedRevisionRows.nth(2).getByRole("button", { name: "Restore to draft…" }).click();
  const conflictRestoreDialog = page.getByRole("dialog", { name: "Restore this version to the draft?" });
  await expect(conflictRestoreDialog.getByLabel("Editor source to restore")).toHaveValue(firstRevisionEditorSource);
  const beforeRestoreRace = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    { headers: { Origin: origin, "X-Deykit-Capability": capability as string } },
  );
  const currentDraft = (await beforeRestoreRace.json()).data.draft;
  expect(currentDraft.record.editor_source).toBe(firstRevisionEditorSource);
  const restoreRaceWinnerSource = `${currentDraft.record.editor_source}\n`;
  let releaseRestore!: () => void;
  let reportRestoreStarted!: () => void;
  const restoreStarted = new Promise<void>((resolve) => { reportRestoreStarted = resolve; });
  const holdRestore = new Promise<void>((resolve) => { releaseRestore = resolve; });
  let restoreHeld = false;
  let restoreConflictStatus: number | undefined;
  await page.route(`**/decisions/${decisionId}/restore-revision`, async (route) => {
    if (route.request().method() === "POST" && !restoreHeld) {
      restoreHeld = true;
      reportRestoreStarted();
      await holdRestore;
    }
    const response = await route.fetch();
    restoreConflictStatus = response.status();
    await route.fulfill({ response });
  });
  await conflictRestoreDialog.getByRole("button", { name: "Restore to draft", exact: true }).click();
  await restoreStarted;
  const concurrentDraftWrite = await page.request.put(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}/draft`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
      data: {
        schema_version: 1,
        operation_id: "m10-restore-conflict-winner",
        expected_etag: currentDraft.etag,
        editor_source: restoreRaceWinnerSource,
      },
    },
  );
  expect(concurrentDraftWrite.status()).toBe(200);
  releaseRestore();
  await expect(page.getByRole("alert")).toBeVisible();
  expect(restoreConflictStatus).toBe(409);
  await expect(conflictRestoreDialog).toBeVisible();
  await expect(conflictRestoreDialog).toContainText("Review the current draft before reapplying.");
  await expect(conflictRestoreDialog.getByLabel("Editor source to restore")).toHaveValue(firstRevisionEditorSource);
  await conflictRestoreDialog.getByRole("button", { name: "Review current draft" }).click();
  await expect(conflictRestoreDialog.getByLabel("Reviewed current draft source")).toHaveValue(restoreRaceWinnerSource);
  await conflictRestoreDialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: decisionName, exact: true })
    .click();
  const restoreConflictWinner = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    { headers: { Origin: origin, "X-Deykit-Capability": capability as string } },
  );
  expect((await restoreConflictWinner.json()).data.draft.record.editor_source).toBe(restoreRaceWinnerSource);
  await page.getByText("Advanced editor source", { exact: true }).click();
  await expect(page.getByLabel("Decision source")).toHaveValue(restoreRaceWinnerSource);
  await expect(page.getByRole("heading", { name: decisionName })).toBeVisible();

  await page.getByRole("button", { name: "Examples", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Expected answers" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("examples-label-review.png"), fullPage: true });

  await page.getByRole("button", { name: "Import examples" }).click();
  await page.getByLabel("Map expected answers for").selectOption(decisionId);
  await page.getByLabel("Advanced mapping source").fill(
    '{"input_kind":"json","input_column":"input","input_parse_json":true,"id_column":"id","expected_column":"expected","group_column":"group"}',
  );
  const rows = Array.from({ length: 10 }, (_item, index) => {
    const rowNumber = index + 1;
    const input = rowNumber === 3 ? "not-json" : `{"case":${rowNumber}}`;
    const expected = rowNumber === 7 ? "missing-option" : "option-a";
    const group = [1, 2, 8, 9].includes(rowNumber) ? "related-group" : `group-${rowNumber}`;
    return `case-${rowNumber},"${input.replaceAll('"', '""')}",${expected},${group}`;
  });
  const sourceText = `id,input,expected,group\n${rows.join("\n")}\n`;
  await page.getByLabel("Import source text").fill(sourceText);
  await page.getByRole("button", { name: "Preview all rows" }).click();
  await expect(page.getByRole("status").filter({ hasText: "10 rows · 8 valid · 2 rejected · 8 would import" })).toBeVisible();
  await expect(page.getByRole("row", { name: /3.*not-json.*invalid/ })).toBeVisible();
  await expect(page.getByRole("row", { name: /7.*missing-option/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Import valid rows" })).toBeDisabled();
  await page.screenshot({ path: testInfo.outputPath("import-row-errors.png"), fullPage: true });
  await page.getByLabel("Import source text").fill(`${sourceText}# changed proposal\n`);
  await expect(page.getByRole("heading", { name: "Import review" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Import valid rows" })).toHaveCount(0);
  await page.getByLabel("Import source text").fill(sourceText);
  await page.getByRole("button", { name: "Preview all rows" }).click();
  await expect(page.getByRole("status").filter({ hasText: "10 rows · 8 valid · 2 rejected · 8 would import" })).toBeVisible();
  await page.getByRole("checkbox", { name: "Import valid rows only (8) and keep the exclusion report" }).check();
  await page.screenshot({ path: testInfo.outputPath("import-valid-rows-reviewed.png"), fullPage: true });
  await page.getByRole("button", { name: "Import valid rows" }).click();
  await expect(page.getByRole("button", { name: "case-1", exact: true })).toBeVisible();
  expect(importCommitBody).toBeDefined();
  const commitReplay = await page.request.post(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/imports/commit`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
      data: importCommitBody,
    },
  );
  expect(commitReplay.status()).toBe(200);
  expect((await commitReplay.json()).data.replayed).toBe(true);
  const importedCases = await page.request.get(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases?limit=50`,
    { headers: { Origin: origin, "X-Deykit-Capability": capability as string } },
  );
  expect((await importedCases.json()).data.total).toBe("9");

  await page.getByRole("button", { name: "seed-1", exact: true }).click();
  const readSeedLabel = () => page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}/datasets/${datasetId}/labels/seed-1`,
    { headers: { Origin: origin, "X-Deykit-Capability": capability as string } },
  );
  const emptySeedLabel = await readSeedLabel();
  expect((await emptySeedLabel.json()).data.label).toBeNull();
  await page.getByRole("checkbox", { name: "Option A" }).check();
  await page.getByRole("checkbox", { name: "Option B" }).check();
  const stillUnlabelled = await readSeedLabel();
  expect((await stillUnlabelled.json()).data.label).toBeNull();
  await page.getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: decisionName, exact: true })
    .click();
  const keepStagedLabel = page.getByRole("dialog", { name: "Unsaved changes" });
  await expect(keepStagedLabel).toBeVisible();
  await keepStagedLabel.getByRole("button", { name: "Keep editing" }).click();
  await expect(page.getByRole("checkbox", { name: "Option A" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Option B" })).toBeChecked();
  await page.getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: decisionName, exact: true })
    .click();
  const discardStagedLabel = page.getByRole("dialog", { name: "Unsaved changes" });
  await discardStagedLabel.getByRole("button", { name: "Discard changes" }).click();
  await expect(page.getByRole("heading", { name: decisionName })).toBeVisible();
  expect((await (await readSeedLabel()).json()).data.label).toBeNull();
  await page.getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: "Examples", exact: true })
    .click();
  await expect(page.getByRole("heading", { name: "Examples" })).toBeVisible();
  await page.getByRole("button", { name: "seed-1", exact: true }).click();
  await page.getByRole("checkbox", { name: "Option A" }).check();
  await page.getByRole("checkbox", { name: "Option B" }).check();

  let releaseLabelSave!: () => void;
  let reportLabelSaveStarted!: () => void;
  const labelSaveStarted = new Promise<void>((resolve) => { reportLabelSaveStarted = resolve; });
  const holdLabelSave = new Promise<void>((resolve) => { releaseLabelSave = resolve; });
  let heldLabelSave = false;
  let losingLabelBody: Record<string, unknown> | undefined;
  await page.route("**/labels/batch", async (route) => {
    if (route.request().method() === "POST" && !heldLabelSave) {
      heldLabelSave = true;
      losingLabelBody = route.request().postDataJSON() as Record<string, unknown>;
      reportLabelSaveStarted();
      await holdLabelSave;
    }
    await route.continue();
  });
  await page.getByRole("button", { name: "Save expected answer" }).click();
  await labelSaveStarted;
  expect(losingLabelBody).toBeDefined();
  const losingEdits = losingLabelBody?.edits as Array<Record<string, unknown>>;
  const winningLabelBody = {
    ...losingLabelBody,
    operation_id: "m10-label-race-winner",
    edits: losingEdits.map((edit) => ({ ...edit, acceptable_option_ids: ["option-a"] })),
  };
  const winningLabelResponse = await page.request.post(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}/datasets/${datasetId}/labels/batch`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
      data: winningLabelBody,
    },
  );
  expect(winningLabelResponse.status()).toBe(200);
  releaseLabelSave();
  await expect(page.getByRole("button", { name: "Review current label" })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Option A" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Option B" })).toBeChecked();
  expect((await (await readSeedLabel()).json()).data.label.acceptable_option_ids).toEqual(["option-a"]);
  await page.getByRole("button", { name: "Review current label" }).click();
  await expect(page.getByRole("button", { name: "Review current label" })).toHaveCount(0);
  await expect(page.getByRole("checkbox", { name: "Option A" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Option B" })).toBeChecked();
  await page.getByRole("button", { name: "Save expected answer" }).click();
  let savedLabel = await readSeedLabel();
  expect((await savedLabel.json()).data.label).toMatchObject({
    acceptable_option_ids: ["option-a", "option-b"],
    provenance: "human",
    status: "active",
  });
  await page.getByRole("button", { name: "Dispute label" }).click();
  savedLabel = await readSeedLabel();
  expect((await savedLabel.json()).data.label.status).toBe("disputed");
  await page.getByRole("button", { name: "Resolve dispute with staged set" }).click();
  savedLabel = await readSeedLabel();
  expect((await savedLabel.json()).data.label).toMatchObject({ status: "active", provenance: "human" });
  await page.getByRole("button", { name: "Clear label" }).click();
  const clearedLabel = await readSeedLabel();
  expect((await clearedLabel.json()).data.label).toBeNull();

  const readCaseOne = () => page.request.get(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/case-1`,
    { headers: { Origin: origin, "X-Deykit-Capability": capability as string } },
  );
  const readCaseOneLabel = () => page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}/datasets/${datasetId}/labels/case-1`,
    { headers: { Origin: origin, "X-Deykit-Capability": capability as string } },
  );
  const caseBeforeTag = (await (await readCaseOne()).json()).data;
  const tagOnly = await page.request.put(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/case-1`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
      data: {
        schema_version: 1,
        operation_id: "m10-tag-only-edit",
        expected_case_etag: caseBeforeTag.case.etag,
        expected_dataset_etag: caseBeforeTag.dataset_etag,
        input_kind: caseBeforeTag.case.record.input_kind,
        input_source: caseBeforeTag.case.record.input_source,
        tags: [...caseBeforeTag.case.record.tags, "browser-review"],
        split: caseBeforeTag.case.record.split,
        group_id: caseBeforeTag.case.record.group_id,
        derived_from: caseBeforeTag.case.record.derived_from,
        metadata_source: caseBeforeTag.case.record.metadata_source,
      },
    },
  );
  expect(tagOnly.status()).toBe(200);
  expect((await readCaseOneLabel().then((response) => response.json())).data.status).toBe("applicable");

  await page.reload();
  await expect(page.getByRole("heading", { name: "Examples" })).toBeVisible();
  await page.getByRole("button", { name: "case-1", exact: true }).click();
  await page.getByRole("button", { name: "Edit input" }).click();
  await page.getByLabel("Input source").fill('{"case":1,"changed":true}');
  await page.getByRole("button", { name: "Save input" }).click();
  const staleLabel = await readCaseOneLabel();
  expect((await staleLabel.json()).data).toMatchObject({ status: "excluded", reasons: ["stale"] });

  const currentCase = (await (await readCaseOne()).json()).data;
  const removed = await page.request.delete(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/case-1`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
      data: {
        schema_version: 1,
        operation_id: "m10-remove-case-one",
        expected_case_etag: currentCase.case.etag,
        expected_dataset_etag: currentCase.dataset_etag,
      },
    },
  );
  expect(removed.status()).toBe(200);
  const removedData = (await removed.json()).data;
  const readded = await page.request.post(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
      data: {
        schema_version: 1,
        operation_id: "m10-readd-case-one",
        expected_dataset_etag: removedData.dataset.etag,
        case_id: "case-1",
        input_kind: currentCase.case.record.input_kind,
        input_source: currentCase.case.record.input_source,
        tags: currentCase.case.record.tags,
        split: currentCase.case.record.split,
        group_id: currentCase.case.record.group_id,
        derived_from: currentCase.case.record.derived_from,
        metadata_source: currentCase.case.record.metadata_source,
      },
    },
  );
  expect(readded.status()).toBe(200);
  expect((await readCaseOneLabel().then((response) => response.json())).data.label).toBeNull();

  await page.getByRole("button", { name: "Split dataset" }).click();
  await page.getByRole("button", { name: "Preview assignments" }).click();
  await expect(page.getByRole("heading", { name: "Server split preview" })).toBeVisible();
  await page.locator(".split-preview details summary").click();
  const assignments = await page.locator(".split-preview details table tbody tr").evaluateAll((rows) =>
    rows.map((row) => [
      row.querySelector("th")?.textContent?.trim() ?? "",
      row.querySelector("td")?.textContent?.trim() ?? "",
    ] as const),
  );
  const relatedAssignments = assignments
    .filter(([caseId]) => ["case-1", "case-2", "case-8", "case-9"].includes(caseId))
    .map(([, split]) => split);
  expect(relatedAssignments).toHaveLength(4);
  expect(new Set(relatedAssignments).size).toBe(1);
  await page.screenshot({ path: testInfo.outputPath("split-server-preview.png"), fullPage: true });
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await page.getByRole("button", { name: "Discard proposal" }).click();

  await page.getByRole("button", { name: "seed-1", exact: true }).click();
  await page.getByRole("checkbox", { name: "Option A" }).check();
  await page.getByRole("checkbox", { name: "Option B" }).check();
  await page.getByRole("button", { name: "Save expected answer" }).click();
  await expect(page.getByText("Applicable · human")).toBeVisible();
  await page.getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: decisionName, exact: true })
    .click();
  await page.getByRole("button", { name: "+ Add option" }).click();
  const optionNamesForRemoval = page.getByLabel("Option name");
  await expect(optionNamesForRemoval).toHaveCount(3);
  await optionNamesForRemoval.nth(2).fill("Option C");
  const removalSetupTransform = page.waitForResponse((response) =>
    response.url().endsWith("/editor-transform") && response.request().method() === "POST",
  );
  const removalSetupSave = page.waitForResponse((response) =>
    response.url().endsWith("/draft") && response.request().method() === "PUT",
  );
  await optionNamesForRemoval.nth(2).press("Tab");
  await removalSetupTransform;
  await removalSetupSave;

  await page.getByRole("button", { name: "Remove option Option A" }).click();
  const referencedImpact = page.getByRole("dialog", { name: "Remove Option A?" })
    .getByRole("list", { name: "Affected references" });
  await expect(referencedImpact).toContainText("seed-1");
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();

  await page.getByRole("button", { name: "Remove option Option C" }).click();
  const unreferencedImpact = page.getByRole("dialog", { name: "Remove Option C?" });
  await expect(unreferencedImpact).toContainText("The service reported no affected references.");
  await unreferencedImpact.getByRole("button", { name: "Remove option from draft" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Draft saved" })).toBeVisible();
  await expect(page.getByLabel("Option name")).toHaveCount(2);

  await page.getByRole("button", { name: "Remove option Option A" }).click();
  const uncomputableImpact = page.getByRole("dialog", { name: "Remove Option A?" });
  await expect(uncomputableImpact).toContainText("The service could not compute affected references for this invalid definition.");
  await expect(uncomputableImpact.getByRole("list", { name: "Definition validation advice" }).locator("code").first()).toBeVisible();
  await expect(uncomputableImpact.getByRole("list", { name: "Affected references" })).toHaveCount(0);
  await uncomputableImpact.getByRole("button", { name: "Cancel" }).click();

  await page.getByRole("button", { name: "Archive decision" }).click();
  const archiveDialog = page.getByRole("dialog", { name: "Archive this decision?" });
  await expect(archiveDialog).toBeVisible();
  const archiveBodies: Array<Record<string, unknown>> = [];
  await page.route(`**/decisions/${decisionId}/archive`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    archiveBodies.push(route.request().postDataJSON() as Record<string, unknown>);
    const response = await route.fetch();
    if (archiveBodies.length === 1) {
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
      return;
    }
    await route.fulfill({ response });
  });
  await archiveDialog.getByRole("button", { name: "Archive decision", exact: true }).click();
  await expect(archiveDialog.getByRole("button", { name: "Retry same archive action" })).toBeVisible();
  await archiveDialog.getByRole("button", { name: "Retry same archive action" }).click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible();
  expect(archiveBodies).toHaveLength(2);
  expect(archiveBodies[1]).toEqual(archiveBodies[0]);
  await page.unroute(`**/decisions/${decisionId}/archive`);
  const archivedRow = page.getByRole("table", { name: "Archived decisions" }).getByRole("row", { name: new RegExp(decisionName) });
  await expect(archivedRow).toBeVisible();
  const retainedRevisions = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}/revisions?limit=50`,
    { headers: { Origin: origin, "X-Deykit-Capability": capability as string } },
  );
  expect((await retainedRevisions.json()).data.items).toHaveLength(2);
  await archivedRow.getByRole("button", { name: "Restore", exact: true }).click();
  await expect(page.getByRole("table", { name: "Project decisions" })).toContainText(decisionName);

  await page.getByRole("button", { name: "Providers", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Providers" })).toBeVisible();
  await page.getByRole("button", { name: "Add provider profile" }).click();
  await expect(page.getByRole("heading", { name: "New profile" })).toBeVisible();
  await expect(page.getByLabel("Adapter")).toHaveValue("jev");
  await page.getByLabel("Requested model ID").fill("jev-latest");
  await page.getByLabel("Destination").fill("https://api.typesafe.ai/v1/systemone");
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByText("Not configured · Unavailable", { exact: false })).toBeVisible();
  await expect(page.getByText("Explicit network check · 0 inference calls.")).toBeVisible();
  const environmentName = "M08_FAKE_ENV";
  await page.getByLabel("Environment variable name").fill(environmentName);
  await page.getByRole("button", { name: "Attach environment reference" }).click();
  await expect(page.getByText(environmentName)).toHaveCount(0);
  await expect(page.getByText("Configured · Available", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Refresh model list" }).click();
  await expect(page.getByText("fake-offline-model", { exact: true })).toBeVisible();
  await expect(page.getByText("1 models returned · network checked · 0 inference calls")).toBeVisible();

  const providerProfilesResponse = await page.request.get(
    `/api/v1/projects/${registrationId}/providers?limit=100`,
    { headers: authorizedHeaders },
  );
  expect(providerProfilesResponse.status()).toBe(200);
  const configuredProvider = (await providerProfilesResponse.json()).data.items.find(
    (item: { adapter: string; requested_model: string }) =>
      item.adapter === "jev" && item.requested_model === "jev-latest",
  );
  expect(configuredProvider).toBeTruthy();
  const credentialValue = "synthetic-installed-os-credential-never-real";
  const credentialBodies: Array<Record<string, unknown>> = [];
  let firstCredentialStatus: number | undefined;
  await page.route(`**/providers/${configuredProvider.id}/credential-os-store`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    credentialBodies.push(route.request().postDataJSON() as Record<string, unknown>);
    const response = await route.fetch();
    if (credentialBodies.length === 1) {
      firstCredentialStatus = response.status();
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
      return;
    }
    await route.fulfill({ response });
  });
  const secretInput = page.getByLabel("Store a credential in the operating system");
  await secretInput.fill(credentialValue);
  await page.getByRole("button", { name: "Store credential" }).click();
  await expect(page.getByRole("button", { name: "Retry the same credential request" })).toBeVisible();
  await expect(secretInput).toHaveValue("");
  await expect(secretInput).toBeDisabled();
  await expect(page.getByRole("button", { name: "Store credential" })).toBeDisabled();
  expect(await page.locator("body").innerText()).not.toContain(credentialValue);
  await page.getByRole("button", { name: "Retry the same credential request" }).click();
  await expect(page.getByText("Configured · Available", { exact: false })).toBeVisible();
  expect(firstCredentialStatus).toBe(200);
  expect(credentialBodies).toHaveLength(2);
  expect(credentialBodies[1]).toEqual(credentialBodies[0]);
  expect(typeof credentialBodies[0].credential_value).toBe("string");
  expect((credentialBodies[0].credential_value as string).length).toBe(credentialValue.length);
  expect(await page.locator("body").innerText()).not.toContain(credentialValue);
  await page.unroute(`**/providers/${configuredProvider.id}/credential-os-store`);
  await page.screenshot({ path: testInfo.outputPath("provider-setup.png"), fullPage: true });

  await page.getByRole("button", { name: "Fixtures", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Fixtures" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("fixture-setup.png"), fullPage: true });

  // Inspect the packaged authored fixture through the installed UI and API.
  // The test never invokes provider networking or requests raw-source display.
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Welcome to deykit." })).toBeVisible();
  await page.getByRole("button", { name: "Try support demo", exact: true }).click();
  const fixtureDemoPath = testInfo.outputPath("fixture-support-demo");
  await page.getByLabel("Project folder path").fill(fixtureDemoPath);
  await page.getByRole("dialog").getByRole("button", { name: "Try support demo", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sandbox", exact: true })).toBeVisible();
  const fixtureRegistrationId = new URL(page.url()).hash.match(/^#\/p\/([A-Za-z0-9_-]+)/)?.[1] as string;
  const fixtureHeaders = { Origin: origin, "X-Deykit-Capability": capability as string };
  const fixtureProvidersResponse = await page.request.get(
    `/api/v1/projects/${fixtureRegistrationId}/providers?limit=100`,
    { headers: fixtureHeaders },
  );
  expect(fixtureProvidersResponse.status()).toBe(200);
  const fixtureProvider = (await fixtureProvidersResponse.json()).data.items.find(
    (item: { adapter: string }) => item.adapter === "fixture",
  );
  expect(fixtureProvider).toMatchObject({
    requested_model: expect.stringMatching(/^authored-/),
    destination: "fixture:jev-choice",
    evidence_mode: "authored_fixture",
  });
  const fixturePage = await page.request.get(
    `/api/v1/projects/${fixtureRegistrationId}/fixtures?limit=50`,
    { headers: fixtureHeaders },
  );
  expect(fixturePage.status()).toBe(200);
  const fixtureSummary = (await fixturePage.json()).data.items[0];
  expect(fixtureSummary).toMatchObject({
    decision_id: expect.any(String),
    dataset_id: expect.any(String),
    model_identity: expect.stringMatching(/^authored-/),
  });
  expect(Number(fixtureSummary.binding_count)).toBeGreaterThan(0);
  expect(fixtureSummary.bindings.length).toBeGreaterThan(0);
  for (const binding of fixtureSummary.bindings) {
    expect(binding.case_id).toEqual(expect.any(String));
    expect(binding.request_hash).toMatch(/^[a-f0-9]{64}$/);
    expect(binding.model_identity).toBe(fixtureSummary.model_identity);
  }
  await page.getByRole("button", { name: "Providers", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Providers" })).toBeVisible();
  await page.getByRole("button", { name: fixtureProvider.id, exact: true }).click();
  await expect(page.getByRole("heading", { name: "Authored fixture profile" })).toBeVisible();
  await expect(page.locator(".fixture-provider")).toContainText(fixtureProvider.requested_model);
  await expect(page.getByLabel("Environment variable name")).toHaveCount(0);
  await expect(page.getByLabel("Store a credential in the operating system")).toHaveCount(0);
  await expect(page.getByLabel("Destination")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Refresh model list" })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("fixture-provider-safe-details.png"), fullPage: true });
  await page.getByRole("button", { name: "Open fixture library" }).click();
  await expect(page.getByRole("heading", { name: "Fixture library" })).toBeVisible();
  await page.getByRole("button", { name: "Fixtures", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Fixture library" })).toBeVisible();
  await page.getByRole("button", { name: fixtureSummary.name, exact: true }).click();
  await expect(page.getByRole("heading", { name: fixtureSummary.name, exact: true })).toBeVisible();
  await expect(page.getByRole("table", { name: "Exact authored case bindings" })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Show exact stored request source text" })).not.toBeChecked();
  const fixtureDetail = await page.request.get(
    `/api/v1/projects/${fixtureRegistrationId}/fixtures/${fixtureSummary.id}?include_requests=false`,
    { headers: fixtureHeaders },
  );
  expect(fixtureDetail.status()).toBe(200);
  expect((await fixtureDetail.json()).data).toMatchObject({
    id: fixtureSummary.id,
    decision_id: fixtureSummary.decision_id,
    dataset_id: fixtureSummary.dataset_id,
    model_identity: fixtureSummary.model_identity,
    requests: [],
  });
  await page.screenshot({ path: testInfo.outputPath("fixture-exact-bindings.png"), fullPage: true });

  const bindingSources = execFileSync(
    "python",
    [
      "-c",
      "import sys; from pathlib import Path; from deykit.contracts.codec import dump_record, load_record; from deykit.contracts.records import FixtureSet; record = load_record(FixtureSet, (Path(sys.argv[1]) / 'source' / 'fixtures' / (sys.argv[2] + '.json')).read_bytes()); print('\\n'.join(dump_record(binding).decode('utf-8') for binding in record.bindings))",
      fixtureDemoPath,
      fixtureSummary.id,
    ],
    { encoding: "utf8" },
  ).trimEnd().split("\n");
  await page.getByLabel("Decision").selectOption(fixtureSummary.decision_id);
  await page.getByLabel("Dataset").selectOption(fixtureSummary.dataset_id);
  await page.getByRole("button", { name: "Author fixture set" }).click();
  await page.getByLabel("Fixture set name").fill("Browser authored exact copy");
  await page.getByLabel("Model identity").fill(fixtureSummary.model_identity);
  await page.getByLabel("Strict binding source lines").fill(bindingSources.join("\n"));
  await page.getByRole("button", { name: "Create authored set" }).click();
  await expect(page.getByRole("heading", { name: "Browser authored exact copy" })).toBeVisible();
  const createdFixtureId = await page.locator(".fixture-detail code").first().textContent();
  expect(createdFixtureId).toMatch(/^fixture-[A-Za-z0-9_-]+$/);
  const createdFixture = await page.request.get(
    `/api/v1/projects/${fixtureRegistrationId}/fixtures/${createdFixtureId as string}?include_requests=false`,
    { headers: fixtureHeaders },
  );
  expect(createdFixture.status()).toBe(200);
  const createdFixtureData = (await createdFixture.json()).data;
  expect(createdFixtureData).toMatchObject({
    name: "Browser authored exact copy",
    decision_id: fixtureSummary.decision_id,
    dataset_id: fixtureSummary.dataset_id,
    model_identity: fixtureSummary.model_identity,
  });
  expect(createdFixtureData.bindings.map((binding: { request_hash: string }) => binding.request_hash)).toEqual(
    fixtureSummary.bindings.map((binding: { request_hash: string }) => binding.request_hash),
  );
  expect(createdFixtureData.requests).toEqual([]);

  await page.setViewportSize({ width: 320, height: 800 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("authoring-narrow-320.png"), fullPage: true });

  expect(apiResponses.every((url) => new URL(url).origin === origin)).toBe(true);
  expect(apiResponses.every((url) => !url.includes(capability as string))).toBe(true);
  expect(page.url()).not.toContain(capability as string);
  expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  expect(await page.evaluate(() => (document as Document & { cookie: string }).cookie)).toBe("");
});
