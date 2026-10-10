import { expect, test } from "@playwright/test";
import type { APIResponse, Request, Response } from "@playwright/test";
import type { ApiOperationData } from "../src/api/client";
import { execFileSync } from "node:child_process";
import { writeFile } from "node:fs/promises";
import { operationMetadata } from "../src/api/generated/operations";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function safeErrorIdentifier(value: unknown): string | null {
  return typeof value === "string" && /^[a-z][a-z0-9_]*$/.test(value)
    ? value
    : null;
}

function safeRoutePattern(pathname: string): string {
  const route = Object.values(operationMetadata)
    .map(({ path }) => path.split("/"))
    .find((templateSegments) => {
      const pathSegments = pathname.split("/");
      return (
        pathSegments.length === templateSegments.length &&
        templateSegments.every((segment, index) =>
          /^\{[a-z_]+\}$/.test(segment)
            ? pathSegments[index] !== ""
            : pathSegments[index] === segment,
        )
      );
    });
  if (!route) return "<unknown-route>";
  return route
    .map((segment) =>
      /^\{[a-z_]+\}$/.test(segment) ? `:${segment.slice(1, -1)}` : segment,
    )
    .join("/");
}

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
    .getByRole("button", { name: "Reconnect", exact: true })
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

test("installed browser authors exact decision source and previews imports through real APIs", async ({
  page,
}, testInfo) => {
  test.setTimeout(600_000);
  page.setDefaultTimeout(10_000);
  const completedPhases: string[] = [];
  const screenshots: string[] = [];
  const actionTimings: Array<{
    action: "reapply_add" | "split_replay";
    stage: "receipt" | "readiness";
    elapsed_ms: number;
  }> = [];
  let activePhase = "Workspace bootstrap and project creation";
  let progressSequence = 0;
  const progressPath = testInfo.outputPath("authoring-progress.json");
  const initialViewport = page.viewportSize();
  const browserVersion = page.context().browser()?.version() ?? null;
  const apiFailures: Array<{
    route_pattern: string;
    status: number;
    code: string | null;
    reason: string | null;
  }> = [];
  const sourceReadEvents: Array<{
    event: "start" | "headers" | "body" | "body_error" | "cancelled";
    route_pattern: string;
    method: "GET";
    elapsed_ms: number;
    status?: number;
  }> = [];
  const sourceReadEventWaiters = new Set<() => void>();
  let pendingSourceReadCategories: string[] = [];
  let recordLateSourceReadProgress = false;
  let splitReadinessFacts:
    | {
        edit_enabled: boolean;
        option_a_enabled: boolean;
        selected_loading: boolean;
        labels_loading: boolean;
        selection_review_notice_present: boolean;
        error_present: boolean;
        saved_refresh_present: boolean;
        pending_route_categories: string[];
      }
    | undefined;
  let activeSplitReadEvents:
    | Array<{
        event: "body" | "body_error" | "cancelled";
        route_pattern: string;
        status?: number;
      }>
    | undefined;
  function recordSourceReadEvent(event: (typeof sourceReadEvents)[number]) {
    sourceReadEvents.push(event);
    if (sourceReadEvents.length > 160) sourceReadEvents.shift();
    if (
      activeSplitReadEvents &&
      (event.event === "body" ||
        event.event === "body_error" ||
        event.event === "cancelled")
    ) {
      activeSplitReadEvents.push({
        event: event.event,
        route_pattern: event.route_pattern,
        ...(event.status === undefined ? {} : { status: event.status }),
      });
      for (const notify of sourceReadEventWaiters) notify();
    }
  }
  const sourceReadStarts = new WeakMap<
    Request,
    { route_pattern: string; startedAt: number }
  >();
  const sourceReadTemplates = new Set(
    Object.values(operationMetadata)
      .filter(
        ({ method, path }) =>
          method === "GET" &&
          path.includes("/projects/{registration_id}/") &&
          /(overview|datasets|cases|labels)/.test(path),
      )
      .map(({ path }) => path.replace(/\{([a-z_]+)\}/g, ":$1")),
  );
  let progressWriteQueue: Promise<void> = Promise.resolve();
  function recordProgress(): Promise<void> {
    const body = JSON.stringify({
      active_phase: activePhase,
      completed_phases: completedPhases,
      screenshots,
      action_timings: actionTimings,
      browser_version: browserVersion,
      initial_viewport: initialViewport,
      api_failures: apiFailures,
      source_read_events: sourceReadEvents,
      pending_source_read_categories: pendingSourceReadCategories,
      split_readiness_facts: splitReadinessFacts,
    });
    const sequence = ++progressSequence;
    const write = progressWriteQueue.then(async () => {
      await writeFile(progressPath, `${body}\n`, "utf8");
      await testInfo.attach(`authoring-progress-${sequence}`, {
        body: `${body}\n`,
        contentType: "application/json",
      });
    });
    progressWriteQueue = write.catch(() => undefined);
    return write;
  }
  async function recordDirectApiFailure(response: APIResponse, path: string) {
    if (response.status() < 400) return;
    const body: unknown = await response.json().catch(() => undefined);
    const error = isRecord(body) ? body.error : undefined;
    const details = isRecord(error) ? error : undefined;
    apiFailures.push({
      route_pattern: safeRoutePattern(path),
      status: response.status(),
      code: safeErrorIdentifier(details?.code),
      reason: safeErrorIdentifier(details?.reason),
    });
    await recordProgress();
  }
  async function expectDirectDataEnvelope(response: APIResponse, path: string) {
    await recordDirectApiFailure(response, path);
    expect(response.status()).toBe(200);
    const envelope: unknown = await response.json();
    expect(
      isRecord(envelope) &&
        envelope.schema_version === 1 &&
        isRecord(envelope.data),
    ).toBe(true);
  }
  async function enterPhase(name: string) {
    completedPhases.push(activePhase);
    activePhase = name;
    await recordProgress();
  }
  async function captureScreenshot(name: string) {
    await page.screenshot({ path: testInfo.outputPath(name), fullPage: true });
    screenshots.push(name);
    await recordProgress();
  }
  async function openDecisionSourceEditor() {
    const editor = page.getByLabel("Decision source");
    if (!(await editor.isVisible()))
      await page.getByText("Advanced editor source", { exact: true }).click();
    await expect(editor).toBeVisible();
    return editor;
  }
  function caseButton(caseId: string) {
    return page
      .getByRole("region", { name: /^Cases in / })
      .getByRole("button", { name: caseId, exact: true });
  }
  await recordProgress();

  const projectName = "M10 authoring acceptance";
  let decisionName = "Precise source decision";
  const projectPath = testInfo.outputPath("authoring-project");
  const apiResponses: string[] = [];
  const bundledAssetOrigins: string[] = [];
  const importCommitBodies: Array<Record<string, unknown>> = [];
  const splitCommitBodies: Array<Record<string, unknown>> = [];
  const addBodies: Array<Record<string, unknown>> = [];
  const removeBodies: Array<Record<string, unknown>> = [];
  const mutationRequests: string[] = [];
  let capability: string | undefined;
  page.on("request", (request) => {
    apiResponses.push(request.url());
    if (
      (activePhase ===
        "Import row validation and explicit accepted-row commit" ||
        activePhase ===
          "Case source preservation and stale-label applicability") &&
      request.method() === "GET"
    ) {
      const routePattern = safeRoutePattern(new URL(request.url()).pathname);
      if (sourceReadTemplates.has(routePattern)) {
        const startedAt = Date.now();
        sourceReadStarts.set(request, {
          route_pattern: routePattern,
          startedAt,
        });
        sourceReadEvents.push({
          event: "start",
          route_pattern: routePattern,
          method: "GET",
          elapsed_ms: 0,
        });
        if (sourceReadEvents.length > 160) sourceReadEvents.shift();
        if (recordLateSourceReadProgress)
          void recordProgress().catch(() => undefined);
      }
    }
    if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method()))
      mutationRequests.push(
        `${request.method()} ${safeRoutePattern(new URL(request.url()).pathname)}`,
      );
    if (request.url().endsWith("/imports/commit")) {
      importCommitBodies.push(
        request.postDataJSON() as Record<string, unknown>,
      );
    }
    if (request.url().endsWith("/splits/commit"))
      splitCommitBodies.push(request.postDataJSON() as Record<string, unknown>);
  });
  page.on("response", (response) => {
    const resourceType = response.request().resourceType();
    if (
      (resourceType === "script" || resourceType === "stylesheet") &&
      new URL(response.url()).pathname.includes("/assets/")
    )
      bundledAssetOrigins.push(new URL(response.url()).origin);
  });
  page.on("response", async (response) => {
    const sourceRead = sourceReadStarts.get(response.request());
    if (sourceRead) {
      sourceReadEvents.push({
        event: "headers",
        route_pattern: sourceRead.route_pattern,
        method: "GET",
        elapsed_ms: Math.max(0, Date.now() - sourceRead.startedAt),
        status: response.status(),
      });
      if (sourceReadEvents.length > 160) sourceReadEvents.shift();
      void recordProgress().catch(() => undefined);
      void response
        .body()
        .then(() => {
          sourceReadEvents.push({
            event: "body",
            route_pattern: sourceRead.route_pattern,
            method: "GET",
            elapsed_ms: Math.max(0, Date.now() - sourceRead.startedAt),
            status: response.status(),
          });
          if (sourceReadEvents.length > 160) sourceReadEvents.shift();
          return recordProgress();
        })
        .catch(() => {
          sourceReadEvents.push({
            event: "body_error",
            route_pattern: sourceRead.route_pattern,
            method: "GET",
            elapsed_ms: Math.max(0, Date.now() - sourceRead.startedAt),
            status: response.status(),
          });
          if (sourceReadEvents.length > 160) sourceReadEvents.shift();
          return recordProgress();
        });
    }
    if (response.status() >= 400) {
      const body = await response.json().catch(() => undefined);
      const error = isRecord(body) ? body.error : undefined;
      const details = isRecord(error) ? error : undefined;
      apiFailures.push({
        route_pattern: safeRoutePattern(new URL(response.url()).pathname),
        status: response.status(),
        code: safeErrorIdentifier(details?.code),
        reason: safeErrorIdentifier(details?.reason),
      });
      await recordProgress();
    }
    if (response.url().endsWith("/api/v1/session/bootstrap")) {
      const body = await response.json().catch(() => undefined);
      if (typeof body?.data?.capability === "string")
        capability = body.data.capability;
    }
  });

  await page.clock.install();
  await page.clock.resume();
  const shell = await page.goto("/");
  expect(shell?.status()).toBe(200);
  expect(shell?.headers()["content-security-policy"]).toContain(
    "frame-ancestors 'none'",
  );
  expect(bundledAssetOrigins.length).toBeGreaterThan(0);
  expect(
    bundledAssetOrigins.every(
      (assetOrigin) => assetOrigin === new URL(page.url()).origin,
    ),
  ).toBe(true);
  await expect(
    page.getByRole("heading", { name: "Welcome to deykit." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Create project" }).click();
  await page.getByLabel("Project name").fill(projectName);
  await page.getByLabel("Project folder path").fill(projectPath);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible();
  await enterPhase("Dataset creation and first import mapping");

  await page
    .getByRole("button", { name: "Create dataset", exact: true })
    .click();
  await page.getByLabel("Dataset name").fill("Imported before decision");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Create dataset", exact: true })
    .click();
  await expect(page.getByRole("heading", { name: "Examples" })).toBeVisible();
  await captureScreenshot("examples-before-decision.png");

  await enterPhase("Serialized opaque mapping transforms and import preview");
  await page
    .getByRole("button", { name: "Project examples", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Import examples", exact: true })
    .click();
  await page
    .getByLabel("Import source text")
    .fill("id,input\nseed-1,first imported input\n");
  const mappingBodies: Array<Record<string, unknown>> = [];
  let firstMappingSource: string | undefined;
  let finalMappingSource: string | undefined;
  let releaseFirstMapping!: () => void;
  let reportFirstMapping!: () => void;
  let reportSecondMapping!: () => void;
  const firstMappingGate = new Promise<void>((resolve) => {
    releaseFirstMapping = resolve;
  });
  const firstMappingStarted = new Promise<void>((resolve) => {
    reportFirstMapping = resolve;
  });
  const secondMappingFinished = new Promise<void>((resolve) => {
    reportSecondMapping = resolve;
  });
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
  await expect(
    page.getByRole("button", { name: "Preview all rows" }),
  ).toBeDisabled();
  expect(mappingBodies).toHaveLength(1);
  releaseFirstMapping();
  await secondMappingFinished;
  expect(mappingBodies).toHaveLength(2);
  expect(mappingBodies[1].mapping_source).toBe(firstMappingSource);
  await expect(page.getByLabel("id column")).toHaveValue("id");
  await expect(page.getByLabel("input column")).toHaveValue("input");
  await expect(
    page.getByRole("button", { name: "Preview all rows" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Preview all rows" }).click();
  await expect.poll(() => previewBodies.length).toBe(1);
  expect(previewBodies[0].mapping_source).toBe(finalMappingSource);
  await expect(
    page.getByRole("heading", { name: "Import review" }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "1 rows · 1 valid · 0 rejected" }),
  ).toBeVisible();
  await captureScreenshot("import-before-decision.png");
  await page.getByRole("button", { name: "Import cases" }).click();
  await expect(caseButton("seed-1")).toBeVisible();
  const initialImportHash = new URL(page.url()).hash;
  const registrationId = initialImportHash.match(
    /^#\/p\/([A-Za-z0-9_-]+)/,
  )?.[1] as string;
  const datasetId = new URLSearchParams(
    initialImportHash.split("?")[1] ?? "",
  ).get("dataset") as string;

  await page.getByRole("button", { name: projectName, exact: true }).click();
  await enterPhase(
    "Exact decision source authoring and API/CLI conflict recovery",
  );
  await page
    .getByRole("button", { name: "Create decision", exact: true })
    .click();
  await page.getByLabel("Decision name").fill(decisionName);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Create decision", exact: true })
    .click();
  await expect(page.getByLabel("Question")).toBeVisible();
  const schemaSource =
    '{"type":"object","properties":{"large":{"const":9007199254740993},"fraction":{"multipleOf":0.1234567890123456789}}}';
  await page.getByLabel("Advanced JSON Schema source").fill(schemaSource);
  await page.getByLabel("Advanced JSON Schema source").press("Tab");
  await expect(page.locator(".document-title-row [role=status]")).toHaveText(
    "Draft saved",
  );
  const initialDecisionMatch = new URL(page.url()).hash.match(
    /\/d\/([A-Za-z0-9_-]+)/,
  );
  if (!initialDecisionMatch?.[1])
    throw new Error("The created decision is missing from the current route.");
  if (typeof capability !== "string")
    throw new Error("The local API capability was not initialized.");
  const initialOrigin = new URL(page.url()).origin;
  const initialSchemaResponse = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${initialDecisionMatch[1]}`,
    {
      headers: {
        Origin: initialOrigin,
        "X-Deykit-Capability": capability,
      },
    },
  );
  expect(initialSchemaResponse.status()).toBe(200);
  const initialSchemaDecision = (await initialSchemaResponse.json()).data;
  expect(initialSchemaDecision.draft.record.editor_source).toContain(
    JSON.stringify(schemaSource),
  );
  await captureScreenshot("decision-json-schema-initial-exact.png");

  const schemaCompositionEditor = page.getByLabel(
    "Advanced JSON Schema source",
  );
  const intermediateCompositionSource =
    '{"type":"object","properties":{"ime":{"const":"intermediate"}}}';
  const committedCompositionSource =
    '{"type":"object","properties":{"ime":{"const":"committed"}}}';
  const compositionTransforms: Array<Record<string, unknown>> = [];
  await page.route("**/editor-transform", async (route) => {
    if (route.request().method() === "POST")
      compositionTransforms.push(
        route.request().postDataJSON() as Record<string, unknown>,
      );
    await route.continue();
  });
  const compositionTransformResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/editor-transform") &&
      response.request().method() === "POST",
  );
  await schemaCompositionEditor.focus();
  await schemaCompositionEditor.dispatchEvent("compositionstart", { data: "" });
  await schemaCompositionEditor.fill(intermediateCompositionSource);
  await schemaCompositionEditor.evaluate((editor) => editor.blur());
  await schemaCompositionEditor.evaluate((editor, committedSource) => {
    const setter = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value",
    )?.set;
    setter?.call(editor, committedSource);
    editor.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        inputType: "insertCompositionText",
        data: "",
      }),
    );
    editor.dispatchEvent(
      new CompositionEvent("compositionend", { bubbles: true, data: "" }),
    );
  }, committedCompositionSource);
  await compositionTransformResponse;
  expect(compositionTransforms).toHaveLength(1);
  expect(compositionTransforms[0].edit).toEqual({
    kind: "replace_schema",
    input_schema_source: committedCompositionSource,
  });
  expect(compositionTransforms[0].editor_source).not.toContain("intermediate");
  await page.unroute("**/editor-transform");
  await expect(page.locator(".document-title-row [role=status]")).toHaveText(
    "Draft saved",
  );

  const pendingBlurSource =
    '{"type":"object","properties":{"queued":{"const":"blurred"}}}';
  const interruptedCompositionSource =
    '{"type":"object","properties":{"ime":{"const":"intermediate-after-blur"}}}';
  const committedAfterBlurSource =
    '{"type":"object","properties":{"ime":{"const":"committed-after-blur"}}}';
  const pausedCompositionTransforms: Array<Record<string, unknown>> = [];
  const pausedCompositionResponses: number[] = [];
  page.on("response", (response) => {
    if (
      response.url().endsWith("/editor-transform") &&
      response.request().method() === "POST"
    )
      pausedCompositionResponses.push(response.status());
  });
  await page.route("**/editor-transform", async (route) => {
    if (route.request().method() === "POST")
      pausedCompositionTransforms.push(
        route.request().postDataJSON() as Record<string, unknown>,
      );
    await route.continue();
  });
  await schemaCompositionEditor.fill(pendingBlurSource);
  await schemaCompositionEditor.evaluate((editor) => editor.blur());
  await schemaCompositionEditor.focus();
  await schemaCompositionEditor.dispatchEvent("compositionstart", {
    data: "",
  });
  await schemaCompositionEditor.fill(interruptedCompositionSource);
  await page.waitForTimeout(600);
  expect(pausedCompositionTransforms).toHaveLength(0);
  const composingDecisionHash = new URL(page.url()).hash;
  await page.getByRole("button", { name: projectName, exact: true }).click();
  const compositionNavigationGuard = page.getByRole("dialog", {
    name: "Unsaved changes",
  });
  await expect(compositionNavigationGuard).toBeVisible();
  expect(new URL(page.url()).hash).toBe(composingDecisionHash);
  expect(pausedCompositionTransforms).toHaveLength(0);
  await compositionNavigationGuard
    .getByRole("button", { name: "Keep editing", exact: true })
    .click();
  await schemaCompositionEditor.evaluate((editor, committedSource) => {
    const setter = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value",
    )?.set;
    setter?.call(editor, committedSource);
    editor.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        inputType: "insertCompositionText",
        data: "",
      }),
    );
    editor.dispatchEvent(
      new CompositionEvent("compositionend", { bubbles: true, data: "" }),
    );
  }, committedAfterBlurSource);
  await expect
    .poll(() => pausedCompositionResponses.length, { timeout: 10000 })
    .toBe(2);
  expect(pausedCompositionTransforms).toHaveLength(2);
  expect(pausedCompositionTransforms[0].edit).toEqual({
    kind: "replace_schema",
    input_schema_source: pendingBlurSource,
  });
  expect(pausedCompositionTransforms[1].edit).toEqual({
    kind: "replace_schema",
    input_schema_source: committedAfterBlurSource,
  });
  expect(pausedCompositionTransforms[1].editor_source).not.toContain(
    "intermediate-after-blur",
  );
  expect(pausedCompositionResponses.every((status) => status === 200)).toBe(
    true,
  );
  await page.unroute("**/editor-transform");
  await expect(page.locator(".document-title-row [role=status]")).toHaveText(
    "Draft saved",
  );
  await captureScreenshot("decision-json-schema.png");

  const registrationMatch = new URL(page.url()).hash.match(
    /^#\/p\/([A-Za-z0-9_-]+)/,
  );
  const decisionMatch = new URL(page.url()).hash.match(/\/d\/([A-Za-z0-9_-]+)/);
  expect(registrationMatch).not.toBeNull();
  expect(decisionMatch).not.toBeNull();
  expect(capability).toMatch(/^[A-Za-z0-9_-]{43}$/);
  const origin = new URL(page.url()).origin;
  const authorizedHeaders = {
    Origin: origin,
    "X-Deykit-Capability": capability as string,
  };
  expect(registrationMatch?.[1]).toBe(registrationId);
  const decisionId = decisionMatch?.[1] as string;
  const stored = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  expect(stored.status()).toBe(200);
  const decision = (await stored.json()).data;
  expect(decision.draft.record.editor_source).toContain(
    JSON.stringify(committedAfterBlurSource),
  );

  await enterPhase("Failed transforms remain pending until explicit retry");
  const failedTransformRequests: Array<Record<string, unknown>> = [];
  const blockedVersionRequests: Array<Record<string, unknown>> = [];
  let failFirstTransform = true;
  await page.route("**/editor-transform", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    failedTransformRequests.push(
      route.request().postDataJSON() as Record<string, unknown>,
    );
    if (failFirstTransform) {
      failFirstTransform = false;
      await route.abort("failed");
      return;
    }
    await route.continue();
  });
  await page.route(`**/decisions/${decisionId}/revisions`, async (route) => {
    if (route.request().method() === "POST")
      blockedVersionRequests.push(
        route.request().postDataJSON() as Record<string, unknown>,
      );
    await route.continue();
  });
  await page.getByLabel("Question").fill("Retained before transform failure");
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  const retryPendingEdits = page.getByRole("button", {
    name: "Retry pending edits",
  });
  await expect(retryPendingEdits).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save version", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Retry same version save" }),
  ).toHaveCount(0);
  expect(failedTransformRequests).toHaveLength(1);
  const emptyCompositionEditor = page.getByLabel("Advanced JSON Schema source");
  const emptyCompositionValue = await emptyCompositionEditor.inputValue();
  await emptyCompositionEditor.focus();
  await emptyCompositionEditor.dispatchEvent("compositionstart", { data: "" });
  await emptyCompositionEditor.dispatchEvent("compositionend", { data: "" });
  await expect(retryPendingEdits).toBeEnabled();
  await expect(page.locator(".document-title-row [role=status]")).toHaveText(
    "Changes not saved",
  );
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  await expect(retryPendingEdits).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save version", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Retry same version save" }),
  ).toHaveCount(0);
  expect(blockedVersionRequests).toHaveLength(0);
  expect(failedTransformRequests).toHaveLength(1);
  expect(await emptyCompositionEditor.inputValue()).toBe(emptyCompositionValue);
  const firstRetryDraft = page.waitForResponse(
    (response) =>
      response.url().endsWith("/draft") &&
      response.request().method() === "PUT",
  );
  await retryPendingEdits.click();
  await expect.poll(() => failedTransformRequests.length).toBe(2);
  expect(failedTransformRequests[1]).toEqual(failedTransformRequests[0]);
  expect((await firstRetryDraft).status()).toBe(200);
  await expect(page.getByLabel("Question")).toHaveValue(
    "Retained before transform failure",
  );
  await expect(retryPendingEdits).toHaveCount(0);

  await enterPhase("Draft uncertainty does not create a version retry");
  let failFirstDraftSave = true;
  await page.route("**/draft", async (route) => {
    if (route.request().method() === "PUT" && failFirstDraftSave) {
      failFirstDraftSave = false;
      await route.abort("failed");
      return;
    }
    await route.continue();
  });
  await page.getByLabel("Question").fill("Question before draft uncertainty");
  await page.getByLabel("Question").press("Tab");
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  await expect(page.locator(".document-title-row [role=status]")).toHaveText(
    "Save outcome unknown",
  );
  await expect(
    page.getByRole("button", { name: "Save version", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Retry same version save" }),
  ).toHaveCount(0);
  expect(blockedVersionRequests).toHaveLength(0);
  await page.getByRole("button", { name: "Retry unchanged save" }).click();
  await expect(page.locator(".document-title-row [role=status]")).toHaveText(
    "Draft saved",
  );
  await page.unroute("**/draft");

  await enterPhase(
    "Authoritative read failure does not create a version retry",
  );
  await page.route(
    `**/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          schema_version: 1,
          error: {
            schema_version: 1,
            code: "internal_error",
            reason: "decision_read_failed",
            message: "Read unavailable",
          },
        }),
      });
    },
  );
  const failedAuthoritativeRead = page.waitForResponse(
    (response) =>
      response.url().includes(`/decisions/${decisionId}`) &&
      response.request().method() === "GET" &&
      response.status() === 503,
  );
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  await failedAuthoritativeRead;
  await expect(
    page.getByRole("button", { name: "Save version", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Retry same version save" }),
  ).toHaveCount(0);
  expect(blockedVersionRequests).toHaveLength(0);
  await page.unroute(
    `**/api/v1/projects/${registrationId}/decisions/${decisionId}`,
  );

  await enterPhase("Transform failure during IME retains ordered edits");
  const composingFailureRequests: Array<Record<string, unknown>> = [];
  let releaseComposingFailure!: () => void;
  let reportComposingFailureStarted!: () => void;
  const composingFailureGate = new Promise<void>((resolve) => {
    releaseComposingFailure = resolve;
  });
  const composingFailureStarted = new Promise<void>((resolve) => {
    reportComposingFailureStarted = resolve;
  });
  await page.route("**/editor-transform", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    composingFailureRequests.push(
      route.request().postDataJSON() as Record<string, unknown>,
    );
    if (composingFailureRequests.length === 1) {
      reportComposingFailureStarted();
      await composingFailureGate;
      await route.abort("failed");
      return;
    }
    await route.continue();
  });
  await page.getByLabel("Question").fill("Retained during composition failure");
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  await composingFailureStarted;
  const failedDuringCompositionEditor = page.getByLabel(
    "Advanced JSON Schema source",
  );
  const failedDuringCompositionSource =
    '{"type":"object","properties":{"recovery":{"const":"committed-after-failure"}}}';
  const intermediateFailureSource =
    '{"type":"object","properties":{"recovery":{"const":"intermediate-after-failure"}}}';
  await failedDuringCompositionEditor.focus();
  await failedDuringCompositionEditor.dispatchEvent("compositionstart", {
    data: "",
  });
  await failedDuringCompositionEditor.fill(intermediateFailureSource);
  releaseComposingFailure();
  await expect(retryPendingEdits).toBeVisible();
  await expect(retryPendingEdits).toBeDisabled();
  expect(blockedVersionRequests).toHaveLength(0);
  await failedDuringCompositionEditor.evaluate((editor, committedSource) => {
    const setter = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value",
    )?.set;
    setter?.call(editor, committedSource);
    editor.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        inputType: "insertCompositionText",
        data: "",
      }),
    );
    editor.dispatchEvent(
      new CompositionEvent("compositionend", { bubbles: true, data: "" }),
    );
  }, failedDuringCompositionSource);
  await expect(retryPendingEdits).toBeEnabled();
  expect(composingFailureRequests).toHaveLength(1);
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  await expect(retryPendingEdits).toBeVisible();
  expect(blockedVersionRequests).toHaveLength(0);
  expect(composingFailureRequests).toHaveLength(1);
  const recoveredFailureDraft = page.waitForResponse(
    (response) =>
      response.url().endsWith("/draft") &&
      response.request().method() === "PUT",
  );
  await retryPendingEdits.click();
  await expect.poll(() => composingFailureRequests.length).toBe(3);
  expect(composingFailureRequests[0].edit).toEqual({
    kind: "set_instructions",
    value: "Retained during composition failure",
  });
  expect(composingFailureRequests[1]).toEqual(composingFailureRequests[0]);
  expect(composingFailureRequests[2].edit).toEqual({
    kind: "replace_schema",
    input_schema_source: failedDuringCompositionSource,
  });
  expect(composingFailureRequests[2].editor_source).toContain(
    "Retained during composition failure",
  );
  expect(composingFailureRequests[2].editor_source).not.toContain(
    "intermediate-after-failure",
  );
  expect((await recoveredFailureDraft).status()).toBe(200);
  expect(blockedVersionRequests).toHaveLength(0);
  await page.unroute("**/editor-transform");
  await page.unroute(`**/decisions/${decisionId}/revisions`);
  await expect(page.locator(".document-title-row [role=status]")).toHaveText(
    "Draft saved",
  );

  await enterPhase("Obsolete transform settles before raw IME acknowledgement");
  let releaseObsoleteTransform!: () => void;
  let reportObsoleteTransformStarted!: () => void;
  const obsoleteTransformGate = new Promise<void>((resolve) => {
    releaseObsoleteTransform = resolve;
  });
  const obsoleteTransformStarted = new Promise<void>((resolve) => {
    reportObsoleteTransformStarted = resolve;
  });
  await page.route("**/editor-transform", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const transformed = await route.fetch();
    reportObsoleteTransformStarted();
    await obsoleteTransformGate;
    await route.fulfill({ response: transformed });
  });
  await page.getByLabel("Question").fill("Question from obsolete transform");
  await page.getByLabel("Question").press("Tab");
  await obsoleteTransformStarted;
  let rawDraftWrites = 0;
  const countRawDraftWrites = (request: Request) => {
    if (
      request.method() === "PUT" &&
      new URL(request.url()).pathname.endsWith("/draft")
    )
      rawDraftWrites += 1;
  };
  page.on("request", countRawDraftWrites);
  const obsoleteRawEditor = await openDecisionSourceEditor();
  const sourceBeforeReplacement = await obsoleteRawEditor.inputValue();
  const rawReplacementSource = sourceBeforeReplacement.replace(
    '"Retained during composition failure"',
    '"Raw replacement after stale transform"',
  );
  expect(rawReplacementSource).not.toBe(sourceBeforeReplacement);
  const rawIntermediateSource = rawReplacementSource.replace(
    '"Raw replacement after stale transform"',
    '"Raw intermediate composition"',
  );
  await obsoleteRawEditor.focus();
  await obsoleteRawEditor.dispatchEvent("compositionstart", { data: "" });
  await obsoleteRawEditor.fill(rawIntermediateSource);
  const rawReplacementAcknowledged = page.waitForResponse(
    (response) =>
      response.url().endsWith("/draft") &&
      response.request().method() === "PUT",
  );
  await obsoleteRawEditor.evaluate((editor, committedSource) => {
    const setter = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value",
    )?.set;
    setter?.call(editor, committedSource);
    editor.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        inputType: "insertCompositionText",
        data: "",
      }),
    );
    editor.dispatchEvent(
      new CompositionEvent("compositionend", { bubbles: true, data: "" }),
    );
  }, rawReplacementSource);
  await expect(obsoleteRawEditor).toHaveValue(rawReplacementSource);
  await expect(page.locator(".document-title-row [role=status]")).toHaveText(
    "Saving draft…",
  );
  expect(rawDraftWrites).toBe(0);
  const projectEditorPath = operationMetadata.projectDecisionEditor.path
    .replace("{registration_id}", registrationId)
    .replace("{decision_id}", decisionId);
  const rawReplacementProjection = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === projectEditorPath &&
      response.request().method() === "POST" &&
      (response.request().postDataJSON() as { editor_source?: string })
        .editor_source === rawReplacementSource,
  );
  releaseObsoleteTransform();
  expect((await rawReplacementAcknowledged).status()).toBe(200);
  expect(rawDraftWrites).toBe(1);
  await expect(page.locator(".document-title-row [role=status]")).toHaveText(
    "Draft saved",
  );
  page.off("request", countRawDraftWrites);
  const projectionResponse = await rawReplacementProjection;
  expect(projectionResponse.status()).toBe(200);
  await projectionResponse.body();
  const rawReplacementRead = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    { headers: authorizedHeaders },
  );
  if (!rawReplacementRead.ok()) {
    const failure = await rawReplacementRead.json().catch(() => undefined);
    const error = isRecord(failure) ? failure.error : undefined;
    const details = isRecord(error) ? error : undefined;
    apiFailures.push({
      route_pattern: safeRoutePattern(
        new URL(rawReplacementRead.url()).pathname,
      ),
      status: rawReplacementRead.status(),
      code: safeErrorIdentifier(details?.code),
      reason: safeErrorIdentifier(details?.reason),
    });
    await recordProgress();
  }
  expect(rawReplacementRead.status()).toBe(200);
  expect(
    (await rawReplacementRead.json()).data.draft.record.editor_source,
  ).toBe(rawReplacementSource);
  await page.unroute("**/editor-transform");
  await page.getByRole("button", { name: projectName, exact: true }).click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible();
  await expect(
    page.getByRole("dialog", { name: "Unsaved changes" }),
  ).toHaveCount(0);
  await page
    .getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: decisionName, exact: true })
    .click();
  const reopenedRawEditor = await openDecisionSourceEditor();
  await expect(reopenedRawEditor).toHaveValue(rawReplacementSource);

  await enterPhase("In-flight transform held across committed IME source");
  const inFlightCompositionSource =
    '{"type":"object","properties":{"ime":{"const":"in-flight-committed"},"large":{"const":9007199254740993},"fraction":{"multipleOf":0.1234567890123456789}}}';
  const inFlightIntermediateSource =
    '{"type":"object","properties":{"ime":{"const":"in-flight-intermediate"}}}';
  const inFlightTransforms: Array<Record<string, unknown>> = [];
  const pausedVersionRequests: Array<Record<string, unknown>> = [];
  let releaseInFlightTransform!: () => void;
  let reportInFlightTransform!: () => void;
  const inFlightTransformGate = new Promise<void>((resolve) => {
    releaseInFlightTransform = resolve;
  });
  const inFlightTransformStarted = new Promise<void>((resolve) => {
    reportInFlightTransform = resolve;
  });
  await page.route("**/editor-transform", async (route) => {
    if (route.request().method() === "POST") {
      inFlightTransforms.push(
        route.request().postDataJSON() as Record<string, unknown>,
      );
      if (inFlightTransforms.length === 1) {
        reportInFlightTransform();
        await inFlightTransformGate;
      }
    }
    await route.continue();
  });
  await page.route(`**/decisions/${decisionId}/revisions`, async (route) => {
    if (route.request().method() === "POST")
      pausedVersionRequests.push(
        route.request().postDataJSON() as Record<string, unknown>,
      );
    await route.continue();
  });
  await page.getByLabel("Question").fill("Question before IME composition");
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  await inFlightTransformStarted;
  const inFlightSchemaEditor = page.getByLabel("Advanced JSON Schema source");
  await inFlightSchemaEditor.focus();
  await inFlightSchemaEditor.dispatchEvent("compositionstart", { data: "" });
  await inFlightSchemaEditor.fill(inFlightIntermediateSource);
  releaseInFlightTransform();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "Finish composing or committing the editor source" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save version", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Retry same version save" }),
  ).toHaveCount(0);
  expect(pausedVersionRequests).toHaveLength(0);
  await expect(inFlightSchemaEditor).toHaveValue(inFlightIntermediateSource);
  const inFlightDraftSaved = page.waitForResponse(
    (response) =>
      response.url().endsWith("/draft") &&
      response.request().method() === "PUT",
  );
  await inFlightSchemaEditor.evaluate((editor, committedSource) => {
    const setter = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value",
    )?.set;
    setter?.call(editor, committedSource);
    editor.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        inputType: "insertCompositionText",
        data: "",
      }),
    );
    editor.dispatchEvent(
      new CompositionEvent("compositionend", { bubbles: true, data: "" }),
    );
  }, inFlightCompositionSource);
  await expect
    .poll(() => inFlightTransforms.length, { timeout: 10000 })
    .toBe(2);
  expect(inFlightTransforms[0].edit).toEqual({
    kind: "set_instructions",
    value: "Question before IME composition",
  });
  expect(inFlightTransforms[1].edit).toEqual({
    kind: "replace_schema",
    input_schema_source: inFlightCompositionSource,
  });
  expect(inFlightTransforms[1].editor_source).not.toContain(
    "in-flight-intermediate",
  );
  expect(pausedVersionRequests).toHaveLength(0);
  expect((await inFlightDraftSaved).status()).toBe(200);
  await page.unroute("**/editor-transform");
  await page.unroute(`**/decisions/${decisionId}/revisions`);
  await expect(page.locator(".document-title-row [role=status]")).toHaveText(
    "Draft saved",
  );
  const committedDuringInFlight = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    { headers: authorizedHeaders },
  );
  expect(committedDuringInFlight.status()).toBe(200);
  const committedDuringInFlightSource = (await committedDuringInFlight.json())
    .data.draft.record.editor_source as string;
  expect(committedDuringInFlightSource).toContain("in-flight-committed");
  expect(committedDuringInFlightSource).toContain("9007199254740993");
  expect(committedDuringInFlightSource).toContain("0.1234567890123456789");
  expect(committedDuringInFlightSource).toContain(
    "Question before IME composition",
  );
  expect(committedDuringInFlightSource).not.toContain("in-flight-intermediate");
  await captureScreenshot("decision-ime-inflight-committed.png");

  await enterPhase("Delayed draft acknowledgement preserves composing edits");
  const acknowledgedCompositionSource =
    '{"type":"object","properties":{"ack":{"const":"committed-after-ack"},"large":{"const":9007199254740993},"fraction":{"multipleOf":0.1234567890123456789}}}';
  const acknowledgedIntermediateSource =
    '{"type":"object","properties":{"ack":{"const":"intermediate-after-ack"}}}';
  let releaseDraftAcknowledgement!: () => void;
  let reportDraftCommit!: () => void;
  const draftAcknowledgementGate = new Promise<void>((resolve) => {
    releaseDraftAcknowledgement = resolve;
  });
  const draftCommitted = new Promise<void>((resolve) => {
    reportDraftCommit = resolve;
  });
  let heldDraftAcknowledgement = false;
  await page.route("**/draft", async (route) => {
    if (route.request().method() === "PUT" && !heldDraftAcknowledgement) {
      heldDraftAcknowledgement = true;
      const committed = await route.fetch();
      reportDraftCommit();
      await draftAcknowledgementGate;
      await route.fulfill({ response: committed });
      return;
    }
    await route.continue();
  });
  await page
    .getByLabel("Question")
    .fill("Question before delayed acknowledgement");
  await page.getByLabel("Question").press("Tab");
  await draftCommitted;
  const ackCompositionEditor = page.getByLabel("Advanced JSON Schema source");
  await ackCompositionEditor.focus();
  await ackCompositionEditor.dispatchEvent("compositionstart", { data: "" });
  await ackCompositionEditor.fill(acknowledgedIntermediateSource);
  releaseDraftAcknowledgement();
  const titleHashDuringAck = new URL(page.url()).hash;
  await page.getByRole("button", { name: projectName, exact: true }).click();
  const ackCompositionGuard = page.getByRole("dialog", {
    name: "Unsaved changes",
  });
  await expect(ackCompositionGuard).toBeVisible();
  expect(new URL(page.url()).hash).toBe(titleHashDuringAck);
  await ackCompositionGuard
    .getByRole("button", { name: "Keep editing", exact: true })
    .click();
  const committedAckDraft = page.waitForResponse(
    (response) =>
      response.url().endsWith("/draft") &&
      response.request().method() === "PUT",
  );
  await ackCompositionEditor.evaluate((editor, committedSource) => {
    const setter = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value",
    )?.set;
    setter?.call(editor, committedSource);
    editor.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        inputType: "insertCompositionText",
        data: "",
      }),
    );
    editor.dispatchEvent(
      new CompositionEvent("compositionend", { bubbles: true, data: "" }),
    );
  }, acknowledgedCompositionSource);
  expect((await committedAckDraft).status()).toBe(200);
  await expect(page.locator(".document-title-row [role=status]")).toHaveText(
    "Draft saved",
  );
  await page.unroute("**/draft");
  const postAcknowledgementResponse = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    { headers: authorizedHeaders },
  );
  const postAcknowledgementSource = (await postAcknowledgementResponse.json())
    .data.draft.record.editor_source as string;
  expect(postAcknowledgementSource).toContain("committed-after-ack");
  expect(postAcknowledgementSource).toContain("9007199254740993");
  expect(postAcknowledgementSource).toContain("0.1234567890123456789");
  expect(postAcknowledgementSource).toContain(
    "Question before delayed acknowledgement",
  );
  expect(postAcknowledgementSource).not.toContain("intermediate-after-ack");
  await captureScreenshot("decision-ime-delayed-ack.png");

  await enterPhase("Delayed save-and-leave flush locks the editor");
  const saveAndLeaveEditor = await openDecisionSourceEditor();
  const saveAndLeaveSource = postAcknowledgementSource.replace(
    '"Question before delayed acknowledgement"',
    '"Question saved before leave"',
  );
  expect(saveAndLeaveSource).not.toBe(postAcknowledgementSource);
  await saveAndLeaveEditor.fill(saveAndLeaveSource);
  const saveAndLeaveHash = new URL(page.url()).hash;
  await page.getByRole("button", { name: projectName, exact: true }).click();
  const saveAndLeaveGuard = page.getByRole("dialog", {
    name: "Unsaved changes",
  });
  await expect(saveAndLeaveGuard).toBeVisible();
  let releaseSaveAndLeave!: () => void;
  let reportSaveAndLeaveStarted!: () => void;
  const saveAndLeaveGate = new Promise<void>((resolve) => {
    releaseSaveAndLeave = resolve;
  });
  const saveAndLeaveStarted = new Promise<void>((resolve) => {
    reportSaveAndLeaveStarted = resolve;
  });
  let heldSaveAndLeave = false;
  await page.route("**/draft", async (route) => {
    if (route.request().method() === "PUT" && !heldSaveAndLeave) {
      heldSaveAndLeave = true;
      const committed = await route.fetch();
      reportSaveAndLeaveStarted();
      await saveAndLeaveGate;
      await route.fulfill({ response: committed });
      return;
    }
    await route.continue();
  });
  await saveAndLeaveGuard
    .getByRole("button", { name: "Save and leave", exact: true })
    .click();
  await saveAndLeaveStarted;
  await expect(saveAndLeaveEditor).toHaveJSProperty("readOnly", true);
  expect(new URL(page.url()).hash).toBe(saveAndLeaveHash);
  releaseSaveAndLeave();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible();
  await page.unroute("**/draft");
  await page
    .getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: decisionName, exact: true })
    .click();
  await expect(page.getByLabel("Question")).toHaveValue(
    "Question saved before leave",
  );
  const reopenedSaveAndLeaveEditor = await openDecisionSourceEditor();
  await expect(reopenedSaveAndLeaveEditor).toHaveValue(saveAndLeaveSource);
  await captureScreenshot("decision-save-and-leave-locked.png");

  const latestBeforeCliResponse = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    { headers: authorizedHeaders },
  );
  const latestBeforeCli = (await latestBeforeCliResponse.json()).data;
  const cliSource = latestBeforeCli.draft.record.editor_source.replace(
    '"Question saved before leave"',
    '"CLI winner"',
  );
  const browserSource = latestBeforeCli.draft.record.editor_source.replace(
    '"Question saved before leave"',
    '"Browser losing edit"',
  );
  expect(cliSource).not.toBe(latestBeforeCli.draft.record.editor_source);
  expect(browserSource).not.toBe(latestBeforeCli.draft.record.editor_source);
  const cliSourcePath = testInfo.outputPath("cli-winner-source.json");
  await writeFile(cliSourcePath, cliSource, "utf8");
  let releaseBrowserSave!: () => void;
  let reportBrowserSaveStarted!: () => void;
  const browserSaveStarted = new Promise<void>((resolve) => {
    reportBrowserSaveStarted = resolve;
  });
  const holdBrowserSave = new Promise<void>((resolve) => {
    releaseBrowserSave = resolve;
  });
  let heldFirstSave = false;
  await page.route("**/api/v1/projects/*/decisions/*/draft", async (route) => {
    if (route.request().method() === "PUT" && !heldFirstSave) {
      heldFirstSave = true;
      reportBrowserSaveStarted();
      await holdBrowserSave;
    }
    await route.continue();
  });
  const sourceEditor = await openDecisionSourceEditor();
  await sourceEditor.fill(browserSource);
  await browserSaveStarted;
  const cliResult = execFileSync(
    "deykit",
    [
      "--project",
      projectPath,
      "--json",
      "decision",
      "edit",
      decisionId,
      "--file",
      cliSourcePath,
      "--if-hash",
      latestBeforeCli.draft.etag,
      "--operation-id",
      "m10-browser-cli-etag-winner",
    ],
    { cwd: projectPath, encoding: "utf8" },
  );
  expect(cliResult).toContain("m10-browser-cli-etag-winner");
  releaseBrowserSave();
  await expect(
    page.getByRole("button", { name: "Review current and reapply my source" }),
  ).toBeVisible();
  await expect(sourceEditor).toHaveValue(browserSource);
  const raceWinner = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  expect((await raceWinner.json()).data.draft.record.editor_source).toBe(
    cliSource,
  );
  await page
    .getByRole("button", { name: "Review current and reapply my source" })
    .click();
  await expect(page.locator(".document-title-row [role=status]")).toHaveText(
    "Draft saved",
  );
  const reapplied = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  const reappliedDraft = (await reapplied.json()).data.draft;
  expect(reappliedDraft.record.editor_source).toBe(browserSource);

  decisionName = "Precise source decision renamed";
  await enterPhase("Decision mutation replay and immutable revision history");
  const renameBodies: Array<Record<string, unknown>> = [];
  await page.route(`**/decisions/${decisionId}/rename`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    renameBodies.push(
      route.request().postDataJSON() as Record<string, unknown>,
    );
    const response = await route.fetch();
    if (renameBodies.length === 1) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "{}",
      });
      return;
    }
    await route.fulfill({ response });
  });
  const renameResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/rename") &&
      response.request().method() === "POST",
  );
  await page.getByLabel("Decision name").fill(decisionName);
  await page.getByLabel("Decision name").press("Tab");
  expect((await renameResponse).status()).toBe(200);
  await expect(
    page.getByRole("button", { name: "Retry same rename" }),
  ).toBeVisible();
  const replayedRename = page.waitForResponse(
    (response) =>
      response.url().endsWith("/rename") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Retry same rename" }).click();
  const replayedRenameResponse = await replayedRename;
  expect(replayedRenameResponse.status()).toBe(200);
  expect((await replayedRenameResponse.json()).data.record.name).toBe(
    decisionName,
  );
  expect(renameBodies).toHaveLength(2);
  expect(renameBodies[1]).toEqual(renameBodies[0]);
  await expect(
    page.getByRole("button", { name: "Retry same rename" }),
  ).toHaveCount(0);
  await page.unroute(`**/decisions/${decisionId}/rename`);
  const renamed = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  if (!renamed.ok()) {
    const failure = await renamed.json().catch(() => undefined);
    const error = isRecord(failure) ? failure.error : undefined;
    const details = isRecord(error) ? error : undefined;
    apiFailures.push({
      route_pattern: safeRoutePattern(new URL(renamed.url()).pathname),
      status: renamed.status(),
      code: safeErrorIdentifier(details?.code),
      reason: safeErrorIdentifier(details?.reason),
    });
    await recordProgress();
  }
  expect(renamed.status()).toBe(200);
  expect((await renamed.json()).data.decision.record.name).toBe(decisionName);

  const revisionSaveBodies: Array<Record<string, unknown>> = [];
  await page.route(`**/decisions/${decisionId}/revisions`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    revisionSaveBodies.push(
      route.request().postDataJSON() as Record<string, unknown>,
    );
    const response = await route.fetch();
    if (revisionSaveBodies.length === 1) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "{}",
      });
      return;
    }
    await route.fulfill({ response });
  });
  await page
    .getByLabel("Version note (optional)")
    .fill("Source preservation baseline");
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Retry same version save" }),
  ).toBeVisible();
  const versionEditor = page.getByLabel("Advanced JSON Schema source");
  await versionEditor.focus();
  await versionEditor.dispatchEvent("compositionstart", { data: "" });
  await page.getByRole("button", { name: "Retry same version save" }).click();
  await expect(
    page.getByRole("button", { name: "Retry same version save" }),
  ).toBeVisible();
  expect(revisionSaveBodies).toHaveLength(1);
  await versionEditor.dispatchEvent("compositionend", { data: "" });
  const rawSourceEditor = page.getByLabel("Decision source");
  if (!(await rawSourceEditor.isVisible()))
    await page.locator(".advanced-source > summary").click();
  await expect(rawSourceEditor).toBeVisible();
  await page.clock.pauseAt(await page.evaluate(() => Date.now() + 1_000));
  const sourceBeforeHeldRefresh = await rawSourceEditor.inputValue();
  const sourceDuringHeldRefresh = `${sourceBeforeHeldRefresh} `;
  const projectionAfterVersionEdit = page.waitForResponse(
    (response) =>
      response.url().endsWith("/editor-projection") &&
      response.request().method() === "POST",
  );
  await rawSourceEditor.focus();
  await rawSourceEditor.dispatchEvent("compositionstart", { data: "" });
  await rawSourceEditor.fill(sourceDuringHeldRefresh);
  await rawSourceEditor.dispatchEvent("compositionend", { data: "" });
  await page.clock.runFor(1);
  const projectedVersionEdit = await projectionAfterVersionEdit;
  expect(projectedVersionEdit.status()).toBe(200);
  await expect(rawSourceEditor).toHaveValue(sourceDuringHeldRefresh);

  let releaseVersionContextRead!: () => void;
  let signalVersionContextRead!: () => void;
  const versionContextReadGate = new Promise<void>((resolve) => {
    releaseVersionContextRead = resolve;
  });
  const versionContextReadStarted = new Promise<void>((resolve) => {
    signalVersionContextRead = resolve;
  });
  let versionContextReadData: unknown;
  await page.route(`**/decisions/${decisionId}`, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const response = await route.fetch();
    versionContextReadData = await response.json();
    signalVersionContextRead();
    await versionContextReadGate;
    await route.fulfill({ response });
  });
  const heldRefreshDraftWrites: Request[] = [];
  const captureHeldRefreshDraftWrite = (request: Request) => {
    if (request.url().endsWith("/draft") && request.method() === "PUT")
      heldRefreshDraftWrites.push(request);
  };
  page.on("request", captureHeldRefreshDraftWrite);
  const versionReplayResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/decisions/${decisionId}/revisions`) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Retry same version save" }).click();
  await versionContextReadStarted;
  await page.clock.runFor(500);
  expect(heldRefreshDraftWrites).toHaveLength(0);
  await expect(rawSourceEditor).toHaveValue(sourceDuringHeldRefresh);
  const heldSourceDraftResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/draft") &&
      response.request().method() === "PUT",
  );
  releaseVersionContextRead();
  const replayedVersionResponse = await versionReplayResponse;
  expect(replayedVersionResponse.status()).toBe(200);
  const replayedVersionData = (await replayedVersionResponse.json()).data;
  const replayedVersionNotice = page.getByRole("status").filter({
    hasText: `Saved version ${replayedVersionData.revision.record.id}.`,
  });
  await expect(replayedVersionNotice).toHaveCount(1);
  await expect(replayedVersionNotice).toHaveText(
    `Saved version ${replayedVersionData.revision.record.id}.`,
  );
  expect(revisionSaveBodies).toHaveLength(2);
  expect(revisionSaveBodies[1]).toEqual(revisionSaveBodies[0]);
  await expect(
    page.getByRole("button", { name: "Save version", exact: true }),
  ).toBeEnabled();
  await page.clock.runFor(500);
  const heldSourceDraftReceipt = await heldSourceDraftResponse;
  expect(heldSourceDraftReceipt.status()).toBe(200);
  expect(heldRefreshDraftWrites).toHaveLength(1);
  const versionContextEnvelope = isRecord(versionContextReadData)
    ? versionContextReadData
    : {};
  const versionContextData = isRecord(versionContextEnvelope.data)
    ? versionContextEnvelope.data
    : {};
  const versionContextDraft = isRecord(versionContextData.draft)
    ? versionContextData.draft
    : {};
  expect(typeof versionContextDraft.etag).toBe("string");
  expect(heldSourceDraftReceipt.request().postDataJSON()).toMatchObject({
    editor_source: sourceDuringHeldRefresh,
    expected_etag: versionContextDraft.etag,
  });
  const heldSourceDraftData = (await heldSourceDraftReceipt.json()).data;
  expect(heldSourceDraftData.record.editor_source).toBe(
    sourceDuringHeldRefresh,
  );
  expect(typeof heldSourceDraftData.etag).toBe("string");
  const postVersionDraftEtag = heldSourceDraftData.etag as string;
  page.off("request", captureHeldRefreshDraftWrite);
  await page.unroute(`**/decisions/${decisionId}`);
  await page.clock.resume();
  await page.unroute(`**/decisions/${decisionId}/revisions`);

  await page
    .getByLabel("Version note (optional)")
    .fill("Fresh save after version baseline advance");
  const nextVersionResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/decisions/${decisionId}/revisions`) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  const nextVersionReceipt = await nextVersionResponse;
  expect(nextVersionReceipt.status()).toBe(200);
  expect(
    (nextVersionReceipt.request().postDataJSON() as Record<string, unknown>)
      .expected_draft_etag,
  ).toBe(postVersionDraftEtag);
  const nextVersionData = (await nextVersionReceipt.json()).data;
  const nextVersionRevisionId = nextVersionData.revision.record.id as string;
  await expect(
    page.getByRole("button", { name: "Save version", exact: true }),
  ).toBeEnabled();

  await enterPhase("Known version receipt survives failed context refresh");
  let failNextVersionContextRead = false;
  let recoveryVersionPosts = 0;
  const countRecoveryVersionPost = (request: Request) => {
    if (
      request.url().endsWith(`/decisions/${decisionId}/revisions`) &&
      request.method() === "POST"
    )
      recoveryVersionPosts += 1;
  };
  page.on("request", countRecoveryVersionPost);
  await page.route(`**/decisions/${decisionId}`, async (route) => {
    if (route.request().method() === "GET" && failNextVersionContextRead) {
      failNextVersionContextRead = false;
      await route.abort("failed");
      return;
    }
    await route.continue();
  });
  await page.route(`**/decisions/${decisionId}/revisions`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const response = await route.fetch();
    if (response.status() === 200) failNextVersionContextRead = true;
    await route.fulfill({ response });
  });
  await page
    .getByLabel("Version note (optional)")
    .fill("Version receipt with recoverable context read");
  const versionWithFailedRead = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/decisions/${decisionId}/revisions`) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  const knownVersionWithFailedRead = await versionWithFailedRead;
  expect(knownVersionWithFailedRead.status()).toBe(200);
  const recoveryVersionData = (await knownVersionWithFailedRead.json()).data;
  const recoveryVersionRevisionId = recoveryVersionData.revision.record
    .id as string;
  await expect(
    page.getByText(/Version saved; refresh its draft context/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Retry same version save" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Refreshing saved draft…", exact: true }),
  ).toBeDisabled();
  expect(recoveryVersionPosts).toBe(1);
  const recoveryReadResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/decisions/${decisionId}`) &&
      response.request().method() === "GET",
  );
  await page
    .getByRole("button", { name: "Refresh saved version context" })
    .click();
  const recoveredVersionContext = await recoveryReadResponse;
  expect(recoveredVersionContext.status()).toBe(200);
  await recoveredVersionContext.body();
  await expect(
    page.getByRole("button", { name: "Save version", exact: true }),
  ).toBeEnabled();
  expect(recoveryVersionPosts).toBe(1);
  page.off("request", countRecoveryVersionPost);
  await page.unroute(`**/decisions/${decisionId}`);
  await page.unroute(`**/decisions/${decisionId}/revisions`);

  await enterPhase("Incompatible version context preserves local source");
  let provideIncompatibleVersionContext = false;
  let incompatibleDraftWriteStatus: number | undefined;
  let incompatibleDraftWriteCount = 0;
  let incompatibleDraftWriteSource: string | undefined;
  let incompatibleDraftWriteEtag: string | undefined;
  await page.route(`**/decisions/${decisionId}`, async (route) => {
    if (
      route.request().method() !== "GET" ||
      !provideIncompatibleVersionContext
    )
      return route.continue();
    provideIncompatibleVersionContext = false;
    const beforeExternalWrite = await route.fetch();
    expect(beforeExternalWrite.status()).toBe(200);
    const currentData = (await beforeExternalWrite.json()).data;
    const currentDraftEtag = currentData.draft.etag as string;
    const externalEditorSource = `${currentData.draft.record.editor_source} `;
    incompatibleDraftWriteCount += 1;
    const externalDraftWrite = await page.request.put(
      `/api/v1/projects/${registrationId}/decisions/${decisionId}/draft`,
      {
        headers: authorizedHeaders,
        data: {
          schema_version: 1,
          operation_id: "m10-external-version-context-change",
          expected_etag: currentDraftEtag,
          editor_source: externalEditorSource,
        },
      },
    );
    incompatibleDraftWriteStatus = externalDraftWrite.status();
    if (externalDraftWrite.ok()) {
      const externalDraftData = (await externalDraftWrite.json()).data;
      incompatibleDraftWriteSource = externalDraftData.record
        .editor_source as string;
      incompatibleDraftWriteEtag = externalDraftData.etag as string;
    }
    const afterExternalWrite = await route.fetch();
    await route.fulfill({ response: afterExternalWrite });
  });
  await page.route(`**/decisions/${decisionId}/revisions`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const response = await route.fetch();
    if (response.status() === 200) provideIncompatibleVersionContext = true;
    await route.fulfill({ response });
  });
  const incompatibleVersionReceipt = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/decisions/${decisionId}/revisions`) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  const savedWithIncompatibleContext = await incompatibleVersionReceipt;
  expect(savedWithIncompatibleContext.status()).toBe(200);
  const incompatibleVersionData = (await savedWithIncompatibleContext.json())
    .data;
  const incompatibleVersionRevisionId = incompatibleVersionData.revision.record
    .id as string;
  await expect(
    page.getByText(/current draft or decision changed/),
  ).toBeVisible();
  await expect(rawSourceEditor).toHaveValue(sourceDuringHeldRefresh);
  await expect(
    page.getByRole("button", { name: "Refreshing saved draft…", exact: true }),
  ).toBeDisabled();
  expect(incompatibleDraftWriteCount).toBe(1);
  expect(incompatibleDraftWriteStatus).toBe(200);
  expect(incompatibleDraftWriteSource).toBe(`${sourceDuringHeldRefresh} `);
  expect(typeof incompatibleDraftWriteEtag).toBe("string");
  const deliberateReviewRead = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/decisions/${decisionId}`) &&
      response.request().method() === "GET",
  );
  const deliberatelyReappliedDraft = page.waitForResponse(
    (response) =>
      response.url().endsWith("/draft") &&
      response.request().method() === "PUT",
  );
  await page
    .getByRole("button", { name: "Review current and reapply my source" })
    .click();
  const reviewedCurrentContext = await deliberateReviewRead;
  expect(reviewedCurrentContext.status()).toBe(200);
  const reviewedCurrentData = (await reviewedCurrentContext.json()).data;
  const deliberateDraftReceipt = await deliberatelyReappliedDraft;
  expect(deliberateDraftReceipt.status()).toBe(200);
  expect(deliberateDraftReceipt.request().postDataJSON()).toMatchObject({
    editor_source: sourceDuringHeldRefresh,
    expected_etag: reviewedCurrentData.draft.etag,
  });
  expect((await deliberateDraftReceipt.json()).data.record.editor_source).toBe(
    sourceDuringHeldRefresh,
  );
  await expect(
    page.getByRole("button", { name: "Save version", exact: true }),
  ).toBeEnabled();
  await page.unroute(`**/decisions/${decisionId}`);
  await page.unroute(`**/decisions/${decisionId}/revisions`);

  const rejectedVersionBodies: Array<Record<string, unknown>> = [];
  await page.route(`**/decisions/${decisionId}/revisions`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    rejectedVersionBodies.push(
      route.request().postDataJSON() as Record<string, unknown>,
    );
    await route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({
        schema_version: 1,
        error: {
          schema_version: 1,
          code: "conflict",
          reason: "draft_changed",
          message: "Version changed",
        },
      }),
    });
  });
  const rejectedVersionResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/decisions/${decisionId}/revisions`) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  const knownRejectedVersion = await rejectedVersionResponse;
  expect(knownRejectedVersion.status()).toBe(409);
  expect(await knownRejectedVersion.json()).toMatchObject({
    error: { code: "conflict", reason: "draft_changed" },
  });
  await expect(
    page.getByRole("alert").filter({ hasText: "Version changed" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save version", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Retry same version save" }),
  ).toHaveCount(0);
  expect(rejectedVersionBodies).toHaveLength(1);
  await page.unroute(`**/decisions/${decisionId}/revisions`);

  const firstRevisionPage = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}/revisions?limit=50`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  expect(firstRevisionPage.status()).toBe(200);
  const firstRevisionId = replayedVersionData.revision.record.id as string;
  const firstRevisionItems = (await firstRevisionPage.json()).data.items;
  expect(
    firstRevisionItems.some(
      (item: { revision: { record: { id: string } } }) =>
        item.revision.record.id === firstRevisionId,
    ),
  ).toBe(true);
  const firstRevision = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}/revisions/${firstRevisionId}`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  expect(firstRevision.status()).toBe(200);
  const firstRevisionData = (await firstRevision.json()).data;
  expect(firstRevisionData.revision.record.id).toBe(firstRevisionId);
  const firstRevisionEditorSource = firstRevisionData.editor_source as string;
  expect(firstRevisionEditorSource).toBe(replayedVersionData.editor_source);
  expect(
    firstRevisionData.revision.record.definition.questions[0].instructions,
  ).toBe("Browser losing edit");
  expect(firstRevisionData.revision.record.definition.input_schema_source).toBe(
    acknowledgedCompositionSource,
  );
  expect(firstRevisionEditorSource).toContain("committed-after-ack");
  expect(firstRevisionEditorSource).toContain("9007199254740993");
  expect(firstRevisionEditorSource).toContain("0.1234567890123456789");

  await page.getByRole("button", { name: "+ Add option" }).click();
  const optionNames = page.getByLabel("Option name");
  await expect(optionNames).toHaveCount(3);
  await optionNames.nth(2).fill("Option C");
  const addTransform = page.waitForResponse(
    (response) =>
      response.url().endsWith("/editor-transform") &&
      response.request().method() === "POST",
  );
  const addDraftSave = page.waitForResponse(
    (response) =>
      response.url().endsWith("/draft") &&
      response.request().method() === "PUT",
  );
  await optionNames.nth(2).press("Tab");
  await addTransform;
  await addDraftSave;
  const renameTransform = page.waitForResponse(
    (response) =>
      response.url().endsWith("/editor-transform") &&
      response.request().method() === "POST",
  );
  const renameDraftSave = page.waitForResponse(
    (response) =>
      response.url().endsWith("/draft") &&
      response.request().method() === "PUT",
  );
  await page.getByLabel("Option name").nth(1).fill("Renamed Option B");
  await page.getByLabel("Option name").nth(1).press("Tab");
  await renameTransform;
  await renameDraftSave;
  const reorderTransform = page.waitForResponse(
    (response) =>
      response.url().endsWith("/editor-transform") &&
      response.request().method() === "POST",
  );
  const reorderDraftSave = page.waitForResponse(
    (response) =>
      response.url().endsWith("/draft") &&
      response.request().method() === "PUT",
  );
  await page.getByRole("button", { name: "Move Option C up" }).click();
  const [reorderTransformResponse, reorderDraftSaveResponse] =
    await Promise.all([reorderTransform, reorderDraftSave]);
  expect(reorderTransformResponse.status()).toBe(200);
  expect(reorderDraftSaveResponse.status()).toBe(200);
  await Promise.all([
    reorderTransformResponse.json(),
    reorderDraftSaveResponse.json(),
  ]);
  await expect(
    page.getByRole("status").filter({ hasText: "Draft saved" }),
  ).toHaveText("Draft saved");
  const transformedDecisionPath = `/api/v1/projects/${registrationId}/decisions/${decisionId}`;
  const transformedDecision = await page.request.get(transformedDecisionPath, {
    headers: { Origin: origin, "X-Deykit-Capability": capability as string },
  });
  await recordDirectApiFailure(transformedDecision, transformedDecisionPath);
  expect(transformedDecision.status()).toBe(200);
  const transformedSource = (await transformedDecision.json()).data.draft.record
    .editor_source as string;
  expect(transformedSource).toContain("9007199254740993");
  expect(transformedSource).toContain("0.1234567890123456789");
  await expect(optionNames).toHaveCount(3);
  await expect(optionNames.nth(0)).toHaveValue("Option A");
  await expect(optionNames.nth(1)).toHaveValue("Option C");
  await expect(optionNames.nth(2)).toHaveValue("Renamed Option B");
  const immediateVersionOptionName = "Saved before transform debounce";
  await page.getByLabel("Option name").nth(1).fill(immediateVersionOptionName);
  const immediateSaveResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/decisions/${decisionId}/revisions`) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  const immediateVersionReceipt = await immediateSaveResponse;
  expect(immediateVersionReceipt.status()).toBe(200);
  const immediateVersionData = (await immediateVersionReceipt.json()).data;
  const immediateVersionId = immediateVersionData.revision.record.id as string;
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: `Saved version ${immediateVersionId}.` }),
  ).toHaveText(`Saved version ${immediateVersionId}.`);
  await expect(
    page.getByRole("button", { name: "Save version", exact: true }),
  ).toBeEnabled();
  const immediateRevisionPage = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}/revisions?limit=50`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  if (!immediateRevisionPage.ok()) {
    const failure = await immediateRevisionPage.json().catch(() => undefined);
    const error = isRecord(failure) ? failure.error : undefined;
    const details = isRecord(error) ? error : undefined;
    apiFailures.push({
      route_pattern: safeRoutePattern(
        new URL(immediateRevisionPage.url()).pathname,
      ),
      status: immediateRevisionPage.status(),
      code: safeErrorIdentifier(details?.code),
      reason: safeErrorIdentifier(details?.reason),
    });
    await recordProgress();
  }
  expect(immediateRevisionPage.status()).toBe(200);
  const immediateRevisionItems = (await immediateRevisionPage.json()).data
    .items;
  expect(
    immediateRevisionItems.some(
      (item: { revision: { record: { id: string } } }) =>
        item.revision.record.id === immediateVersionId,
    ),
  ).toBe(true);
  const immediateRevision = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}/revisions/${immediateVersionId}`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  expect(immediateRevision.status()).toBe(200);
  const immediateRevisionData = (await immediateRevision.json()).data;
  expect(immediateRevisionData.revision.record.id).toBe(immediateVersionId);
  const immediateRevisionSource = immediateRevisionData.editor_source as string;
  expect(immediateRevisionSource).toBe(immediateVersionData.editor_source);
  expect(
    immediateRevisionData.revision.record.definition.questions[0].instructions,
  ).toBe("Browser losing edit");
  expect(
    immediateRevisionData.revision.record.definition.input_schema_source,
  ).toBe(acknowledgedCompositionSource);
  expect(immediateRevisionSource).toContain(immediateVersionOptionName);
  expect(immediateRevisionSource).toContain("9007199254740993");
  expect(immediateRevisionSource).toContain("0.1234567890123456789");
  const draftAfterImmediateSave = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  expect(draftAfterImmediateSave.status()).toBe(200);
  const immediateSavedDecision = (await draftAfterImmediateSave.json()).data;
  expect(immediateRevisionSource).toBe(
    immediateSavedDecision.draft.record.editor_source,
  );
  expect(immediateSavedDecision.draft.record.base_revision_id).toBe(
    immediateVersionId,
  );
  expect(immediateSavedDecision.decision.record.latest_revision_id).toBe(
    immediateVersionId,
  );
  await page
    .getByLabel("Version note (optional)")
    .fill("Stable option identity and order");
  await expect(
    page.getByRole("button", { name: "Save version", exact: true }),
  ).toBeEnabled();
  const stableVersionResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/decisions/${decisionId}/revisions`) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Save version", exact: true }).click();
  const stableVersionReceipt = await stableVersionResponse;
  expect(stableVersionReceipt.status()).toBe(200);
  const stableVersionData = (await stableVersionReceipt.json()).data;
  const stableVersionId = stableVersionData.revision.record.id as string;
  const initialOptionIds =
    firstRevisionData.revision.record.definition.questions[0].options.map(
      (option: { id: string }) => option.id,
    );
  const latestSavedOptions =
    stableVersionData.revision.record.definition.questions[0].options;
  const latestSavedOptionIds = latestSavedOptions.map(
    (option: { id: string }) => option.id,
  );
  const addedOptionIds = latestSavedOptionIds.filter(
    (optionId: string) => !initialOptionIds.includes(optionId),
  );
  expect(addedOptionIds).toHaveLength(1);
  expect(latestSavedOptionIds).toEqual([
    initialOptionIds[0],
    addedOptionIds[0],
    initialOptionIds[1],
  ]);
  expect(
    latestSavedOptions.map((option: { name: string }) => option.name),
  ).toEqual(["Option A", immediateVersionOptionName, "Renamed Option B"]);
  await expect(
    page.getByRole("button", { name: "Save version", exact: true }),
  ).toBeEnabled();

  const expectedRevisionIds = [
    firstRevisionId,
    nextVersionRevisionId,
    recoveryVersionRevisionId,
    incompatibleVersionRevisionId,
    immediateVersionId,
    stableVersionId,
  ];
  expect(new Set(expectedRevisionIds).size).toBe(expectedRevisionIds.length);
  await page
    .getByRole("button", { name: "Version history", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Version history" }),
  ).toBeVisible();
  const revisionRows = page
    .getByRole("table", { name: "Saved decision versions" })
    .getByRole("row");
  await expect(revisionRows).toHaveCount(expectedRevisionIds.length + 1);
  for (const revisionId of expectedRevisionIds)
    await expect(revisionRows.filter({ hasText: revisionId })).toHaveCount(1);
  const baselineRow = revisionRows.filter({ hasText: firstRevisionId });
  await expect(baselineRow).toHaveCount(1);
  await baselineRow.getByRole("button", { name: "Compare to latest" }).click();
  await expect(page.getByLabel("Difference from latest version")).toContainText(
    "Option order changed: No",
  );
  await expect(page.getByLabel("Difference from latest version")).toContainText(
    `Added option IDs: ${addedOptionIds[0]}`,
  );
  await baselineRow.getByRole("button", { name: "Inspect" }).click();
  await page.getByText("Exact saved editor source", { exact: true }).click();
  const savedEditor = page.getByLabel("Saved editor source");
  await expect(savedEditor).toHaveValue(firstRevisionEditorSource);
  await baselineRow.getByRole("button", { name: "Restore to draft…" }).click();
  const restoreDialog = page.getByRole("dialog", {
    name: "Restore this version to the draft?",
  });
  await expect(restoreDialog).toBeVisible();
  await expect(
    restoreDialog.getByLabel("Editor source to restore"),
  ).toHaveValue(firstRevisionEditorSource);
  const uncertainRestoreRequests: Array<Record<string, unknown>> = [];
  let firstRestoreStatus: number | undefined;
  let releaseRestoreReply!: () => void;
  let reportRestoreReplyStarted!: () => void;
  const restoreReplyGate = new Promise<void>((resolve) => {
    releaseRestoreReply = resolve;
  });
  const restoreReplyStarted = new Promise<void>((resolve) => {
    reportRestoreReplyStarted = resolve;
  });
  await page.route(
    `**/decisions/${decisionId}/restore-revision`,
    async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      uncertainRestoreRequests.push(
        route.request().postDataJSON() as Record<string, unknown>,
      );
      const response = await route.fetch();
      if (uncertainRestoreRequests.length === 1) {
        firstRestoreStatus = response.status();
        reportRestoreReplyStarted();
        await restoreReplyGate;
        await route.abort("failed");
        return;
      }
      await route.fulfill({ response });
    },
  );
  await restoreDialog
    .getByRole("button", { name: "Restore to draft", exact: true })
    .click();
  await restoreReplyStarted;
  expect(uncertainRestoreRequests).toHaveLength(1);
  const restoreHashBeforeBack = page.url();
  await page.goBack();
  await expect(restoreDialog).toBeVisible();
  expect(page.url()).toBe(restoreHashBeforeBack);
  expect(uncertainRestoreRequests).toHaveLength(1);
  await expect(
    restoreDialog.getByLabel("Editor source to restore"),
  ).toHaveValue(firstRevisionEditorSource);
  releaseRestoreReply();
  await expect(
    page.getByRole("button", { name: "Retry the same restore request" }),
  ).toBeVisible();
  await expect(
    restoreDialog.getByLabel("Editor source to restore"),
  ).toHaveValue(firstRevisionEditorSource);
  const restoreReplayResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/restore-revision") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Retry the same restore request" })
    .click();
  const restoredResponse = await restoreReplayResponse;
  expect(restoredResponse.status()).toBe(200);
  await restoredResponse.body();
  await expect(
    page.getByRole("button", { name: "Retry the same restore request" }),
  ).toHaveCount(0);
  await expect(restoreDialog).toHaveCount(0);
  await expect(page.getByLabel("Decision name")).toHaveValue(decisionName);
  expect(firstRestoreStatus).toBe(200);
  expect(uncertainRestoreRequests).toHaveLength(2);
  expect(uncertainRestoreRequests[1]).toEqual(uncertainRestoreRequests[0]);
  await page.unroute(`**/decisions/${decisionId}/restore-revision`);

  await page
    .getByRole("button", { name: "Version history", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Version history" }),
  ).toBeVisible();
  const refreshedRevisionRows = page
    .getByRole("table", { name: "Saved decision versions" })
    .getByRole("row");
  const firstRevisionRow = refreshedRevisionRows.filter({
    hasText: firstRevisionId,
  });
  await expect(firstRevisionRow).toHaveCount(1);
  await firstRevisionRow
    .getByRole("button", { name: "Restore to draft…" })
    .click();
  const conflictRestoreDialog = page.getByRole("dialog", {
    name: "Restore this version to the draft?",
  });
  await expect(
    conflictRestoreDialog.getByLabel("Editor source to restore"),
  ).toHaveValue(firstRevisionEditorSource);
  const beforeRestoreRace = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  const currentDraft = (await beforeRestoreRace.json()).data.draft;
  expect(currentDraft.record.editor_source).toBe(firstRevisionEditorSource);
  const restoreRaceWinnerSource = `${currentDraft.record.editor_source}\n`;
  let releaseRestore!: () => void;
  let reportRestoreStarted!: () => void;
  const restoreStarted = new Promise<void>((resolve) => {
    reportRestoreStarted = resolve;
  });
  const holdRestore = new Promise<void>((resolve) => {
    releaseRestore = resolve;
  });
  let restoreHeld = false;
  let restoreConflictStatus: number | undefined;
  let restoreConflictRequests = 0;
  await page.route(
    `**/decisions/${decisionId}/restore-revision`,
    async (route) => {
      if (route.request().method() === "POST") restoreConflictRequests += 1;
      if (route.request().method() === "POST" && !restoreHeld) {
        restoreHeld = true;
        reportRestoreStarted();
        await holdRestore;
      }
      const response = await route.fetch();
      restoreConflictStatus = response.status();
      await route.fulfill({ response });
    },
  );
  await conflictRestoreDialog
    .getByRole("button", { name: "Restore to draft", exact: true })
    .click();
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
  await expect(
    conflictRestoreDialog
      .getByLabel("Current draft after conflict")
      .getByRole("status"),
  ).toHaveText(
    "The saved version was not restored. The current draft remains unchanged.",
  );
  await expect(
    conflictRestoreDialog.getByLabel("Editor source to restore"),
  ).toHaveValue(firstRevisionEditorSource);
  const blockedRestore = conflictRestoreDialog.getByRole("button", {
    name: "Restore over reviewed draft",
    exact: true,
  });
  await expect(blockedRestore).toBeDisabled();
  await conflictRestoreDialog
    .getByRole("button", { name: "Review current draft", exact: true })
    .click();
  await expect(
    conflictRestoreDialog.getByLabel("Reviewed current draft source"),
  ).toHaveValue(restoreRaceWinnerSource);
  await expect(blockedRestore).toBeEnabled();
  await expect(
    conflictRestoreDialog.getByLabel("Editor source to restore"),
  ).toHaveValue(firstRevisionEditorSource);
  await conflictRestoreDialog
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await page
    .getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: decisionName, exact: true })
    .click();
  expect(restoreConflictRequests).toBe(1);
  await expect(page.getByLabel("Decision name")).toHaveValue(decisionName);
  const restoredSourceEditor = await openDecisionSourceEditor();
  await expect(restoredSourceEditor).toHaveValue(restoreRaceWinnerSource);
  const restoreConflictWinner = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  expect(restoreConflictWinner.status()).toBe(200);
  expect(
    (await restoreConflictWinner.json()).data.draft.record.editor_source,
  ).toBe(restoreRaceWinnerSource);

  const inputFormatTransform = page.waitForResponse(
    (response) =>
      response.url().endsWith("/editor-transform") &&
      response.request().method() === "POST",
  );
  await page.getByRole("radio", { name: "JSON", exact: true }).check();
  const inputFormatReceipt = await inputFormatTransform;
  expect(inputFormatReceipt.status()).toBe(200);
  await inputFormatReceipt.body();
  await expect(page.locator(".document-title-row [role=status]")).toHaveText(
    "Draft saved",
  );
  const jsonInputDecision = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}`,
    { headers: authorizedHeaders },
  );
  expect(jsonInputDecision.status()).toBe(200);
  const jsonInputDecisionData = (await jsonInputDecision.json()).data;
  expect(jsonInputDecisionData.draft.record.editor_source).toContain(
    '"input_kind":"json"',
  );
  expect(jsonInputDecisionData.draft.record.editor_source).toContain(
    JSON.stringify(acknowledgedCompositionSource),
  );

  await enterPhase("Label staging, review, provenance and write races");
  await page
    .getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: "Examples", exact: true })
    .click();
  await caseButton("seed-1").click();
  await expect(
    page.getByRole("heading", { name: "Expected answers" }),
  ).toBeVisible();
  await captureScreenshot("examples-label-review.png");

  await enterPhase("Import row validation and explicit accepted-row commit");
  await page
    .getByRole("button", { name: "Import examples", exact: true })
    .click();
  await page.getByLabel("Map expected answers for").selectOption(decisionId);
  await page
    .getByLabel("Advanced mapping source")
    .fill(
      '{"schema_version":1,"input_kind":"json","input_column":"input","input_parse_json":true,"id_column":"id","expected_column":"expected","group_column":"group"}',
    );
  const rows = Array.from({ length: 10 }, (_item, index) => {
    const rowNumber = index + 1;
    const input = rowNumber === 3 ? "not-json" : `{"case":${rowNumber}}`;
    const expected = rowNumber === 7 ? "missing-option" : "option-a";
    const group = [1, 2, 8, 9].includes(rowNumber)
      ? "related-group"
      : `group-${rowNumber}`;
    return `case-${rowNumber},"${input.replaceAll('"', '""')}",${expected},${group}`;
  });
  const sourceText = `id,input,expected,group\n${rows.join("\n")}\n`;
  await page.getByLabel("Import source text").fill(sourceText);
  await page.getByRole("button", { name: "Preview all rows" }).click();
  const importRow3 = page
    .getByRole("row")
    .filter({ has: page.getByRole("rowheader", { name: "3", exact: true }) });
  const importRow7 = page
    .getByRole("row")
    .filter({ has: page.getByRole("rowheader", { name: "7", exact: true }) });
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "10 rows · 8 valid · 2 rejected · 8 would import" }),
  ).toBeVisible();
  await expect(importRow3).toContainText("Line 4: Input is not valid JSON.");
  await expect(importRow7).toContainText(
    "Line 8: Expected answers include an option that does not exist.",
  );
  await expect(
    page.getByRole("button", { name: "Import valid rows" }),
  ).toBeDisabled();
  await captureScreenshot("import-row-errors.png");
  await page
    .getByLabel("Import source text")
    .fill(`${sourceText}# changed proposal\n`);
  await expect(
    page.getByRole("heading", { name: "Import review" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Import valid rows" }),
  ).toHaveCount(0);
  await page.getByLabel("Import source text").fill(sourceText);
  await page.getByRole("button", { name: "Preview all rows" }).click();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "10 rows · 8 valid · 2 rejected · 8 would import" }),
  ).toBeVisible();
  await expect(importRow3).toContainText("Line 4: Input is not valid JSON.");
  await expect(importRow7).toContainText(
    "Line 8: Expected answers include an option that does not exist.",
  );
  await page
    .getByRole("checkbox", {
      name: "Import valid rows only (8) and keep the exclusion report",
    })
    .check();
  await captureScreenshot("import-valid-rows-reviewed.png");
  const importCommitsBeforeReplayScenario = importCommitBodies.length;
  let firstImportCommitStatus: number | undefined;
  await page.route("**/imports/commit", async (route) => {
    const response = await route.fetch();
    if (importCommitBodies.length === importCommitsBeforeReplayScenario + 1) {
      firstImportCommitStatus = response.status();
      await route.abort("failed");
      return;
    }
    await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "Import valid rows" }).click();
  await expect(
    page.getByRole("button", { name: "Retry the same import request" }),
  ).toBeVisible();
  expect(firstImportCommitStatus).toBe(200);
  await expect(
    page.getByRole("button", { name: "Close", exact: true }),
  ).toBeDisabled();
  const importHashBeforeRouteAttempt = page.url();
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, `#/p/${registrationId}/d/${decisionId}`);
  const importUnknownGuard = page.getByRole("dialog", {
    name: "Unsaved changes",
  });
  await expect(importUnknownGuard).toBeVisible();
  await expect(
    importUnknownGuard.getByRole("button", {
      name: "Discard changes",
      exact: true,
    }),
  ).toBeDisabled();
  await importUnknownGuard
    .getByRole("button", { name: "Keep editing", exact: true })
    .click();
  await expect(page).toHaveURL(importHashBeforeRouteAttempt);
  expect(importCommitBodies).toHaveLength(
    importCommitsBeforeReplayScenario + 1,
  );
  const importReplayResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/imports/commit") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Retry the same import request" })
    .click();
  const importedResponse = await importReplayResponse;
  expect(importedResponse.status()).toBe(200);
  await importedResponse.body();
  await expect(
    page.getByRole("button", { name: "Retry the same import request" }),
  ).toHaveCount(0);
  await expect(caseButton("case-1")).toBeVisible({ timeout: 10_000 });
  await expect(caseButton("case-10")).toBeVisible({ timeout: 10_000 });
  await expect(
    page.getByText("Loading selected example…", { exact: true }),
  ).toHaveCount(0);
  expect(importCommitBodies).toHaveLength(
    importCommitsBeforeReplayScenario + 2,
  );
  const originalImportCommitBody =
    importCommitBodies[importCommitsBeforeReplayScenario];
  if (!originalImportCommitBody)
    throw new Error("Original import commit request was not captured");
  expect(importCommitBodies[importCommitsBeforeReplayScenario + 1]).toEqual(
    originalImportCommitBody,
  );
  await page.unroute("**/imports/commit");
  await expect(page.getByLabel("Dataset")).toHaveValue(datasetId);
  const commitReplay = await page.request.post(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/imports/commit`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
      data: originalImportCommitBody,
    },
  );
  const commitReplayBody: unknown = await commitReplay
    .json()
    .catch(() => undefined);
  if (commitReplay.status() >= 400) {
    const error = isRecord(commitReplayBody)
      ? commitReplayBody.error
      : undefined;
    const details = isRecord(error) ? error : undefined;
    apiFailures.push({
      route_pattern: safeRoutePattern(
        `/api/v1/projects/${registrationId}/datasets/${datasetId}/imports/commit`,
      ),
      status: commitReplay.status(),
      code: safeErrorIdentifier(details?.code),
      reason: safeErrorIdentifier(details?.reason),
    });
    await recordProgress();
  }
  expect(commitReplay.status()).toBe(200);
  expect(
    isRecord(commitReplayBody) &&
      isRecord(commitReplayBody.data) &&
      commitReplayBody.data.replayed,
  ).toBe(true);
  const importedCases = await page.request.get(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases?limit=50`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  expect((await importedCases.json()).data.total).toBe("9");

  await caseButton("seed-1").click();
  await page.getByRole("button", { name: "Edit input" }).click();
  await page.getByRole("radio", { name: "JSON", exact: true }).check();
  const stagedCaseSource = '{"case":"seed-1","kept":true}';
  await page.getByLabel("Input source", { exact: true }).fill(stagedCaseSource);
  let caseRefreshFailures = 2;
  const committedCaseBodies: Array<Record<string, unknown>> = [];
  await page.route("**/cases/seed-1", async (route) => {
    if (route.request().method() === "PUT") {
      committedCaseBodies.push(
        route.request().postDataJSON() as Record<string, unknown>,
      );
      return route.continue();
    }
    if (route.request().method() === "GET" && caseRefreshFailures > 0) {
      caseRefreshFailures -= 1;
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          schema_version: 1,
          error: {
            schema_version: 1,
            code: "internal_error",
            message: "The local service could not complete the request.",
            reason: "injected_read_failure",
          },
        }),
      });
      return;
    }
    await route.continue();
  });
  const stagedCaseHash = page.url();
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, `#/p/${registrationId}/d/${decisionId}`);
  const keepStagedCase = page.getByRole("dialog", { name: "Unsaved changes" });
  await expect(keepStagedCase).toBeVisible();
  await keepStagedCase
    .getByRole("button", { name: "Keep editing", exact: true })
    .click();
  await expect(page).toHaveURL(stagedCaseHash);
  await expect(page.getByLabel("Input source", { exact: true })).toHaveValue(
    stagedCaseSource,
  );
  const committedCaseResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/cases/seed-1") &&
      response.request().method() === "PUT",
  );
  const failedCaseRefresh = page.waitForResponse(
    (response) =>
      response.url().endsWith("/cases/seed-1") &&
      response.request().method() === "GET" &&
      response.status() === 503,
  );
  await page.getByRole("button", { name: "Save input" }).click();
  const committedCaseReceipt = await committedCaseResponse;
  expect(committedCaseReceipt.status()).toBe(200);
  await committedCaseReceipt.body();
  await (await failedCaseRefresh).body();
  await expect(
    page
      .getByRole("dialog", { name: "Edit seed-1" })
      .getByRole("region", { name: "Saved changes awaiting refresh" }),
  ).toContainText("Case saved; refresh its current review");
  await captureScreenshot("case-saved-refresh-pending.png");
  await expect(page.getByLabel("Input source", { exact: true })).toHaveValue(
    stagedCaseSource,
  );
  await expect(page.getByRole("button", { name: "Save input" })).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Retry same case edit" }),
  ).toHaveCount(0);
  expect(committedCaseBodies).toHaveLength(1);
  const committedCaseHash = page.url();
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, `#/p/${registrationId}/d/${decisionId}`);
  const committedCaseGuard = page.getByRole("dialog", {
    name: "Unsaved changes",
  });
  await expect(committedCaseGuard).toBeVisible();
  await expect(committedCaseGuard).toContainText(
    "The case was saved. Refresh its current review before leaving this examples page.",
  );
  await expect(
    committedCaseGuard.getByRole("button", {
      name: "Save and leave",
      exact: true,
    }),
  ).toBeDisabled();
  await expect(
    committedCaseGuard.getByRole("button", {
      name: "Discard changes",
      exact: true,
    }),
  ).toBeEnabled();
  await committedCaseGuard
    .getByRole("button", { name: "Keep editing", exact: true })
    .click();
  await expect(page).toHaveURL(committedCaseHash);
  expect(committedCaseBodies).toHaveLength(1);
  const failedCaseRecovery = page.waitForResponse(
    (response) =>
      response.url().endsWith("/cases/seed-1") &&
      response.request().method() === "GET" &&
      response.status() === 503,
  );
  await page.getByRole("button", { name: "Refresh saved case" }).click();
  await (await failedCaseRecovery).body();
  await expect(
    page.getByText("The local service could not complete the request."),
  ).toBeVisible();
  await expect(page.getByLabel("Input source", { exact: true })).toHaveValue(
    stagedCaseSource,
  );
  expect(committedCaseBodies).toHaveLength(1);
  const recoveredCaseRead = page.waitForResponse(
    (response) =>
      response.url().endsWith("/cases/seed-1") &&
      response.request().method() === "GET" &&
      response.status() === 200,
  );
  await page.getByRole("button", { name: "Refresh saved case" }).click();
  await (await recoveredCaseRead).body();
  const changedLabelReview = page.getByRole("region", {
    name: "Review selected context",
  });
  await expect(changedLabelReview).toContainText(
    "The current example or label context changed. Review it before making another change.",
  );
  await expect(
    page.getByText(
      "Case saved. The current label review changed; review it before making another label change.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit input" })).toBeDisabled();
  await page.getByRole("button", { name: "Review current selection" }).click();
  await expect(changedLabelReview).toHaveCount(0);
  await expect(
    page.getByText(
      "Current example and label review acknowledged. Your staged changes remain available to reapply deliberately.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit input" })).toBeEnabled({
    timeout: 10_000,
  });
  await expect(
    page.getByText("Loading selected example…", { exact: true }),
  ).toHaveCount(0, { timeout: 10_000 });
  expect(committedCaseBodies).toHaveLength(1);
  expect(committedCaseBodies[0]?.input_source).toBe(stagedCaseSource);
  await expect(
    page.getByLabel("Complete example input source", { exact: true }),
  ).toHaveText(stagedCaseSource);
  const committedCaseRead = await page.request.get(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/seed-1`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  await recordDirectApiFailure(
    committedCaseRead,
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/seed-1`,
  );
  expect(committedCaseRead.status()).toBe(200);
  expect((await committedCaseRead.json()).data.case.record.input_source).toBe(
    stagedCaseSource,
  );
  await page.unroute("**/cases/seed-1");
  await caseButton("case-1").click();
  await expect(
    page.getByRole("heading", { name: "case-1", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit input" })).toBeEnabled({
    timeout: 10_000,
  });
  await expect(
    page.getByText("Loading selected example…", { exact: true }),
  ).toHaveCount(0, { timeout: 10_000 });
  const caseOneBefore = await page.request.get(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/case-1`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  await recordDirectApiFailure(
    caseOneBefore,
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/case-1`,
  );
  expect(caseOneBefore.status()).toBe(200);
  const caseOneOriginalSource = (await caseOneBefore.json()).data.case.record
    .input_source as string;
  const caseTwoBefore = await page.request.get(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/case-2`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  await recordDirectApiFailure(
    caseTwoBefore,
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/case-2`,
  );
  expect(caseTwoBefore.status()).toBe(200);
  const caseTwoOriginalSource = (await caseTwoBefore.json()).data.case.record
    .input_source as string;
  await page.getByRole("button", { name: "Edit input" }).click();
  const staleCaseSource = '{"case":"case-1","stale":true}';
  await page.getByLabel("Input source", { exact: true }).fill(staleCaseSource);
  let releaseStaleCaseRead!: () => void;
  let reportStaleCaseReadStarted!: () => void;
  const staleCaseReadGate = new Promise<void>((resolve) => {
    releaseStaleCaseRead = resolve;
  });
  const staleCaseReadStarted = new Promise<void>((resolve) => {
    reportStaleCaseReadStarted = resolve;
  });
  const staleCaseBodies: Array<Record<string, unknown>> = [];
  let releaseCaseTwoRead!: () => void;
  let reportCaseTwoReadStarted!: () => void;
  const caseTwoReadGate = new Promise<void>((resolve) => {
    releaseCaseTwoRead = resolve;
  });
  const caseTwoReadStarted = new Promise<void>((resolve) => {
    reportCaseTwoReadStarted = resolve;
  });
  await page.route("**/cases/case-1", async (route) => {
    if (route.request().method() === "PUT") {
      staleCaseBodies.push(
        route.request().postDataJSON() as Record<string, unknown>,
      );
      return route.continue();
    }
    if (route.request().method() === "GET") {
      reportStaleCaseReadStarted();
      await staleCaseReadGate;
    }
    await route.continue();
  });
  await page.route("**/cases/case-2", async (route) => {
    if (route.request().method() === "GET") {
      reportCaseTwoReadStarted();
      await caseTwoReadGate;
    }
    await route.continue();
  });
  const staleCaseReadResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/cases/case-1") &&
      response.request().method() === "GET" &&
      response.status() === 200,
  );
  const caseTwoReadResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/cases/case-2") &&
      response.request().method() === "GET" &&
      response.status() === 200,
  );
  await page.getByRole("button", { name: "Save input" }).click();
  await staleCaseReadStarted;
  expect(staleCaseBodies).toHaveLength(1);
  await expect(
    page
      .getByRole("dialog", { name: "Edit case-1" })
      .getByRole("region", { name: "Saved changes awaiting refresh" }),
  ).toBeVisible();
  const staleCaseTargetHash = `#/p/${registrationId}/d/${decisionId}/examples?dataset=${encodeURIComponent(datasetId)}&case=case-2`;
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, staleCaseTargetHash);
  const discardStaleCaseRead = page.getByRole("dialog", {
    name: "Unsaved changes",
  });
  await expect(discardStaleCaseRead).toBeVisible();
  await discardStaleCaseRead
    .getByRole("button", { name: "Discard changes", exact: true })
    .click();
  const staleCaseTargetUrl = new URL(
    staleCaseTargetHash,
    page.url(),
  ).toString();
  await expect(page).toHaveURL(staleCaseTargetUrl);
  releaseStaleCaseRead();
  await (await staleCaseReadResponse).body();
  expect(staleCaseBodies).toHaveLength(1);
  expect(staleCaseBodies[0]?.input_source).toBe(staleCaseSource);
  await caseTwoReadStarted;
  await expect(
    page.getByLabel("Complete example input source", { exact: true }),
  ).toHaveText(caseOneOriginalSource);
  releaseCaseTwoRead();
  await (await caseTwoReadResponse).body();
  await expect(
    page.getByRole("heading", { name: "case-2", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Complete example input source", { exact: true }),
  ).toHaveText(caseTwoOriginalSource);
  await expect(
    page.getByRole("button", { name: "Refresh saved case" }),
  ).toHaveCount(0);
  await page.unroute("**/cases/case-1");
  await page.unroute("**/cases/case-2");
  const caseOneExamplesHash = `#/p/${registrationId}/d/${decisionId}/examples?dataset=${encodeURIComponent(datasetId)}&case=case-1`;
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, caseOneExamplesHash);
  await expect(page).toHaveURL(
    new URL(caseOneExamplesHash, page.url()).toString(),
  );
  await expect(
    page.getByRole("heading", { name: "case-1", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Complete example input source", { exact: true }),
  ).toHaveText(staleCaseSource);
  await expect(
    page.getByRole("button", { name: "Refresh saved case" }),
  ).toHaveCount(0);
  let releaseSeedCaseRead!: () => void;
  let reportSeedCaseReadStarted!: () => void;
  let seedCaseSource: string | undefined;
  const holdSeedCaseRead = new Promise<void>((resolve) => {
    releaseSeedCaseRead = resolve;
  });
  const seedCaseReadStarted = new Promise<void>((resolve) => {
    reportSeedCaseReadStarted = resolve;
  });
  let labelWritesDuringSelection = 0;
  const countSelectionLabelWrites = (request: Request) => {
    if (request.method() === "POST" && request.url().endsWith("/labels/batch"))
      labelWritesDuringSelection += 1;
  };
  page.on("request", countSelectionLabelWrites);
  await page.route("**/cases/seed-1", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    reportSeedCaseReadStarted();
    await holdSeedCaseRead;
    const response = await route.fetch();
    const responseData = await response.json();
    const source = responseData.data.case.record.input_source;
    if (typeof source !== "string")
      throw new Error("The admitted case read has no input source.");
    seedCaseSource = source;
    await route.fulfill({ response });
  });
  await caseButton("seed-1").click();
  await seedCaseReadStarted;
  const admittedSeedRead = page.waitForResponse(
    (response) =>
      response.url().endsWith("/cases/seed-1") &&
      response.request().method() === "GET" &&
      response.status() === 200,
  );
  try {
    await expect(
      page.getByLabel("Complete example input source", { exact: true }),
    ).toHaveText(staleCaseSource);
    await expect(
      page.getByRole("checkbox", { name: "Option A", exact: true }),
    ).toBeDisabled();
    expect(labelWritesDuringSelection).toBe(0);
    await captureScreenshot(
      "selection-loading-keeps-old-controls-readonly.png",
    );
  } finally {
    releaseSeedCaseRead();
  }
  await (await admittedSeedRead).body();
  await expect(
    page.getByRole("heading", { name: "seed-1", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Expected answers" }),
  ).toBeVisible();
  if (seedCaseSource === undefined)
    throw new Error("The admitted case read did not provide its source.");
  await expect(
    page.getByLabel("Complete example input source", { exact: true }),
  ).toHaveText(seedCaseSource);
  await expect(page.getByRole("checkbox", { name: "Option A" })).toBeEnabled();
  await captureScreenshot("selection-admitted-target-controls-ready.png");
  await page.getByRole("checkbox", { name: "Option A", exact: true }).check();
  await expect(
    page.getByRole("button", { name: "Save expected answer", exact: true }),
  ).toBeEnabled();
  await page.getByRole("checkbox", { name: "Option A", exact: true }).uncheck();
  expect(labelWritesDuringSelection).toBe(0);
  await page.unroute("**/cases/seed-1");
  page.off("request", countSelectionLabelWrites);
  const readSeedLabel = async () => {
    const response = await page.request.get(
      `/api/v1/projects/${registrationId}/decisions/${decisionId}/datasets/${datasetId}/labels/seed-1`,
      {
        headers: {
          Origin: origin,
          "X-Deykit-Capability": capability as string,
        },
      },
    );
    if (response.status() !== 200) {
      const failure = await response.json().catch(() => undefined);
      const error = isRecord(failure) ? failure.error : undefined;
      const details = isRecord(error) ? error : undefined;
      const diagnostic = {
        route_pattern: safeRoutePattern(new URL(response.url()).pathname),
        status: response.status(),
        code: safeErrorIdentifier(details?.code),
        reason: safeErrorIdentifier(details?.reason),
      };
      apiFailures.push(diagnostic);
      await recordProgress();
      expect(response.status(), JSON.stringify(diagnostic)).toBe(200);
    }
    const envelope: unknown = await response.json();
    expect(
      isRecord(envelope) &&
        envelope.schema_version === 1 &&
        isRecord(envelope.data),
    ).toBe(true);
    return response;
  };
  const emptySeedLabel = await readSeedLabel();
  expect((await emptySeedLabel.json()).data.label).toBeNull();
  await page.getByRole("checkbox", { name: "Option A" }).check();
  await page.getByRole("checkbox", { name: "Option B" }).check();
  const stagedLabelHash = page.url();
  await caseButton("case-2").click();
  const keepStagedSelection = page.getByRole("dialog", {
    name: "Unsaved changes",
  });
  await expect(keepStagedSelection).toBeVisible();
  await keepStagedSelection
    .getByRole("button", { name: "Keep editing", exact: true })
    .click();
  await expect(page).toHaveURL(stagedLabelHash);
  await expect(
    page.getByRole("heading", { name: "seed-1", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Option A" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Option B" })).toBeChecked();
  const stillUnlabelled = await readSeedLabel();
  expect((await stillUnlabelled.json()).data.label).toBeNull();
  await page
    .getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: decisionName, exact: true })
    .click();
  const keepStagedLabel = page.getByRole("dialog", { name: "Unsaved changes" });
  await expect(keepStagedLabel).toBeVisible();
  await keepStagedLabel
    .getByRole("button", { name: "Keep editing", exact: true })
    .click();
  await expect(page.getByRole("checkbox", { name: "Option A" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Option B" })).toBeChecked();
  await page
    .getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: decisionName, exact: true })
    .click();
  const discardStagedLabel = page.getByRole("dialog", {
    name: "Unsaved changes",
  });
  await discardStagedLabel
    .getByRole("button", { name: "Discard changes", exact: true })
    .click();
  await expect(page.getByLabel("Decision name")).toHaveValue(decisionName);
  expect((await (await readSeedLabel()).json()).data.label).toBeNull();
  await page
    .getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: "Examples", exact: true })
    .click();
  await expect(page.getByRole("heading", { name: "Examples" })).toBeVisible();
  await caseButton("seed-1").click();
  await page.getByRole("checkbox", { name: "Option A" }).check();
  await page.getByRole("checkbox", { name: "Option B" }).check();

  let releaseLabelSave!: () => void;
  let reportLabelSaveStarted!: () => void;
  const labelSaveStarted = new Promise<void>((resolve) => {
    reportLabelSaveStarted = resolve;
  });
  const holdLabelSave = new Promise<void>((resolve) => {
    releaseLabelSave = resolve;
  });
  let heldLabelSave = false;
  let droppedCommittedLabelResponse = false;
  let losingLabelBody: Record<string, unknown> | undefined;
  const labelMutationBodies: Array<Record<string, unknown>> = [];
  await page.route("**/labels/batch", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const body = route.request().postDataJSON() as Record<string, unknown>;
    labelMutationBodies.push(body);
    if (!heldLabelSave) {
      heldLabelSave = true;
      losingLabelBody = body;
      reportLabelSaveStarted();
      await holdLabelSave;
    }
    const response = await route.fetch();
    const edits = body.edits as Array<Record<string, unknown>>;
    if (edits[0]?.action === "dispute" && !droppedCommittedLabelResponse) {
      droppedCommittedLabelResponse = true;
      await route.abort("failed");
      return;
    }
    await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "Save expected answer" }).click();
  await labelSaveStarted;
  expect(losingLabelBody).toBeDefined();
  const losingEdits = losingLabelBody?.edits as Array<Record<string, unknown>>;
  const winningLabelBody = {
    ...losingLabelBody,
    operation_id: "m10-label-race-winner",
    edits: losingEdits.map((edit) => ({
      ...edit,
      acceptable_option_ids: ["option-a"],
    })),
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
  await expect(
    page.getByRole("button", { name: "Review current label" }),
  ).toBeEnabled();
  await expect(page.getByRole("checkbox", { name: "Option A" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Option B" })).toBeChecked();
  expect(
    (await (await readSeedLabel()).json()).data.label.acceptable_option_ids,
  ).toEqual(["option-a"]);
  await page.getByRole("button", { name: "Review current label" }).click();
  await expect(
    page.getByRole("button", { name: "Review current label" }),
  ).toHaveCount(0);
  await expect(page.getByRole("checkbox", { name: "Option A" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Option B" })).toBeChecked();
  const expectedLabelSaveResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/labels/batch") &&
      response.request().method() === "POST",
  );
  let labelRefreshFailures = 2;
  await page.route("**/labels/seed-1", async (route) => {
    if (route.request().method() === "GET" && labelRefreshFailures > 0) {
      labelRefreshFailures -= 1;
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          schema_version: 1,
          error: {
            schema_version: 1,
            code: "internal_error",
            message: "The local service could not complete the request.",
            reason: "injected_read_failure",
          },
        }),
      });
      return;
    }
    await route.continue();
  });
  const labelMutationCountBeforeReceipt = labelMutationBodies.length;
  const failedLabelRefresh = page.waitForResponse(
    (response) =>
      response.url().endsWith("/labels/seed-1") &&
      response.request().method() === "GET" &&
      response.status() === 503,
  );
  await page.getByRole("button", { name: "Save expected answer" }).click();
  const expectedLabelReceipt = await expectedLabelSaveResponse;
  expect(expectedLabelReceipt.status()).toBe(200);
  await expectedLabelReceipt.body();
  await (await failedLabelRefresh).body();
  await expect(
    page.getByRole("region", { name: "Saved changes awaiting refresh" }),
  ).toContainText("Label saved; refresh its current review");
  await captureScreenshot("label-saved-refresh-pending.png");
  await expect(page.getByRole("checkbox", { name: "Option A" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Option B" })).toBeChecked();
  await expect(
    page.getByRole("button", { name: "Dispute label" }),
  ).toBeDisabled();
  expect(labelMutationBodies).toHaveLength(labelMutationCountBeforeReceipt + 1);
  const writesDuringCommittedLabelRefresh = mutationRequests.length;
  const importCommitsBeforeBlockedActions = importCommitBodies.length;
  const splitCommitsBeforeBlockedActions = splitCommitBodies.length;
  await expect(
    page.getByRole("button", { name: "Import examples" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Split dataset" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Add example" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Remove case" }),
  ).toBeDisabled();
  expect(addBodies).toHaveLength(0);
  expect(removeBodies).toHaveLength(0);
  expect(mutationRequests).toHaveLength(writesDuringCommittedLabelRefresh);
  expect(importCommitBodies).toHaveLength(importCommitsBeforeBlockedActions);
  expect(splitCommitBodies).toHaveLength(splitCommitsBeforeBlockedActions);
  const committedLabelHash = page.url();
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, `#/p/${registrationId}/d/${decisionId}`);
  const committedLabelGuard = page.getByRole("dialog", {
    name: "Unsaved changes",
  });
  await expect(committedLabelGuard).toBeVisible();
  await expect(committedLabelGuard).toContainText(
    "The label was saved. Refresh its current review before leaving this examples page.",
  );
  await expect(
    committedLabelGuard.getByRole("button", {
      name: "Save and leave",
      exact: true,
    }),
  ).toBeDisabled();
  await expect(
    committedLabelGuard.getByRole("button", {
      name: "Discard changes",
      exact: true,
    }),
  ).toBeEnabled();
  await committedLabelGuard
    .getByRole("button", { name: "Keep editing", exact: true })
    .click();
  await expect(page).toHaveURL(committedLabelHash);
  expect(labelMutationBodies).toHaveLength(labelMutationCountBeforeReceipt + 1);
  const failedLabelRecovery = page.waitForResponse(
    (response) =>
      response.url().endsWith("/labels/seed-1") &&
      response.request().method() === "GET" &&
      response.status() === 503,
  );
  await page.getByRole("button", { name: "Refresh saved label" }).click();
  await (await failedLabelRecovery).body();
  await expect(
    page.getByText("The local service could not complete the request."),
  ).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Option A" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Option B" })).toBeChecked();
  expect(labelMutationBodies).toHaveLength(labelMutationCountBeforeReceipt + 1);

  const labelBeforeExternalClear = await readSeedLabel();
  expect(labelBeforeExternalClear.status()).toBe(200);
  const labelBeforeExternalClearBody = (await labelBeforeExternalClear.json())
    .data;
  expect(labelBeforeExternalClearBody.label.acceptable_option_ids).toEqual([
    "option-a",
    "option-b",
  ]);
  const externalClearOperationId = "m10-external-clear-after-label-receipt";
  const externalClearReceipt = await page.request.post(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}/datasets/${datasetId}/labels/batch`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
      data: {
        schema_version: 1,
        operation_id: externalClearOperationId,
        edits: [
          { review: labelBeforeExternalClearBody.review, action: "clear" },
        ],
      },
    },
  );
  expect(externalClearReceipt.status()).toBe(200);
  await externalClearReceipt.body();

  const recoveredLabelRead = page.waitForResponse(
    (response) =>
      response.url().endsWith("/labels/seed-1") &&
      response.request().method() === "GET" &&
      response.status() === 200,
  );
  await page.getByRole("button", { name: "Refresh saved label" }).click();
  await (await recoveredLabelRead).body();
  await expect(
    page.getByRole("button", { name: "Review current label" }),
  ).toBeEnabled();
  await expect(page.getByRole("checkbox", { name: "Option A" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Option B" })).toBeChecked();
  expect(labelMutationBodies).toHaveLength(labelMutationCountBeforeReceipt + 1);
  await page.unroute("**/labels/seed-1");
  let savedLabel = await readSeedLabel();
  expect((await savedLabel.json()).data.label).toBeNull();
  await page.getByRole("button", { name: "Review current label" }).click();
  await expect(
    page.getByRole("button", { name: "Review current label" }),
  ).toHaveCount(0);
  await expect(page.getByRole("checkbox", { name: "Option A" })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Option B" })).toBeChecked();
  expect(labelMutationBodies).toHaveLength(labelMutationCountBeforeReceipt + 1);
  const deliberateLabelSaveResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/labels/batch") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Save expected answer" }).click();
  const deliberateLabelSaveReceipt = await deliberateLabelSaveResponse;
  expect(deliberateLabelSaveReceipt.status()).toBe(200);
  await deliberateLabelSaveReceipt.body();
  const deliberateLabelBody = labelMutationBodies.at(-1);
  expect(deliberateLabelBody?.operation_id).not.toBe(externalClearOperationId);
  expect(
    (deliberateLabelBody?.edits as Array<Record<string, unknown>>)[0],
  ).toMatchObject({
    action: "set",
    acceptable_option_ids: ["option-a", "option-b"],
  });
  await expect(
    page.getByRole("button", { name: "Dispute label" }),
  ).toBeEnabled();
  savedLabel = await readSeedLabel();
  expect((await savedLabel.json()).data.label).toMatchObject({
    acceptable_option_ids: ["option-a", "option-b"],
    provenance: "human",
    status: "active",
  });
  const disputeReason = "The source does not support this assigned answer.";
  await page.getByLabel("Provenance note").fill(disputeReason);
  await page.getByRole("button", { name: "Dispute label" }).click();
  await expect(
    page.getByRole("button", { name: "Retry original label request" }),
  ).toBeVisible();
  expect(labelMutationBodies.at(-1)?.operation_id).toBeTruthy();
  const firstDisputeEdit = (
    labelMutationBodies.at(-1)?.edits as Array<Record<string, unknown>>
  )[0];
  expect(firstDisputeEdit?.action).toBe("dispute");
  expect(firstDisputeEdit?.note).toBe(disputeReason);
  const unknownLabelHash = page.url();
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, `#/p/${registrationId}/d/${decisionId}`);
  const unknownLabelGuard = page.getByRole("dialog", {
    name: "Unsaved changes",
  });
  await expect(unknownLabelGuard).toBeVisible();
  await expect(
    unknownLabelGuard.getByRole("button", {
      name: "Discard changes",
      exact: true,
    }),
  ).toBeDisabled();
  await unknownLabelGuard
    .getByRole("button", { name: "Keep editing", exact: true })
    .click();
  await expect(page).toHaveURL(unknownLabelHash);
  expect(
    labelMutationBodies.filter(
      (body) =>
        (body.edits as Array<Record<string, unknown>>)[0]?.action === "dispute",
    ),
  ).toHaveLength(1);
  await page
    .getByRole("button", { name: "Retry original label request" })
    .click();
  await expect(
    page.getByRole("button", { name: "Retry original label request" }),
  ).toHaveCount(0);
  const disputeBodies = labelMutationBodies.filter(
    (body) =>
      (body.edits as Array<Record<string, unknown>>)[0]?.action === "dispute",
  );
  expect(disputeBodies).toHaveLength(2);
  expect(disputeBodies[1]).toEqual(disputeBodies[0]);
  expect(
    (disputeBodies[0]?.edits as Array<Record<string, unknown>>)[0]?.note,
  ).toBe(disputeReason);
  expect(
    (disputeBodies[1]?.edits as Array<Record<string, unknown>>)[0]?.note,
  ).toBe(disputeReason);
  await expect(
    page.getByRole("button", { name: "Resolve dispute with staged set" }),
  ).toBeEnabled();
  savedLabel = await readSeedLabel();
  expect((await savedLabel.json()).data.label.status).toBe("disputed");
  const resolveLabelResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/labels/batch") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Resolve dispute with staged set" })
    .click();
  const resolvedLabelReceipt = await resolveLabelResponse;
  expect(resolvedLabelReceipt.status()).toBe(200);
  await resolvedLabelReceipt.body();
  await expect(
    page.getByRole("button", { name: "Dispute label" }),
  ).toBeEnabled();
  savedLabel = await readSeedLabel();
  expect((await savedLabel.json()).data.label).toMatchObject({
    status: "active",
    provenance: "human",
  });
  const clearNote = "This note remains visible until the clear is saved.";
  await page.getByLabel("Provenance note").fill(clearNote);
  await expect(page.getByLabel("Provenance note")).toHaveValue(clearNote);
  const clearLabelResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/labels/batch") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Clear label" }).click();
  const clearedLabelReceipt = await clearLabelResponse;
  expect(clearedLabelReceipt.status()).toBe(200);
  await clearedLabelReceipt.body();
  const clearEdit = (
    labelMutationBodies.at(-1)?.edits as Array<Record<string, unknown>>
  )[0];
  expect(clearEdit?.action).toBe("clear");
  expect(clearEdit).not.toHaveProperty("note");
  await expect(page.getByRole("checkbox", { name: "Option A" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Clear label" })).toHaveCount(
    0,
  );
  const clearedLabel = await readSeedLabel();
  expect((await clearedLabel.json()).data.label).toBeNull();

  const expectSuccessfulRead = async (
    response: APIResponse,
    operation: "case_read" | "case_label_read",
  ) => {
    const status = response.status();
    let code: string | null = null;
    let reason: string | null = null;
    if (status !== 200) {
      try {
        const payload: unknown = await response.json();
        if (isRecord(payload) && isRecord(payload.error)) {
          code = safeErrorIdentifier(payload.error.code);
          reason = safeErrorIdentifier(payload.error.reason);
        }
      } catch {
        // Keep diagnostics limited to safe API identifiers and status.
      }
    }
    expect(status, JSON.stringify({ operation, status, code, reason })).toBe(
      200,
    );
    const envelope: unknown = await response.json();
    expect(
      isRecord(envelope) &&
        envelope.schema_version === 1 &&
        isRecord(envelope.data),
    ).toBe(true);
    return response;
  };
  const readCaseOne = async () =>
    expectSuccessfulRead(
      await page.request.get(
        `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/case-1`,
        {
          headers: {
            Origin: origin,
            "X-Deykit-Capability": capability as string,
          },
        },
      ),
      "case_read",
    );
  const readCaseOneLabel = async () =>
    expectSuccessfulRead(
      await page.request.get(
        `/api/v1/projects/${registrationId}/decisions/${decisionId}/datasets/${datasetId}/labels/case-1`,
        {
          headers: {
            Origin: origin,
            "X-Deykit-Capability": capability as string,
          },
        },
      ),
      "case_label_read",
    );
  await caseButton("case-1").click();
  await expect(
    page.getByRole("heading", { name: "case-1", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Complete example input source", { exact: true }),
  ).toHaveText(staleCaseSource);
  await expect(
    page.getByRole("heading", { name: "Expected answers" }),
  ).toBeVisible();
  await expect(
    page.getByRole("status").filter({ hasText: "Excluded: stale" }),
  ).toBeVisible();
  const staleCaseOneLabelResponse = await readCaseOneLabel();
  expect(staleCaseOneLabelResponse.status()).toBe(200);
  const staleCaseOneLabel = (await staleCaseOneLabelResponse.json()).data;
  expect(staleCaseOneLabel).toMatchObject({
    status: "excluded",
    reasons: ["stale"],
  });
  const staleCaseOneSourceHash = staleCaseOneLabel.review.input_hash;
  const optionA = page.getByRole("checkbox", { name: "Option A" });
  const optionB = page.getByRole("checkbox", { name: "Option B" });
  await expect(optionA).toBeEnabled();
  if (await optionA.isChecked()) await optionA.uncheck();
  if (await optionB.isChecked()) await optionB.uncheck();
  await optionA.check();
  const reactivatedLabelResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/labels/batch") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Save expected answer" }).click();
  const reactivatedLabelReceipt = await reactivatedLabelResponse;
  expect(reactivatedLabelReceipt.status()).toBe(200);
  await reactivatedLabelReceipt.body();
  await expect(
    page.getByRole("button", { name: "Dispute label" }),
  ).toBeEnabled();
  await expect(
    page.getByRole("status").filter({ hasText: /^Applicable/ }),
  ).toBeVisible();
  const applicableCaseOneLabelResponse = await readCaseOneLabel();
  expect(applicableCaseOneLabelResponse.status()).toBe(200);
  const applicableCaseOneLabel = (await applicableCaseOneLabelResponse.json())
    .data;
  expect(applicableCaseOneLabel.status).toBe("applicable");
  expect(applicableCaseOneLabel.reasons).toEqual([]);
  expect(applicableCaseOneLabel.review.input_hash).toBe(staleCaseOneSourceHash);
  expect(applicableCaseOneLabel.label.input_hash).toBe(
    applicableCaseOneLabel.review.input_hash,
  );
  expect(applicableCaseOneLabel.review.input_hash).not.toBe(
    staleCaseOneLabel.label.input_hash,
  );

  const caseBeforeTagResponse = await readCaseOne();
  expect(caseBeforeTagResponse.status()).toBe(200);
  const caseBeforeTag = (await caseBeforeTagResponse.json()).data;
  expect(caseBeforeTag.case.record.input_source).toBe(staleCaseSource);
  const caseOneInputHashBeforeTag = applicableCaseOneLabel.review.input_hash;
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
  await tagOnly.body();
  const caseOneLabelAfterTagResponse = await readCaseOneLabel();
  expect(caseOneLabelAfterTagResponse.status()).toBe(200);
  const caseOneLabelAfterTag = (await caseOneLabelAfterTagResponse.json()).data;
  expect(caseOneLabelAfterTag.status).toBe("applicable");
  expect(caseOneLabelAfterTag.review.input_hash).toBe(
    caseOneInputHashBeforeTag,
  );
  expect(caseOneLabelAfterTag.label).toEqual(applicableCaseOneLabel.label);

  await page.reload();
  await expect(page.getByRole("heading", { name: "Examples" })).toBeVisible();
  await page.getByRole("button", { name: "Add example", exact: true }).click();
  await page.getByRole("radio", { name: "JSON", exact: true }).check();
  const proposedAddSource = '{"proposal":"keep-after-review"}';
  await page
    .getByLabel("Input source", { exact: true })
    .fill(proposedAddSource);
  let releaseAdd!: () => void;
  let reportAddStarted!: () => void;
  const addGate = new Promise<void>((resolve) => {
    releaseAdd = resolve;
  });
  const addStarted = new Promise<void>((resolve) => {
    reportAddStarted = resolve;
  });
  let heldAdd = false;
  await page.route("**/datasets/*/cases", async (route) => {
    if (route.request().method() === "POST") {
      addBodies.push(route.request().postDataJSON() as Record<string, unknown>);
      if (!heldAdd) {
        heldAdd = true;
        reportAddStarted();
        await addGate;
      }
    }
    await route.continue();
  });
  await page
    .getByRole("button", { name: "Add example", exact: true })
    .last()
    .click();
  await addStarted;
  expect(addBodies).toHaveLength(1);
  expect(addBodies[0]?.input_kind).toBe("json");
  expect(addBodies[0]?.input_source).toBe(proposedAddSource);
  const addDataset = await page.request.get(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  const addDatasetData = (await addDataset.json()).data;
  const addWinner = await page.request.post(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
      data: {
        schema_version: 1,
        operation_id: "m10-add-case-conflict-winner",
        expected_dataset_etag: addDatasetData.etag,
        case_id: "m10-add-conflict-winner",
        input_kind: "json",
        input_source: '{"proposal":"winner"}',
        metadata_source: "{}",
        tags: [],
        split: "development",
        group_id: null,
        derived_from: [],
      },
    },
  );
  if (addWinner.status() !== 200) {
    const failure = await addWinner.json().catch(() => undefined);
    const error = isRecord(failure) ? failure.error : undefined;
    const details = isRecord(error) ? error : undefined;
    const diagnostic = {
      route_pattern: safeRoutePattern(new URL(addWinner.url()).pathname),
      status: addWinner.status(),
      code: safeErrorIdentifier(details?.code),
      reason: safeErrorIdentifier(details?.reason),
    };
    apiFailures.push(diagnostic);
    await recordProgress();
    expect(addWinner.status(), JSON.stringify(diagnostic)).toBe(200);
  }
  await addWinner.body();
  releaseAdd();
  await expect(
    page.getByRole("button", { name: "Review current cases and dataset" }),
  ).toBeVisible();
  await expect(page.getByLabel("Input source", { exact: true })).toHaveValue(
    proposedAddSource,
  );
  await page
    .getByRole("button", { name: "Review current cases and dataset" })
    .click();
  const selectedCaseReadPath = `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/`;
  const selectedLabelReadPath = `/api/v1/projects/${registrationId}/decisions/${decisionId}/datasets/${datasetId}/labels/`;
  const selectedCaseReadResponse = page.waitForResponse(
    (response) => {
      const pathname = new URL(response.url()).pathname;
      return (
        response.request().method() === "GET" &&
        pathname.startsWith(selectedCaseReadPath) &&
        pathname.slice(selectedCaseReadPath.length).length > 0 &&
        !pathname.slice(selectedCaseReadPath.length).includes("/")
      );
    },
    { timeout: 0 },
  );
  const selectedLabelReadResponse = page.waitForResponse(
    (response) => {
      const pathname = new URL(response.url()).pathname;
      return (
        response.request().method() === "GET" &&
        pathname.startsWith(selectedLabelReadPath) &&
        pathname.slice(selectedLabelReadPath.length).length > 0 &&
        !pathname.slice(selectedLabelReadPath.length).includes("/")
      );
    },
    { timeout: 0 },
  );
  const labelListReadResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      new URL(response.url()).pathname ===
        `/api/v1/projects/${registrationId}/decisions/${decisionId}/datasets/${datasetId}/labels`,
    { timeout: 0 },
  );
  const refreshedReadResponsesPromise = Promise.all([
    selectedCaseReadResponse,
    selectedLabelReadResponse,
    labelListReadResponse,
  ]);
  void refreshedReadResponsesPromise.catch(() => undefined);
  const reapplyAddResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/cases") &&
      response.request().method() === "POST",
  );
  const reapplyAddStartedAt = Date.now();
  await page.getByRole("button", { name: "Reapply reviewed example" }).click();
  const reapplyAddReceipt = await reapplyAddResponse;
  expect(reapplyAddReceipt.status()).toBe(200);
  const reapplyAddReceiptData = (await reapplyAddReceipt.json()).data;
  const reapplyAddReceiptElapsed = Math.max(
    0,
    Date.now() - reapplyAddStartedAt,
  );
  actionTimings.push({
    action: "reapply_add",
    stage: "receipt",
    elapsed_ms: reapplyAddReceiptElapsed,
  });
  const refreshReadinessStartedAt = Date.now();
  let refreshReadinessTimer: ReturnType<typeof setTimeout> | undefined;
  const refreshReadinessTask = async () => {
    const responses = await refreshedReadResponsesPromise;
    for (const response of responses) {
      expect(response.status()).toBe(200);
      await response.body();
    }
    await Promise.all([
      expect(page.getByRole("button", { name: "Edit input" })).toBeEnabled({
        timeout: 9_000,
      }),
      expect(
        page.getByText("Loading selected example…", { exact: true }),
      ).toHaveCount(0, { timeout: 9_000 }),
      expect(page.getByText("Loading labels…", { exact: true })).toHaveCount(
        0,
        { timeout: 9_000 },
      ),
    ]);
  };
  const boundedRefreshReadiness = Promise.race([
    refreshReadinessTask(),
    new Promise<never>((_resolve, reject) => {
      refreshReadinessTimer = setTimeout(
        () =>
          reject(new Error("Example refresh did not settle after reapply.")),
        10_000,
      );
    }),
  ]);
  void boundedRefreshReadiness.catch(() => undefined);
  try {
    await recordProgress();
    await boundedRefreshReadiness;
  } finally {
    if (refreshReadinessTimer !== undefined)
      clearTimeout(refreshReadinessTimer);
    actionTimings.push({
      action: "reapply_add",
      stage: "readiness",
      elapsed_ms: Math.max(0, Date.now() - refreshReadinessStartedAt),
    });
    await recordProgress();
  }
  const reapplyAddData = reapplyAddReceiptData;
  expect(addBodies).toHaveLength(2);
  expect(addBodies[1].input_source).toBe(proposedAddSource);
  expect(addBodies[1].input_kind).toBe("json");
  expect(addBodies[1].operation_id).not.toBe(addBodies[0].operation_id);
  expect(addBodies[1].expected_dataset_etag).not.toBe(
    addBodies[0].expected_dataset_etag,
  );
  expect(reapplyAddData.case).not.toBeNull();
  const reapplyAddedCaseId = reapplyAddData.case.record.id as string;
  await page.unroute("**/datasets/*/cases");
  await expect(page.getByRole("dialog", { name: "Add example" })).toHaveCount(
    0,
  );
  await expect(caseButton(reapplyAddedCaseId)).toBeVisible();

  await enterPhase("Case source preservation and stale-label applicability");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Examples" })).toBeVisible();
  await caseButton("case-1").click();
  await page.getByRole("button", { name: "Edit input" }).click();
  await page
    .getByLabel("Input source", { exact: true })
    .fill('{"case":1,"changed":true}');
  const caseEditBodies: Array<Record<string, unknown>> = [];
  let releaseCaseEdit!: () => void;
  let reportCaseEditStarted!: () => void;
  const caseEditGate = new Promise<void>((resolve) => {
    releaseCaseEdit = resolve;
  });
  const caseEditStarted = new Promise<void>((resolve) => {
    reportCaseEditStarted = resolve;
  });
  let heldCaseEdit = false;
  await page.route("**/cases/case-1", async (route) => {
    if (route.request().method() === "PUT") {
      caseEditBodies.push(
        route.request().postDataJSON() as Record<string, unknown>,
      );
      if (!heldCaseEdit) {
        heldCaseEdit = true;
        reportCaseEditStarted();
        await caseEditGate;
      }
    }
    await route.continue();
  });
  await page.getByRole("button", { name: "Save input" }).click();
  await caseEditStarted;
  const caseEditBeforeWinner = (await (await readCaseOne()).json()).data;
  const caseEditWinner = await page.request.put(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/case-1`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
      data: {
        schema_version: 1,
        operation_id: "m10-case-edit-conflict-winner",
        expected_case_etag: caseEditBeforeWinner.case.etag,
        expected_dataset_etag: caseEditBeforeWinner.dataset_etag,
        input_kind: caseEditBeforeWinner.case.record.input_kind,
        input_source: '{"case":1,"winner":true}',
        tags: caseEditBeforeWinner.case.record.tags,
        split: caseEditBeforeWinner.case.record.split,
        group_id: caseEditBeforeWinner.case.record.group_id,
        derived_from: caseEditBeforeWinner.case.record.derived_from,
        metadata_source: caseEditBeforeWinner.case.record.metadata_source,
      },
    },
  );
  expect(caseEditWinner.status()).toBe(200);
  releaseCaseEdit();
  await expect(
    page.getByRole("button", { name: "Review current case and dataset" }),
  ).toBeVisible();
  await expect(page.getByLabel("Input source", { exact: true })).toHaveValue(
    '{"case":1,"changed":true}',
  );
  await page
    .getByRole("button", { name: "Review current case and dataset" })
    .click();
  const caseEditDialog = page.getByRole("dialog", { name: "Edit case-1" });
  await expect(
    caseEditDialog.getByRole("region", { name: "Review selected context" }),
  ).toContainText(
    "The current example or label context changed. Review it before making another change.",
  );
  await expect(
    caseEditDialog.getByRole("button", {
      name: "Reapply reviewed case edit",
    }),
  ).toBeDisabled();
  await expect(page.getByLabel("Input source", { exact: true })).toHaveValue(
    '{"case":1,"changed":true}',
  );
  await caseEditDialog
    .getByRole("button", { name: "Review current selection" })
    .click();
  await expect(
    caseEditDialog.getByRole("region", { name: "Review selected context" }),
  ).toHaveCount(0);
  await expect(
    caseEditDialog.getByRole("button", {
      name: "Reapply reviewed case edit",
    }),
  ).toBeEnabled();
  await expect(page.getByLabel("Input source", { exact: true })).toHaveValue(
    '{"case":1,"changed":true}',
  );
  const reapplyCaseEditResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/cases/case-1") &&
      response.request().method() === "PUT",
  );
  await caseEditDialog
    .getByRole("button", { name: "Reapply reviewed case edit" })
    .click();
  const reapplyCaseEditReceipt = await reapplyCaseEditResponse;
  expect(reapplyCaseEditReceipt.status()).toBe(200);
  await reapplyCaseEditReceipt.body();
  await expect(page.getByRole("button", { name: "Edit input" })).toBeVisible();
  expect(caseEditBodies).toHaveLength(2);
  expect(caseEditBodies[1].input_source).toBe('{"case":1,"changed":true}');
  expect(caseEditBodies[1].operation_id).not.toBe(
    caseEditBodies[0].operation_id,
  );
  expect(caseEditBodies[1].expected_case_etag).not.toBe(
    caseEditBodies[0].expected_case_etag,
  );
  expect(caseEditBodies[1].expected_dataset_etag).not.toBe(
    caseEditBodies[0].expected_dataset_etag,
  );
  await page.unroute("**/cases/case-1");
  await expect(page.getByRole("dialog", { name: "Edit case-1" })).toHaveCount(
    0,
    { timeout: 15_000 },
  );
  await expect(
    page.getByLabel("Complete example input source", { exact: true }),
  ).toHaveText('{"case":1,"changed":true}', { timeout: 15_000 });
  await expect(
    page.getByRole("region", { name: "Saved changes awaiting refresh" }),
  ).toHaveCount(0);
  const caseSelectionReview = page.getByRole("region", {
    name: "Review selected context",
  });
  await expect(caseSelectionReview).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit input" })).toBeDisabled();
  await caseSelectionReview
    .getByRole("button", { name: "Review current selection" })
    .click();
  await expect(caseSelectionReview).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Edit input" })).toBeEnabled();
  await expect(
    page.getByLabel("Complete example input source", { exact: true }),
  ).toHaveText('{"case":1,"changed":true}');
  expect(caseEditBodies).toHaveLength(2);
  const staleLabel = await readCaseOneLabel();
  expect((await staleLabel.json()).data).toMatchObject({
    status: "excluded",
    reasons: ["stale"],
  });

  type ObservedProjectRead = {
    route_pattern: string;
    startedAt: number;
    settled: Promise<void>;
    finish: (
      terminal: "body" | "body_error" | "cancelled",
      status?: number,
    ) => void;
  };
  const pendingProjectReads = new Map<Request, ObservedProjectRead>();
  const finishProjectRead = (
    request: Request,
    terminal: "body" | "body_error" | "cancelled",
    status?: number,
  ) => pendingProjectReads.get(request)?.finish(terminal, status);
  page.on("request", (request) => {
    if (request.method() !== "GET") return;
    const routePattern = safeRoutePattern(new URL(request.url()).pathname);
    if (!sourceReadTemplates.has(routePattern)) return;
    let settle!: () => void;
    const settled = new Promise<void>((resolve) => {
      settle = resolve;
    });
    let terminalRecorded = false;
    pendingProjectReads.set(request, {
      route_pattern: routePattern,
      startedAt: Date.now(),
      settled,
      finish: (terminal, status) => {
        if (terminalRecorded) return;
        terminalRecorded = true;
        const startedAt = pendingProjectReads.get(request)?.startedAt;
        recordSourceReadEvent({
          event: terminal,
          route_pattern: routePattern,
          method: "GET",
          elapsed_ms: startedAt === undefined ? 0 : Date.now() - startedAt,
          ...(status === undefined ? {} : { status }),
        });
        pendingProjectReads.delete(request);
        pendingSourceReadCategories = [
          ...new Set(
            [...pendingProjectReads.values()].map((read) => read.route_pattern),
          ),
        ];
        settle();
        if (recordLateSourceReadProgress)
          void recordProgress().catch(() => undefined);
      },
    });
    pendingSourceReadCategories = [
      ...new Set(
        [...pendingProjectReads.values()].map((read) => read.route_pattern),
      ),
    ];
    if (recordLateSourceReadProgress)
      void recordProgress().catch(() => undefined);
  });
  page.on("response", (response) => {
    if (!pendingProjectReads.has(response.request())) return;
    const pending = pendingProjectReads.get(response.request());
    if (pending)
      recordSourceReadEvent({
        event: "headers",
        route_pattern: pending.route_pattern,
        method: "GET",
        elapsed_ms: Math.max(0, Date.now() - pending.startedAt),
        status: response.status(),
      });
    void response.body().then(
      () => finishProjectRead(response.request(), "body", response.status()),
      () =>
        finishProjectRead(
          response.request(),
          response.request().failure() ? "cancelled" : "body_error",
          response.status(),
        ),
    );
  });
  page.on("requestfailed", (request) =>
    finishProjectRead(request, "cancelled"),
  );
  async function settleProjectReads() {
    while (pendingProjectReads.size > 0)
      await Promise.all(
        [...pendingProjectReads.values()].map((read) => read.settled),
      );
  }
  async function waitForProjectReadBodies(
    captureOffset: number,
    routePatterns: readonly string[],
  ) {
    while (true) {
      const events = (activeSplitReadEvents ?? []).slice(captureOffset);
      const successful = new Set(
        events
          .filter((event) => event.event === "body" && event.status === 200)
          .map((event) => event.route_pattern),
      );
      const failed = events.find(
        (event) =>
          event.event === "body_error" ||
          (event.event === "body" && event.status !== 200),
      );
      if (failed)
        throw new Error(
          `A project read body failed for ${failed.route_pattern}.`,
        );
      if (routePatterns.every((pattern) => successful.has(pattern))) return;
      await new Promise<void>((resolve) => {
        const notify = () => {
          sourceReadEventWaiters.delete(notify);
          resolve();
        };
        sourceReadEventWaiters.add(notify);
      });
    }
  }

  await caseButton("case-2").click();
  await expect(
    page.getByRole("heading", { name: "case-2", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit input" })).toBeEnabled();
  await expect(
    page.getByText("Loading selected example…", { exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText("Loading labels…", { exact: true })).toHaveCount(
    0,
  );
  await settleProjectReads();
  await page.getByRole("button", { name: "Remove case" }).click();
  let releaseRemove!: () => void;
  let reportRemoveStarted!: () => void;
  const removeGate = new Promise<void>((resolve) => {
    releaseRemove = resolve;
  });
  const removeStarted = new Promise<void>((resolve) => {
    reportRemoveStarted = resolve;
  });
  let heldRemove = false;
  await page.route("**/datasets/*/cases/case-2", async (route) => {
    if (route.request().method() === "DELETE") {
      removeBodies.push(
        route.request().postDataJSON() as Record<string, unknown>,
      );
      if (!heldRemove) {
        heldRemove = true;
        reportRemoveStarted();
        await removeGate;
      }
    }
    await route.continue();
  });
  await page
    .getByRole("button", { name: "Remove case", exact: true })
    .last()
    .click();
  await removeStarted;
  const caseTwoResponse = await page.request.get(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/case-2`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  await recordDirectApiFailure(
    caseTwoResponse,
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/case-2`,
  );
  expect(caseTwoResponse.status()).toBe(200);
  const caseTwoEnvelope: {
    schema_version: 1;
    data: ApiOperationData<"read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get">;
  } = await caseTwoResponse.json();
  expect(caseTwoEnvelope.schema_version).toBe(1);
  const caseTwo = caseTwoEnvelope.data;
  expect(caseTwo.case.record.id).toBe("case-2");
  const removeConflictWinner = await page.request.put(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/case-2`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
      data: {
        schema_version: 1,
        operation_id: "m10-remove-case-conflict-winner",
        expected_case_etag: caseTwo.case.etag,
        expected_dataset_etag: caseTwo.dataset_etag,
        input_kind: caseTwo.case.record.input_kind,
        input_source: caseTwo.case.record.input_source,
        tags: [...(caseTwo.case.record.tags ?? []), "remove-conflict-winner"],
        split: caseTwo.case.record.split,
        group_id: caseTwo.case.record.group_id,
        derived_from: caseTwo.case.record.derived_from,
        metadata_source: caseTwo.case.record.metadata_source,
      },
    },
  );
  await recordDirectApiFailure(
    removeConflictWinner,
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/case-2`,
  );
  expect(removeConflictWinner.status()).toBe(200);
  releaseRemove();
  await expect(
    page.getByRole("button", { name: "Review current case and dataset" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Review current case and dataset" })
    .click();
  const reapplyRemoveResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/cases/case-2") &&
      response.request().method() === "DELETE",
  );
  await page.getByRole("button", { name: "Reapply reviewed removal" }).click();
  const reapplyRemoveReceipt = await reapplyRemoveResponse;
  expect(reapplyRemoveReceipt.status()).toBe(200);
  const reapplyRemoveEnvelope: {
    schema_version: 1;
    data: ApiOperationData<"delete_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__delete">;
  } = await reapplyRemoveReceipt.json();
  expect(reapplyRemoveEnvelope.schema_version).toBe(1);
  expect(reapplyRemoveEnvelope.data).toMatchObject({
    schema_version: 1,
    replayed: false,
    case: null,
  });
  expect(reapplyRemoveEnvelope.data.dataset.record.id).toBe(datasetId);
  const removeReceiptDatasetEtag = reapplyRemoveEnvelope.data.dataset.etag;
  expect(removeBodies).toHaveLength(2);
  expect(removeBodies[1].operation_id).not.toBe(removeBodies[0].operation_id);
  expect(removeBodies[1].expected_case_etag).not.toBe(
    removeBodies[0].expected_case_etag,
  );
  await page.unroute("**/datasets/*/cases/case-2");
  await expect(page.getByRole("region", { name: /^Cases in / })).toBeVisible();
  await expect(caseButton("case-2")).toHaveCount(0);
  await expect(caseButton("case-1")).toBeVisible();
  await expect(page.getByText("Loading labels…", { exact: true })).toHaveCount(
    0,
  );
  await expect(
    page.getByText("Loading selected example…", { exact: true }),
  ).toHaveCount(0);
  await caseButton("case-1").click();
  await expect(
    page.getByRole("heading", { name: "case-1", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Complete example input source", { exact: true }),
  ).toHaveText('{"case":1,"changed":true}');
  await expect(page.getByRole("button", { name: "Edit input" })).toBeEnabled();
  await expect(
    page.getByText("Loading selected example…", { exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText("Loading labels…", { exact: true })).toHaveCount(
    0,
  );
  await settleProjectReads();
  const readdCaseTwo = await page.request.post(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
      data: {
        schema_version: 1,
        operation_id: "m10-readd-case-two-after-conflict-test",
        expected_dataset_etag: removeReceiptDatasetEtag,
        case_id: "case-2",
        input_kind: caseTwo.case.record.input_kind,
        input_source: caseTwo.case.record.input_source,
        tags: caseTwo.case.record.tags,
        split: caseTwo.case.record.split,
        group_id: caseTwo.case.record.group_id,
        derived_from: caseTwo.case.record.derived_from,
        metadata_source: caseTwo.case.record.metadata_source,
      },
    },
  );
  await recordDirectApiFailure(
    readdCaseTwo,
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases`,
  );
  expect(readdCaseTwo.status()).toBe(200);
  const readdCaseTwoEnvelope: {
    schema_version: 1;
    data: ApiOperationData<"add_case_api_v1_projects__registration_id__datasets__dataset_id__cases_post">;
  } = await readdCaseTwo.json();
  expect(readdCaseTwoEnvelope.schema_version).toBe(1);
  expect(readdCaseTwoEnvelope.data.case?.record.id).toBe("case-2");
  expect(readdCaseTwoEnvelope.data.case?.record.dataset_id).toBe(datasetId);
  expect(readdCaseTwoEnvelope.data.replayed).toBe(false);

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
  await recordDirectApiFailure(
    removed,
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/case-1`,
  );
  expect(removed.status()).toBe(200);
  const removedEnvelope: {
    schema_version: 1;
    data: ApiOperationData<"delete_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__delete">;
  } = await removed.json();
  expect(removedEnvelope.schema_version).toBe(1);
  expect(removedEnvelope.data.case).toBeNull();
  const removedDatasetEtag = removedEnvelope.data.dataset.etag;
  const readded = await page.request.post(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
      data: {
        schema_version: 1,
        operation_id: "m10-readd-case-one",
        expected_dataset_etag: removedDatasetEtag,
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
  await recordDirectApiFailure(
    readded,
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases`,
  );
  expect(readded.status()).toBe(200);
  const readdedEnvelope: {
    schema_version: 1;
    data: ApiOperationData<"add_case_api_v1_projects__registration_id__datasets__dataset_id__cases_post">;
  } = await readded.json();
  expect(readdedEnvelope.schema_version).toBe(1);
  expect(readdedEnvelope.data.case?.record.id).toBe("case-1");
  expect(readdedEnvelope.data.case?.record.dataset_id).toBe(datasetId);
  expect(readdedEnvelope.data.replayed).toBe(false);
  expect(
    (await readCaseOneLabel().then((response) => response.json())).data.label,
  ).toBeNull();

  await enterPhase("External case changes and explicit current review refresh");
  const seedPairReads = [
    page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/seed-1` &&
        response.request().method() === "GET",
    ),
    page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/decisions/${decisionId}/datasets/${datasetId}/labels/seed-1` &&
        response.request().method() === "GET",
    ),
  ];
  await caseButton("seed-1").click();
  const seedPairResponses = await Promise.all(seedPairReads);
  for (const response of seedPairResponses) {
    expect(response.status()).toBe(200);
    await response.body();
  }
  await settleProjectReads();
  await expect(
    page.getByRole("heading", { name: "seed-1", exact: true }),
  ).toBeVisible();
  if (seedCaseSource === undefined)
    throw new Error("The seed case source fixture was not captured.");
  await expect(
    page.getByLabel("Complete example input source", { exact: true }),
  ).toHaveText(seedCaseSource);
  await expect(page.getByRole("button", { name: "Edit input" })).toBeEnabled();
  await expect(
    page.getByText("Loading selected example…", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("region", { name: "Labels unavailable" }),
  ).toBeVisible();
  await settleProjectReads();

  const labelsUnavailable = page.getByRole("region", {
    name: "Labels unavailable",
  });
  const refreshedDatasetReadResponses = [
    page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/datasets/${datasetId}` &&
        response.request().method() === "GET",
    ),
    page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases` &&
        response.request().method() === "GET",
    ),
    page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/decisions/${decisionId}/datasets/${datasetId}/labels` &&
        response.request().method() === "GET",
    ),
  ];
  await labelsUnavailable
    .getByRole("button", { name: "Reload labels" })
    .click();
  const refreshedDatasetReads = await Promise.all(
    refreshedDatasetReadResponses,
  );
  await expect(labelsUnavailable).toHaveCount(0);
  await expect(
    page.getByRole("table", {
      name: `Expected answers for ${decisionName}`,
    }),
  ).toBeVisible();
  await expect(page.getByText("Loading labels…", { exact: true })).toHaveCount(
    0,
  );
  await settleProjectReads();
  expect(refreshedDatasetReads).toHaveLength(3);
  for (const response of refreshedDatasetReads) {
    expect(response.status()).toBe(200);
    await response.body();
  }

  const selectedCaseReads = [
    page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/case-1` &&
        response.request().method() === "GET",
    ),
    page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/decisions/${decisionId}/datasets/${datasetId}/labels/case-1` &&
        response.request().method() === "GET",
    ),
  ];
  await caseButton("case-1").click();
  const selectedCaseResponses = await Promise.all(selectedCaseReads);
  for (const response of selectedCaseResponses) {
    expect(response.status()).toBe(200);
    await response.body();
  }
  await expect(
    page.getByRole("heading", { name: "case-1", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Complete example input source", { exact: true }),
  ).toHaveText('{"case":1,"changed":true}');
  await expect(page.getByRole("button", { name: "Edit input" })).toBeEnabled();
  await expect(
    page.getByText("Loading selected example…", { exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText("Loading labels…", { exact: true })).toHaveCount(
    0,
  );
  await settleProjectReads();

  await enterPhase("Grouped server split preview and option-reference impact");
  await page
    .getByRole("button", { name: "Split dataset", exact: true })
    .click();
  const splitPreviewResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/splits/preview") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Preview assignments" }).click();
  const splitPreview = (await (await splitPreviewResponse).json()).data;
  await expect(
    page.getByRole("heading", { name: "Server split preview" }),
  ).toBeVisible();
  await page.locator(".split-preview details summary").click();
  const assignments = await page
    .locator(".split-preview details table tbody tr")
    .evaluateAll((rows) =>
      rows.map(
        (row) =>
          [
            row.querySelector("th")?.textContent?.trim() ?? "",
            row.querySelector("td")?.textContent?.trim() ?? "",
          ] as const,
      ),
    );
  const relatedAssignments = assignments
    .filter(([caseId]) =>
      ["case-1", "case-2", "case-8", "case-9"].includes(caseId),
    )
    .map(([, split]) => split);
  expect(relatedAssignments).toHaveLength(4);
  expect(new Set(relatedAssignments).size).toBe(1);
  await captureScreenshot("split-server-preview.png");
  type SplitCommitData =
    ApiOperationData<"commit_split_api_v1_projects__registration_id__datasets__dataset_id__splits_commit_post">;
  const splitCommitResults: SplitCommitData[] = [];
  let firstSplitCommitStatus: number | undefined;
  let firstSplitCommitAborted = false;
  await page.route("**/splits/commit", async (route) => {
    const response = await route.fetch();
    const result = (await response.json()).data as SplitCommitData;
    splitCommitResults.push(result);
    if (splitCommitResults.length === 1) {
      firstSplitCommitStatus = response.status();
      await route.abort("failed");
      firstSplitCommitAborted = true;
      return;
    }
    await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "Apply split" }).click();
  await expect
    .poll(() => firstSplitCommitAborted, { timeout: 15_000 })
    .toBe(true);
  expect(firstSplitCommitStatus).toBe(200);
  await expect(
    page.getByRole("button", { name: "Retry the same split request" }),
  ).toBeVisible();
  expect(splitCommitBodies).toHaveLength(1);
  expect(splitCommitBodies[0].preview_document_source).toBe(
    splitPreview.preview_document_source,
  );
  await expect(
    page.getByRole("button", { name: "Close", exact: true }),
  ).toBeDisabled();
  const splitHashBeforeRouteAttempt = page.url();
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, `#/p/${registrationId}/d/${decisionId}`);
  const splitUnknownGuard = page.getByRole("dialog", {
    name: "Unsaved changes",
  });
  await expect(splitUnknownGuard).toBeVisible();
  await expect(
    splitUnknownGuard.getByRole("button", {
      name: "Discard changes",
      exact: true,
    }),
  ).toBeDisabled();
  await splitUnknownGuard
    .getByRole("button", { name: "Keep editing", exact: true })
    .click();
  await expect(page).toHaveURL(splitHashBeforeRouteAttempt);
  expect(splitCommitBodies).toHaveLength(1);
  const splitReadPatterns = [
    `/api/v1/projects/${registrationId}/overview`,
    `/api/v1/projects/${registrationId}/datasets/${datasetId}`,
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases`,
    `/api/v1/projects/${registrationId}/decisions/${decisionId}/datasets/${datasetId}/labels`,
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/case-1`,
    `/api/v1/projects/${registrationId}/decisions/${decisionId}/datasets/${datasetId}/labels/case-1`,
  ].map((path) => safeRoutePattern(path));
  recordLateSourceReadProgress = true;
  activeSplitReadEvents = [];
  const splitReadCaptureStart = 0;
  const splitReplayStartedAt = Date.now();
  const splitReplayResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.endsWith("/splits/commit") &&
      response.request().method() === "POST",
    { timeout: 0 },
  );
  void splitReplayResponse.catch(() => undefined);
  await page
    .getByRole("button", { name: "Retry the same split request" })
    .click();
  const splitReplayReceipt = await splitReplayResponse;
  expect(splitReplayReceipt.status()).toBe(200);
  await splitReplayReceipt.body();
  const splitReadinessStartedAt = Date.now();
  actionTimings.push({
    action: "split_replay",
    stage: "receipt",
    elapsed_ms: splitReadinessStartedAt - splitReplayStartedAt,
  });
  const splitReadinessTimeout = new Error(
    "Split refresh did not reach a settled ready state.",
  );
  let splitRefreshReadinessTimer: ReturnType<typeof setTimeout> | undefined;
  const boundedSplitReadiness = new Promise<never>((_, reject) => {
    splitRefreshReadinessTimer = setTimeout(() => {
      reject(splitReadinessTimeout);
    }, 15_000);
  });
  async function captureSplitReadinessFacts() {
    const [
      editEnabled,
      optionAEnabled,
      selectedLoading,
      labelsLoading,
      selectionReviewNoticePresent,
      errorPresent,
      savedRefreshPresent,
    ] = await Promise.all([
      page
        .getByRole("button", { name: "Edit input" })
        .isEnabled({ timeout: 200 })
        .catch(() => false),
      page
        .getByRole("checkbox", { name: "Option A" })
        .isEnabled({ timeout: 200 })
        .catch(() => false),
      page
        .getByText("Loading selected example…", { exact: true })
        .count()
        .then((count) => count > 0)
        .catch(() => false),
      page
        .getByText("Loading labels…", { exact: true })
        .count()
        .then((count) => count > 0)
        .catch(() => false),
      page
        .getByRole("region", { name: "Review selected context" })
        .count()
        .then((count) => count > 0)
        .catch(() => false),
      page
        .getByRole("alert")
        .count()
        .then((count) => count > 0)
        .catch(() => false),
      page
        .getByRole("region", { name: "Saved changes awaiting refresh" })
        .count()
        .then((count) => count > 0)
        .catch(() => false),
    ]);
    return {
      edit_enabled: editEnabled,
      option_a_enabled: optionAEnabled,
      selected_loading: selectedLoading,
      labels_loading: labelsLoading,
      selection_review_notice_present: selectionReviewNoticePresent,
      error_present: errorPresent,
      saved_refresh_present: savedRefreshPresent,
      pending_route_categories: [...pendingSourceReadCategories],
    };
  }
  void boundedSplitReadiness.catch(() => undefined);
  await expect
    .poll(() => splitCommitResults.length, { timeout: 15_000 })
    .toBe(2);
  await expect(
    page.getByRole("status").filter({ hasText: "Saved new dataset revision" }),
  ).toBeVisible();
  expect(splitCommitBodies[1]).toEqual(splitCommitBodies[0]);
  expect(splitCommitResults.map((result) => result.replayed)).toEqual([
    false,
    true,
  ]);
  const splitReceipt = splitCommitResults[1];
  const splitSnapshot = splitReceipt.snapshot;
  const expectedSplitByCase = Object.fromEntries(
    splitPreview.preview.assignments,
  );
  const savedSplitByCase = Object.fromEntries(
    splitSnapshot.cases.map(({ id, split }) => [id, split]),
  );
  expect(savedSplitByCase).toEqual(expectedSplitByCase);
  await page.unroute("**/splits/commit");
  await page.getByRole("button", { name: "Close", exact: true }).click();

  const casesRegion = page.getByRole("region", { name: /^Cases in / });
  const readVisibleCaseSplits = () =>
    casesRegion.locator("tbody tr").evaluateAll((rows) =>
      Object.fromEntries(
        rows.map((row) => {
          const cells = row.querySelectorAll("td");
          return [
            cells.item(0)?.querySelector("button")?.textContent?.trim() ?? "",
            cells.item(2)?.textContent?.trim() ?? "",
          ];
        }),
      ),
    );
  const splitReadyExpect = expect.configure({ timeout: 15_000 });
  const splitRefreshReadiness = (async () => {
    await waitForProjectReadBodies(splitReadCaptureStart, splitReadPatterns);
    await splitReadyExpect(casesRegion).toBeVisible();
    await splitReadyExpect
      .poll(readVisibleCaseSplits)
      .toEqual(expectedSplitByCase);
    await splitReadyExpect(
      page.getByRole("heading", { name: "case-1", exact: true }),
    ).toBeVisible();
    await splitReadyExpect(
      page.getByLabel("Complete example input source", { exact: true }),
    ).toHaveText('{"case":1,"changed":true}');
    await splitReadyExpect(
      page.getByRole("button", { name: "Edit input" }),
    ).toBeEnabled();
    await splitReadyExpect(
      page.getByRole("heading", { name: "Expected answers" }),
    ).toBeVisible();
    await splitReadyExpect(
      page.getByRole("checkbox", { name: "Option A" }),
    ).toBeEnabled();
    await splitReadyExpect(
      page.getByRole("region", { name: "Saved changes awaiting refresh" }),
    ).toHaveCount(0);
    await splitReadyExpect(
      page.getByText("Loading selected example…", { exact: true }),
    ).toHaveCount(0);
    await splitReadyExpect(
      page.getByText("Loading labels…", { exact: true }),
    ).toHaveCount(0);
    await settleProjectReads();
  })();
  void splitRefreshReadiness.catch(() => undefined);
  try {
    await Promise.race([splitRefreshReadiness, boundedSplitReadiness]);
  } catch (error) {
    try {
      splitReadinessFacts = await captureSplitReadinessFacts();
      await recordProgress();
    } catch {
      // Keep the readiness failure if collecting or saving facts fails.
    }
    throw error;
  } finally {
    if (splitRefreshReadinessTimer !== undefined)
      clearTimeout(splitRefreshReadinessTimer);
  }
  actionTimings.push({
    action: "split_replay",
    stage: "readiness",
    elapsed_ms: Date.now() - splitReadinessStartedAt,
  });
  await recordProgress();
  activeSplitReadEvents = undefined;

  const splitDatasetRead = await page.request.get(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  await expectDirectDataEnvelope(
    splitDatasetRead,
    new URL(splitDatasetRead.url()).pathname,
  );
  const splitDatasetData = (await splitDatasetRead.json()).data;
  expect(splitDatasetData.record).toEqual(splitReceipt.dataset.record);
  expect(splitDatasetData.etag).toBe(splitReceipt.dataset.etag);
  const casesAfterSplitReplay = await page.request.get(
    `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases?limit=100`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  await expectDirectDataEnvelope(
    casesAfterSplitReplay,
    new URL(casesAfterSplitReplay.url()).pathname,
  );
  expect((await casesAfterSplitReplay.json()).data.total).toBe(
    String(splitReceipt.snapshot.cases.length),
  );

  const caseOneBeforeSeedSaveResponse = await readCaseOne();
  const caseOneBeforeSeedSave: ApiOperationData<"read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get"> =
    (await caseOneBeforeSeedSaveResponse.json()).data;
  const caseOneLabelBeforeSeedSaveResponse = await readCaseOneLabel();
  const caseOneLabelBeforeSeedSave: ApiOperationData<"read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get"> =
    (await caseOneLabelBeforeSeedSaveResponse.json()).data;

  const seedSelectionResponses = [
    page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/seed-1` &&
        response.request().method() === "GET",
      { timeout: 0 },
    ),
    page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/decisions/${decisionId}/datasets/${datasetId}/labels/seed-1` &&
        response.request().method() === "GET",
      { timeout: 0 },
    ),
  ];
  for (const response of seedSelectionResponses)
    void response.catch(() => undefined);
  await caseButton("seed-1").click();
  const [seedCaseResponse, seedLabelResponse] = await Promise.all(
    seedSelectionResponses,
  );
  for (const response of [seedCaseResponse, seedLabelResponse]) {
    expect(response.status()).toBe(200);
    await response.body();
  }
  const selectedSeedCase: ApiOperationData<"read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get"> =
    (await seedCaseResponse.json()).data;
  const selectedSeedHeading = page.getByRole("heading", {
    name: "seed-1",
    exact: true,
  });
  const selectedSeedSource = page.getByLabel("Complete example input source", {
    exact: true,
  });
  const selectedSeedOptionA = page.getByRole("checkbox", {
    name: "Option A",
  });
  const selectedSeedOptionB = page.getByRole("checkbox", {
    name: "Option B",
  });
  await expect
    .poll(async () => {
      const [
        headingCount,
        displayedSource,
        editEnabled,
        optionAEnabled,
        optionBEnabled,
        selectedLoadingCount,
        labelsLoadingCount,
      ] = await Promise.all([
        selectedSeedHeading.count(),
        selectedSeedSource.textContent().catch(() => null),
        page
          .getByRole("button", { name: "Edit input" })
          .isEnabled({ timeout: 200 })
          .catch(() => false),
        selectedSeedOptionA.isEnabled({ timeout: 200 }).catch(() => false),
        selectedSeedOptionB.isEnabled({ timeout: 200 }).catch(() => false),
        page.getByText("Loading selected example…", { exact: true }).count(),
        page.getByText("Loading labels…", { exact: true }).count(),
      ]);
      return (
        headingCount === 1 &&
        displayedSource === selectedSeedCase.case.record.input_source &&
        editEnabled &&
        optionAEnabled &&
        optionBEnabled &&
        selectedLoadingCount === 0 &&
        labelsLoadingCount === 0
      );
    })
    .toBe(true);
  await settleProjectReads();
  await page.getByRole("checkbox", { name: "Option A" }).check();
  await page.getByRole("checkbox", { name: "Option B" }).check();
  const applicableLabelSave = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        `/api/v1/projects/${registrationId}/decisions/${decisionId}/datasets/${datasetId}/labels/batch` &&
      response.request().method() === "POST",
    { timeout: 15_000 },
  );
  await page.getByRole("button", { name: "Save expected answer" }).click();
  const applicableLabelReceipt = await applicableLabelSave;
  expect(applicableLabelReceipt.status()).toBe(200);
  await applicableLabelReceipt.body();
  const applicableLabelReceiptData: ApiOperationData<"batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post"> =
    (await applicableLabelReceipt.json()).data;
  expect(applicableLabelReceiptData.changes).toHaveLength(1);
  expect(applicableLabelReceiptData.changes[0]).toMatchObject({
    action: "set",
    case_id: "seed-1",
    dataset_id: datasetId,
    decision_id: decisionId,
    label: {
      acceptable_option_ids: ["option-a", "option-b"],
      provenance: "human",
    },
  });
  await expect(page.getByRole("button", { name: "Dispute label" })).toBeEnabled(
    { timeout: 15_000 },
  );
  await expect(
    page.getByRole("status").filter({ hasText: /^Applicable · human$/ }),
  ).toBeVisible({ timeout: 15_000 });
  await settleProjectReads();
  const seedLabelAfterSaveResponse = await readSeedLabel();
  const seedLabelAfterSave: ApiOperationData<"read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get"> =
    (await seedLabelAfterSaveResponse.json()).data;
  expect(seedLabelAfterSave.status).toBe("applicable");
  expect(seedLabelAfterSave.reasons).toEqual([]);
  expect(seedLabelAfterSave.label).toMatchObject({
    acceptable_option_ids: ["option-a", "option-b"],
    provenance: "human",
  });
  expect(seedLabelAfterSave.label?.input_hash).toBe(
    seedLabelAfterSave.review.input_hash,
  );

  const caseOneAfterSeedSaveResponse = await readCaseOne();
  const caseOneAfterSeedSave: ApiOperationData<"read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get"> =
    (await caseOneAfterSeedSaveResponse.json()).data;
  const caseOneLabelAfterSeedSaveResponse = await readCaseOneLabel();
  const caseOneLabelAfterSeedSave: ApiOperationData<"read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get"> =
    (await caseOneLabelAfterSeedSaveResponse.json()).data;
  expect(caseOneAfterSeedSave.case.record.input_source).toBe(
    caseOneBeforeSeedSave.case.record.input_source,
  );
  expect(caseOneLabelAfterSeedSave.label).toEqual(
    caseOneLabelBeforeSeedSave.label,
  );
  expect(caseOneLabelAfterSeedSave.review.input_hash).toBe(
    caseOneLabelBeforeSeedSave.review.input_hash,
  );
  await page
    .getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: decisionName, exact: true })
    .click();
  await page.getByRole("button", { name: "+ Add option" }).click();
  const optionNamesForRemoval = page.getByLabel("Option name");
  await expect(optionNamesForRemoval).toHaveCount(3);
  await optionNamesForRemoval.nth(2).fill("Option C");
  const removalSetupTransform = page.waitForResponse(
    (response) =>
      response.url().endsWith("/editor-transform") &&
      response.request().method() === "POST",
  );
  const removalSetupSave = page.waitForResponse(
    (response) =>
      response.url().endsWith("/draft") &&
      response.request().method() === "PUT",
  );
  await optionNamesForRemoval.nth(2).press("Tab");
  const [removalSetupTransformResponse, removalSetupSaveResponse] =
    await Promise.all([removalSetupTransform, removalSetupSave]);
  expect(removalSetupTransformResponse.status()).toBe(200);
  expect(removalSetupSaveResponse.status()).toBe(200);
  await Promise.all([
    removalSetupTransformResponse.body(),
    removalSetupSaveResponse.body(),
  ]);

  const referencedImpactResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/editor-transform") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Remove option Option A" }).click();
  const referencedImpactReceipt = await referencedImpactResponse;
  expect(referencedImpactReceipt.status()).toBe(200);
  await referencedImpactReceipt.body();
  const referencedImpact = page
    .getByRole("dialog", { name: "Remove Option A?" })
    .getByRole("list", { name: "Affected references" });
  await expect(referencedImpact).toContainText("seed-1");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Cancel", exact: true })
    .click();

  const unreferencedImpactResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/editor-transform") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Remove option Option C" }).click();
  const unreferencedImpactReceipt = await unreferencedImpactResponse;
  expect(unreferencedImpactReceipt.status()).toBe(200);
  await unreferencedImpactReceipt.body();
  const unreferencedImpact = page.getByRole("dialog", {
    name: "Remove Option C?",
  });
  await expect(unreferencedImpact).toContainText(
    "The service reported no affected references.",
  );
  await unreferencedImpact
    .getByRole("button", { name: "Remove option from draft" })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Draft saved" }),
  ).toBeVisible();
  await expect(page.getByLabel("Option name")).toHaveCount(2);

  const uncomputableImpactResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/editor-transform") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Remove option Option A" }).click();
  const uncomputableImpactReceipt = await uncomputableImpactResponse;
  expect(uncomputableImpactReceipt.status()).toBe(200);
  await uncomputableImpactReceipt.body();
  const uncomputableImpact = page.getByRole("dialog", {
    name: "Remove Option A?",
  });
  await expect(uncomputableImpact).toContainText(
    "The service could not compute affected references for this invalid definition.",
  );
  await expect(
    uncomputableImpact
      .getByRole("list", { name: "Definition validation advice" })
      .locator("code")
      .first(),
  ).toBeVisible();
  await expect(
    uncomputableImpact.getByRole("list", { name: "Affected references" }),
  ).toHaveCount(0);
  await uncomputableImpact
    .getByRole("button", { name: "Cancel", exact: true })
    .click();

  await enterPhase("Decision archive recovery and provider safety controls");
  await page.getByRole("button", { name: "Archive decision" }).click();
  const archiveDialog = page.getByRole("dialog", {
    name: "Archive this decision?",
  });
  await expect(archiveDialog).toBeVisible();
  const archiveBodies: Array<Record<string, unknown>> = [];
  let firstArchiveStatus: number | undefined;
  await page.route(`**/decisions/${decisionId}/archive`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    archiveBodies.push(
      route.request().postDataJSON() as Record<string, unknown>,
    );
    const response = await route.fetch();
    if (archiveBodies.length === 1) {
      firstArchiveStatus = response.status();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "{}",
      });
      return;
    }
    await route.fulfill({ response });
  });
  await archiveDialog
    .getByRole("button", { name: "Archive decision", exact: true })
    .click();
  await expect.poll(() => firstArchiveStatus, { timeout: 15_000 }).toBe(200);
  await expect(
    archiveDialog.getByRole("button", { name: "Retry same archive action" }),
  ).toBeVisible();
  const archiveReplayResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/archive") &&
      response.request().method() === "POST",
  );
  await archiveDialog
    .getByRole("button", { name: "Retry same archive action" })
    .click();
  const archivedResponse = await archiveReplayResponse;
  expect(archivedResponse.status()).toBe(200);
  await archivedResponse.body();
  const archivedResult = (await archivedResponse.json())
    .data as ApiOperationData<"archiveDecision">;
  expect(archivedResult.record.id).toBe(decisionId);
  expect(archivedResult.record.archived).toBe(true);
  await expect(
    archiveDialog.getByRole("button", { name: "Retry same archive action" }),
  ).toHaveCount(0);
  await expect(archiveDialog).toHaveCount(0);
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible();
  expect(archiveBodies).toHaveLength(2);
  expect(archiveBodies[1]).toEqual(archiveBodies[0]);
  await page.unroute(`**/decisions/${decisionId}/archive`);
  const archivedRow = page
    .getByRole("table", { name: "Archived decisions" })
    .getByRole("row", { name: new RegExp(decisionName) });
  await expect(archivedRow).toBeVisible();
  await settleProjectReads();
  const retainedRevisions = await page.request.get(
    `/api/v1/projects/${registrationId}/decisions/${decisionId}/revisions?limit=50`,
    {
      headers: { Origin: origin, "X-Deykit-Capability": capability as string },
    },
  );
  await expectDirectDataEnvelope(
    retainedRevisions,
    new URL(retainedRevisions.url()).pathname,
  );
  const retainedRevisionIds = (await retainedRevisions.json()).data.items.map(
    (item: { revision: { record: { id: string } } }) => item.revision.record.id,
  );
  expect(new Set(retainedRevisionIds).size).toBe(expectedRevisionIds.length);
  expect([...retainedRevisionIds].sort()).toEqual(
    [...expectedRevisionIds].sort(),
  );
  await archivedRow
    .getByRole("button", { name: "Restore", exact: true })
    .click();
  await expect(
    page.getByRole("table", { name: "Project decisions" }),
  ).toContainText(decisionName);

  await page
    .getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: "Providers", exact: true })
    .click();
  await expect(page.getByRole("heading", { name: "Providers" })).toBeVisible();
  await page.getByRole("button", { name: "Add provider profile" }).click();
  await expect(
    page.getByRole("heading", { name: "New profile" }),
  ).toBeVisible();
  await expect(page.getByLabel("Adapter")).toHaveValue("jev");
  await page.getByLabel("Requested model ID").fill("jev-latest");
  await page
    .getByLabel("Destination")
    .fill("https://api.typesafe.ai/v1/systemone");
  const providerProfileSave = page.waitForResponse(
    (response) => {
      const pathname = new URL(response.url()).pathname;
      return (
        response.request().method() === "PUT" &&
        pathname.startsWith(`/api/v1/projects/${registrationId}/providers/`) &&
        /^\/api\/v1\/projects\/[^/]+\/providers\/[^/]+$/.test(pathname)
      );
    },
    { timeout: 15_000 },
  );
  await page.getByRole("button", { name: "Save profile" }).click();
  const providerProfileReceipt = await providerProfileSave;
  expect(providerProfileReceipt.status()).toBe(200);
  await providerProfileReceipt.body();
  await expect(
    page.getByText("Not configured · Unavailable", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText("Explicit network check · 0 inference calls."),
  ).toBeVisible();
  const environmentName = "M08_FAKE_ENV";
  await page.getByLabel("Environment variable name").fill(environmentName);
  const environmentCredentialResponse = page.waitForResponse(
    (response) => {
      const pathname = new URL(response.url()).pathname;
      return (
        response.request().method() === "POST" &&
        pathname.startsWith(`/api/v1/projects/${registrationId}/providers/`) &&
        pathname.endsWith("/credential-environment")
      );
    },
    { timeout: 15_000 },
  );
  await page
    .getByRole("button", { name: "Attach environment reference" })
    .click();
  const environmentCredentialReceipt = await environmentCredentialResponse;
  expect(environmentCredentialReceipt.status()).toBe(200);
  await environmentCredentialReceipt.body();
  await expect(page.getByText(environmentName)).toHaveCount(0);
  await expect(
    page.getByText("Configured · Available", { exact: false }),
  ).toBeVisible();
  const modelListResponse = page.waitForResponse(
    (response) => {
      const pathname = new URL(response.url()).pathname;
      return (
        response.request().method() === "POST" &&
        pathname.startsWith(`/api/v1/projects/${registrationId}/providers/`) &&
        pathname.endsWith("/models")
      );
    },
    { timeout: 15_000 },
  );
  await page.getByRole("button", { name: "Refresh model list" }).click();
  const modelListReceipt = await modelListResponse;
  expect(modelListReceipt.status()).toBe(200);
  await modelListReceipt.body();
  await expect(
    page.getByText("fake-offline-model", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("1 models returned · network checked · 0 inference calls"),
  ).toBeVisible();

  const providerProfilesResponse = await page.request.get(
    `/api/v1/projects/${registrationId}/providers?limit=100`,
    { headers: authorizedHeaders },
  );
  await expectDirectDataEnvelope(
    providerProfilesResponse,
    new URL(providerProfilesResponse.url()).pathname,
  );
  const configuredProvider = (
    await providerProfilesResponse.json()
  ).data.items.find(
    (item: { adapter: string; requested_model: string }) =>
      item.adapter === "jev" && item.requested_model === "jev-latest",
  );
  expect(configuredProvider).toBeTruthy();
  const credentialValue = "synthetic-installed-os-credential-never-real";
  const credentialBodies: Array<Record<string, unknown>> = [];
  let firstCredentialStatus: number | undefined;
  await page.route(
    `**/providers/${configuredProvider.id}/credential-os-store`,
    async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      credentialBodies.push(
        route.request().postDataJSON() as Record<string, unknown>,
      );
      const response = await route.fetch();
      if (credentialBodies.length === 1) {
        firstCredentialStatus = response.status();
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: "{}",
        });
        return;
      }
      await route.fulfill({ response });
    },
  );
  const secretInput = page.getByLabel(
    "Store a credential in the operating system",
  );
  await secretInput.fill(credentialValue);
  await page.getByRole("button", { name: "Store credential" }).click();
  await expect.poll(() => firstCredentialStatus, { timeout: 15_000 }).toBe(200);
  await expect(
    page.getByRole("button", { name: "Retry the same credential request" }),
  ).toBeVisible();
  await expect
    .poll(async () => (await secretInput.inputValue()) === "")
    .toBe(true);
  await expect(secretInput).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Store credential" }),
  ).toBeDisabled();
  expect(
    !(await page.locator("body").innerText()).includes(credentialValue),
  ).toBe(true);
  const credentialReplayResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/credential-os-store") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Retry the same credential request" })
    .click();
  const credentialResponse = await credentialReplayResponse;
  expect(credentialResponse.status()).toBe(200);
  await credentialResponse.body();
  const credentialResult = (await credentialResponse.json())
    .data as ApiOperationData<"setOSStoreCredential">;
  await expect(
    page.getByRole("button", { name: "Retry the same credential request" }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Configured · Available", { exact: false }),
  ).toBeVisible();
  expect(firstCredentialStatus).toBe(200);
  expect(credentialBodies).toHaveLength(2);
  const originalCredentialBody = credentialBodies[0];
  const replayedCredentialBody = credentialBodies[1];
  expect(credentialResult.operation_id).toBe(
    originalCredentialBody.operation_id,
  );
  expect(credentialResult.replayed).toBe(true);
  expect(credentialResult.profile.id).toBe(configuredProvider.id);
  const originalCredential = originalCredentialBody.credential_value;
  const replayedCredential = replayedCredentialBody.credential_value;
  expect(
    typeof originalCredential === "string" &&
      typeof replayedCredential === "string" &&
      originalCredential === replayedCredential &&
      originalCredential === credentialValue,
  ).toBe(true);
  const nonSecretCredentialFields = (body: Record<string, unknown>) =>
    Object.fromEntries(
      Object.entries(body).filter(([field]) => field !== "credential_value"),
    );
  expect(nonSecretCredentialFields(replayedCredentialBody)).toEqual(
    nonSecretCredentialFields(originalCredentialBody),
  );
  expect(
    !(await page.locator("body").innerText()).includes(credentialValue),
  ).toBe(true);
  await page.unroute(
    `**/providers/${configuredProvider.id}/credential-os-store`,
  );
  await captureScreenshot("provider-setup.png");

  await enterPhase(
    "Demo fixture profile safety and authored binding verification",
  );
  await page
    .getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: "Fixtures", exact: true })
    .click();
  await expect(page.getByRole("heading", { name: "Fixtures" })).toBeVisible();
  await captureScreenshot("fixture-setup.png");

  // Inspect the packaged authored fixture through the installed UI and API.
  // The test never invokes provider networking or requests raw-source display.
  await page.getByRole("button", { name: "Projects", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Welcome to deykit." }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Try support demo", exact: true })
    .click();
  const fixtureDemoPath = testInfo.outputPath("fixture-support-demo");
  await page.getByLabel("Project folder path").fill(fixtureDemoPath);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Try support demo", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Sandbox", exact: true }),
  ).toBeVisible();
  const fixtureRegistrationId = new URL(page.url()).hash.match(
    /^#\/p\/([A-Za-z0-9_-]+)/,
  )?.[1] as string;
  const fixtureHeaders = {
    Origin: origin,
    "X-Deykit-Capability": capability as string,
  };
  const fixtureProvidersResponse = await page.request.get(
    `/api/v1/projects/${fixtureRegistrationId}/providers?limit=100`,
    { headers: fixtureHeaders },
  );
  await expectDirectDataEnvelope(
    fixtureProvidersResponse,
    new URL(fixtureProvidersResponse.url()).pathname,
  );
  const fixtureProvider = (
    await fixtureProvidersResponse.json()
  ).data.items.find((item: { adapter: string }) => item.adapter === "fixture");
  expect(fixtureProvider).toMatchObject({
    requested_model: expect.stringMatching(/^authored-/),
    destination: "fixture:jev-choice",
    evidence_mode: "authored_fixture",
  });
  const fixturePage = await page.request.get(
    `/api/v1/projects/${fixtureRegistrationId}/fixtures?limit=50`,
    { headers: fixtureHeaders },
  );
  await expectDirectDataEnvelope(
    fixturePage,
    new URL(fixturePage.url()).pathname,
  );
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
  await page
    .getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: "Providers", exact: true })
    .click();
  await expect(page.getByRole("heading", { name: "Providers" })).toBeVisible();
  await page
    .getByRole("button", { name: fixtureProvider.id, exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Authored fixture profile" }),
  ).toBeVisible();
  await expect(page.locator(".fixture-provider")).toContainText(
    fixtureProvider.requested_model,
  );
  await expect(page.getByLabel("Environment variable name")).toHaveCount(0);
  await expect(
    page.getByLabel("Store a credential in the operating system"),
  ).toHaveCount(0);
  await expect(page.getByLabel("Destination")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Refresh model list" }),
  ).toHaveCount(0);
  await captureScreenshot("fixture-provider-safe-details.png");
  await page.getByRole("button", { name: "Open fixture library" }).click();
  await expect(
    page.getByRole("heading", { name: "Fixture library" }),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: "Fixtures", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Fixture library" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: fixtureSummary.name, exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: fixtureSummary.name, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("table", { name: "Exact authored case bindings" }),
  ).toBeVisible();
  await expect(
    page.getByRole("checkbox", {
      name: "Show exact stored request source text",
    }),
  ).not.toBeChecked();
  const fixtureDetail = await page.request.get(
    `/api/v1/projects/${fixtureRegistrationId}/fixtures/${fixtureSummary.id}?include_requests=false`,
    { headers: fixtureHeaders },
  );
  await expectDirectDataEnvelope(
    fixtureDetail,
    new URL(fixtureDetail.url()).pathname,
  );
  const hiddenFixtureDetail = (await fixtureDetail.json())
    .data as ApiOperationData<"readFixtureSet">;
  expect(hiddenFixtureDetail.id).toBe(fixtureSummary.id);
  expect(hiddenFixtureDetail.decision_id).toBe(fixtureSummary.decision_id);
  expect(hiddenFixtureDetail.dataset_id).toBe(fixtureSummary.dataset_id);
  expect(hiddenFixtureDetail.model_identity).toBe(
    fixtureSummary.model_identity,
  );
  expect(hiddenFixtureDetail.requests.length === 0).toBe(true);
  await expect(page.getByLabel(/^Stored request source \d+$/)).toHaveCount(0);
  await captureScreenshot("fixture-exact-bindings.png");

  const fixtureRequestsVisibleResponse = page.waitForResponse(
    (response) =>
      response.url().includes(`/fixtures/${fixtureSummary.id}`) &&
      new URL(response.url()).searchParams.get("include_requests") === "true" &&
      response.request().method() === "GET",
  );
  await page
    .getByRole("checkbox", { name: "Show exact stored request source text" })
    .check();
  const fixtureRequestsVisible = await fixtureRequestsVisibleResponse;
  expect(fixtureRequestsVisible.status()).toBe(200);
  const revealedFixture = (await fixtureRequestsVisible.json())
    .data as ApiOperationData<"readFixtureSet">;
  const requestSourceTextboxes = page.getByLabel(/^Stored request source \d+$/);
  const fixtureRequestsHiddenResponse = page.waitForResponse(
    (response) =>
      response.url().includes(`/fixtures/${fixtureSummary.id}`) &&
      new URL(response.url()).searchParams.get("include_requests") ===
        "false" &&
      response.request().method() === "GET",
  );
  let revealedSourceMatches: boolean[] = [];
  let revealedSourcesAreReadOnly: boolean[] = [];
  let fixtureRequestsHidden: Response;
  try {
    expect(revealedFixture.requests.length).toBeGreaterThan(0);
    await expect(requestSourceTextboxes).toHaveCount(
      revealedFixture.requests.length,
    );
    revealedSourceMatches = await Promise.all(
      revealedFixture.requests.map(async (request, index) => {
        const textbox = page.getByLabel(`Stored request source ${index + 1}`, {
          exact: true,
        });
        return (await textbox.inputValue()) === request;
      }),
    );
    revealedSourcesAreReadOnly = await Promise.all(
      revealedFixture.requests.map(async (_, index) =>
        requestSourceTextboxes
          .nth(index)
          .evaluate(
            (element) =>
              element instanceof HTMLTextAreaElement && element.readOnly,
          ),
      ),
    );
  } finally {
    await page
      .getByRole("checkbox", {
        name: "Show exact stored request source text",
      })
      .uncheck();
    fixtureRequestsHidden = await fixtureRequestsHiddenResponse;
  }
  const hiddenFixture = (await fixtureRequestsHidden.json())
    .data as ApiOperationData<"readFixtureSet">;
  expect(revealedSourceMatches.every(Boolean)).toBe(true);
  expect(revealedSourcesAreReadOnly.every(Boolean)).toBe(true);
  expect(fixtureRequestsHidden.status()).toBe(200);
  expect(hiddenFixture.requests.length === 0).toBe(true);
  await expect(requestSourceTextboxes).toHaveCount(0);

  const bindingSources = execFileSync(
    "python",
    [
      "-I",
      "-c",
      "import sys; from pathlib import Path; from deykit.contracts.codec import dump_record, load_record; from deykit.contracts.records import FixtureSet; record = load_record(FixtureSet, (Path(sys.argv[1]) / 'source' / 'fixtures' / (sys.argv[2] + '.json')).read_bytes()); print('\\n'.join(dump_record(binding).decode('utf-8') for binding in record.bindings))",
      fixtureDemoPath,
      fixtureSummary.id,
    ],
    { cwd: fixtureDemoPath, encoding: "utf8" },
  )
    .trimEnd()
    .split("\n");
  await page.getByLabel("Decision").selectOption(fixtureSummary.decision_id);
  await page.getByLabel("Dataset").selectOption(fixtureSummary.dataset_id);
  await page.getByRole("button", { name: "Author fixture set" }).click();
  await page.getByLabel("Fixture set name").fill("Browser authored exact copy");
  await page.getByLabel("Model identity").fill(fixtureSummary.model_identity);
  await page
    .getByLabel("Strict binding source lines")
    .fill(bindingSources.join("\n"));
  const initialFixtureCreate = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        `/api/v1/projects/${fixtureRegistrationId}/fixtures` &&
      response.request().method() === "POST",
    { timeout: 15_000 },
  );
  await page.getByRole("button", { name: "Create authored set" }).click();
  const initialFixtureReceipt = await initialFixtureCreate;
  expect(initialFixtureReceipt.status()).toBe(200);
  await initialFixtureReceipt.body();
  await expect(
    page.getByRole("heading", { name: "Browser authored exact copy" }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("table", { name: "Authored fixture sets" })
      .getByRole("button", {
        name: "Browser authored exact copy",
        exact: true,
      }),
  ).toBeVisible({ timeout: 15_000 });
  const createdFixtureId = await page
    .locator(".fixture-detail code")
    .first()
    .textContent();
  expect(createdFixtureId).toMatch(/^fixture-[A-Za-z0-9_-]+$/);
  const createdFixture = await page.request.get(
    `/api/v1/projects/${fixtureRegistrationId}/fixtures/${createdFixtureId as string}?include_requests=false`,
    { headers: fixtureHeaders },
  );
  await expectDirectDataEnvelope(
    createdFixture,
    new URL(createdFixture.url()).pathname,
  );
  const createdFixtureData = (await createdFixture.json())
    .data as ApiOperationData<"readFixtureSet">;
  expect(createdFixtureData).toMatchObject({
    name: "Browser authored exact copy",
    decision_id: fixtureSummary.decision_id,
    dataset_id: fixtureSummary.dataset_id,
    model_identity: fixtureSummary.model_identity,
  });
  expect(
    createdFixtureData.bindings.map(
      (binding: { request_hash: string }) => binding.request_hash,
    ),
  ).toEqual(
    fixtureSummary.bindings.map(
      (binding: { request_hash: string }) => binding.request_hash,
    ),
  );
  expect(createdFixtureData.requests.length === 0).toBe(true);

  await page.getByRole("button", { name: "Author fixture set" }).click();
  await page
    .getByLabel("Fixture set name")
    .fill("Browser retained fixture request");
  await page.getByLabel("Model identity").fill(fixtureSummary.model_identity);
  await page
    .getByLabel("Strict binding source lines")
    .fill(bindingSources.join("\n"));
  const fixtureCreateBodies: Array<Record<string, unknown>> = [];
  const fixtureCreateResults: ApiOperationData<"createFixtureSet">[] = [];
  let firstFixtureCreateStatus: number | undefined;
  let firstFixtureCreateAborted = false;
  await page.route("**/api/v1/projects/*/fixtures", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    fixtureCreateBodies.push(
      route.request().postDataJSON() as Record<string, unknown>,
    );
    const response = await route.fetch();
    fixtureCreateResults.push(
      (await response.json()).data as ApiOperationData<"createFixtureSet">,
    );
    if (fixtureCreateBodies.length === 1) {
      firstFixtureCreateStatus = response.status();
      await route.abort("failed");
      firstFixtureCreateAborted = true;
      return;
    }
    await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "Create authored set" }).click();
  await expect
    .poll(() => firstFixtureCreateAborted, { timeout: 15_000 })
    .toBe(true);
  expect(firstFixtureCreateStatus).toBe(200);
  await expect(
    page.getByRole("button", { name: "Retry same create" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Close", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: "Examples", exact: true })
    .click();
  const fixtureUnknownGuard = page.getByRole("dialog", {
    name: "Unsaved changes",
  });
  await expect(fixtureUnknownGuard).toBeVisible();
  await expect(
    fixtureUnknownGuard.getByRole("button", {
      name: "Discard changes",
      exact: true,
    }),
  ).toBeDisabled();
  await fixtureUnknownGuard
    .getByRole("button", { name: "Keep editing", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Fixture library" }),
  ).toBeVisible();
  const fixtureReplayResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/fixtures") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Retry same create" }).click();
  const fixtureResponse = await fixtureReplayResponse;
  expect(fixtureResponse.status()).toBe(200);
  await fixtureResponse.body();
  await expect(
    page.getByRole("button", { name: "Retry same create" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Browser retained fixture request" }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("table", { name: "Authored fixture sets" })
      .getByRole("button", {
        name: "Browser retained fixture request",
        exact: true,
      }),
  ).toBeVisible({ timeout: 15_000 });
  expect(fixtureCreateBodies).toHaveLength(2);
  expect(fixtureCreateBodies[1]).toEqual(fixtureCreateBodies[0]);
  expect(fixtureCreateResults).toHaveLength(2);
  expect(fixtureCreateResults.map((result) => result.replayed)).toEqual([
    false,
    true,
  ]);
  expect(fixtureCreateResults[1].operation_id).toBe(
    fixtureCreateResults[0].operation_id,
  );
  expect(fixtureCreateResults[1].fixture.id).toBe(
    fixtureCreateResults[0].fixture.id,
  );
  expect(fixtureCreateResults[1].fixture.name).toBe(
    "Browser retained fixture request",
  );
  await page.unroute("**/api/v1/projects/*/fixtures");

  await enterPhase("Responsive 320px and reduced-motion review");
  await page.setViewportSize({ width: 320, height: 800 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(
    await page.evaluate(
      () => matchMedia("(prefers-reduced-motion: reduce)").matches,
    ),
  ).toBe(true);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual((await page.evaluate(() => window.innerWidth)) + 1);
  await page.keyboard.press("Tab");
  let visibleKeyboardStops = 0;
  for (let index = 0; index < 12; index += 1) {
    const visible = await page.evaluate(() => {
      const active = document.activeElement;
      return (
        active instanceof HTMLElement &&
        active !== document.body &&
        active.getClientRects().length > 0
      );
    });
    expect(visible).toBe(true);
    visibleKeyboardStops += 1;
    await page.keyboard.press("Tab");
  }
  expect(visibleKeyboardStops).toBe(12);
  await captureScreenshot("authoring-narrow-320.png");

  expect(apiResponses.every((url) => new URL(url).origin === origin)).toBe(
    true,
  );
  expect(apiResponses.every((url) => !url.includes(capability as string))).toBe(
    true,
  );
  expect(!page.url().includes(capability as string)).toBe(true);
  expect(
    await page.evaluate(() => [localStorage.length, sessionStorage.length]),
  ).toEqual([0, 0]);
  expect(
    (await page.evaluate(
      () => (document as Document & { cookie: string }).cookie,
    )) === "",
  ).toBe(true);
  await enterPhase("Connected authoring workflow complete");
});
