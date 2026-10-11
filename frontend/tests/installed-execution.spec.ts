import { expect, test } from "@playwright/test";
import type { APIResponse, Response } from "@playwright/test";
import { readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { ApiOperationData } from "../src/api/client";
import { operationMetadata } from "../src/api/generated/operations";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function safeIdentifier(value: unknown): string | null {
  return typeof value === "string" && /^[a-z][a-z0-9_]*$/.test(value)
    ? value
    : null;
}

function safeRoutePattern(pathname: string): string {
  const path = Object.values(operationMetadata)
    .map(({ path }) => path.split("/"))
    .find((template) => {
      const actual = pathname.split("/");
      return (
        actual.length === template.length &&
        template.every((segment, index) =>
          /^\{[a-z_]+\}$/.test(segment)
            ? actual[index] !== ""
            : actual[index] === segment,
        )
      );
    });
  return path
    ? path
        .map((segment) =>
          /^\{[a-z_]+\}$/.test(segment) ? `:${segment.slice(1, -1)}` : segment,
        )
        .join("/")
    : "<unknown-route>";
}

type SafeFailure = {
  route_pattern: string;
  status: number;
  code: string | null;
  reason: string | null;
};

test("installed browser reviews and inspects fixture execution", async ({ page }, testInfo) => {
  page.setDefaultTimeout(12_000);
  const controlDirectory = process.env.DEYKIT_FIXTURE_CONTROL_DIRECTORY;
  if (!controlDirectory)
    throw new Error("The installed driver must set the fixture control directory.");
  const fixtureControlDirectory: string = controlDirectory;

  const phaseIds = [
    "demo_and_fixture_choices",
    "dry_review_and_request_opt_in",
    "unknown_start_and_exact_replay",
    "real_cancellation_and_resume",
    "frozen_result_inspection",
    "mobile_run_inspection",
  ];
  const phaseStatus = new Map<string, "pending" | "running" | "passed" | "failed">(
    phaseIds.map((id) => [id, "pending"]),
  );
  const apiFailures: SafeFailure[] = [];
  const screenshots: string[] = [];
  let activePhase: string | null = null;
  let completed = false;
  let capability: string | undefined;
  let bootstrapOrigin: string | undefined;
  const progressPath = testInfo.outputPath("execution-progress.json");

  async function recordProgress() {
    await writeFile(
      progressPath,
      `${JSON.stringify({
        phases: [...phaseStatus].map(([id, status]) => ({ id, status })),
        active_phase: activePhase,
        api_failures: apiFailures,
      })}\n`,
      "utf8",
    );
  }

  async function enterPhase(id: string) {
    if (!phaseStatus.has(id)) throw new Error("Unknown installed execution phase.");
    if (activePhase) phaseStatus.set(activePhase, "passed");
    activePhase = id;
    phaseStatus.set(id, "running");
    await recordProgress();
  }

  async function recordFailure(response: APIResponse | Response) {
    if (response.status() < 400) return;
    const body: unknown = await response.json().catch(() => undefined);
    const error = isRecord(body) && isRecord(body.error) ? body.error : undefined;
    apiFailures.push({
      route_pattern: safeRoutePattern(new URL(response.url()).pathname),
      status: response.status(),
      code: safeIdentifier(error?.code),
      reason: safeIdentifier(error?.reason),
    });
    await recordProgress();
  }

  async function expectEnvelopeStatus(
    response: APIResponse | Response,
    status: number,
  ) {
    await recordFailure(response);
    expect(response.status()).toBe(status);
    const body: unknown = await response.json();
    expect(
      isRecord(body) && body.schema_version === 1 && isRecord(body.data),
    ).toBe(true);
    return (body as { data: unknown }).data;
  }

  async function expectEnvelope(response: APIResponse | Response) {
    return expectEnvelopeStatus(response, 200);
  }

  async function screenshot(name: string) {
    const path = testInfo.outputPath(name);
    await page.screenshot({ path, fullPage: true });
    await testInfo.attach(name, { path, contentType: "image/png" });
    screenshots.push(name);
    await recordProgress();
  }

  async function bootstrapHeaders() {
    const activeCapability = capability;
    const activeOrigin = bootstrapOrigin;
    if (!activeCapability || !activeOrigin)
      throw new Error("The local browser session was not initialized.");
    return {
      Origin: activeOrigin,
      "X-Deykit-Capability": activeCapability,
    };
  }

  async function dispatchCounts() {
    const value: unknown = JSON.parse(
      await readFile(join(fixtureControlDirectory, "counts.json"), "utf8"),
    );
    expect(isRecord(value)).toBe(true);
    expect(value).toMatchObject({ live_dispatch_calls: 0 });
    return value as {
      fixture_dispatch_calls: number;
      for_case_calls: Record<string, number>;
      live_dispatch_calls: number;
    };
  }

  async function waitForEntered(caseId: string) {
    const enteredPath = join(fixtureControlDirectory, `${caseId}.entered`);
    const deadline = Date.now() + 10_000;
    while (Date.now() < deadline) {
      try {
        await readFile(enteredPath, "utf8");
        return;
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
    }
    throw new Error("The fixture dispatch did not enter the configured barrier.");
  }

  async function waitForRunInactive(runId: string) {
    const deadline = Date.now() + 25_000;
    while (Date.now() < deadline) {
      const response = await page.request.get(
        `/api/v1/projects/${registrationId}/runs/${runId}`,
        { headers: await bootstrapHeaders() },
      );
      if (response.status() === 200) {
        const data: unknown = await expectEnvelope(response);
        const run = data as ApiOperationData<"readRun">;
        if (run.run_id === runId && !run.execution_active) return run;
      } else {
        await recordFailure(response);
        throw new Error("The installed run progress read failed.");
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    throw new Error("The installed run did not become inactive within the bound.");
  }

  const projectPath = testInfo.outputPath("fixture-execution-project");
  let registrationId = "";
  let dispatchCaseId = "";
  let holdPath: string | undefined;
  let initialDispatchCount = 0;

  try {
    await recordProgress();
    await enterPhase("demo_and_fixture_choices");
    const bootstrap = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === "/api/v1/session/bootstrap",
    );
    await page.goto("/");
    const bootstrapResponse = await bootstrap;
    const bootstrapData = await expectEnvelope(bootstrapResponse);
    if (
      !isRecord(bootstrapData) ||
      typeof bootstrapData.capability !== "string"
    )
      throw new Error("The local session capability was not initialized.");
    capability = bootstrapData.capability;
    bootstrapOrigin = new URL(page.url()).origin;

    await page.getByRole("button", { name: "Try support demo" }).click();
    await page.getByLabel("Project folder path").fill(projectPath);
    const demoReceiptPromise = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === "/api/v1/projects/demo" &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Try support demo", exact: true })
      .click();
    const demoData = await expectEnvelope(await demoReceiptPromise);
    if (
      !isRecord(demoData) ||
      !isRecord(demoData.registration) ||
      typeof demoData.registration.registration_id !== "string"
    )
      throw new Error("The fixture demo did not return a project registration.");
    registrationId = demoData.registration.registration_id;
    await expect(page.getByRole("heading", { name: "Sandbox", exact: true })).toBeVisible();

    const fixturesResponse = await page.request.get(
      `/api/v1/projects/${registrationId}/fixtures?limit=50`,
      { headers: await bootstrapHeaders() },
    );
    const fixturePage = (await expectEnvelope(fixturesResponse)) as {
      items: Array<{ id: string; decision_id: string; dataset_id: string }>;
    };
    const fixture = fixturePage.items[0];
    if (!fixture) throw new Error("The support demo has no authored fixture set.");
    const countsBeforeReview = await dispatchCounts();
    initialDispatchCount = countsBeforeReview.fixture_dispatch_calls;
    expect(initialDispatchCount).toBe(0);
    expect(countsBeforeReview.live_dispatch_calls).toBe(0);

    await page
      .getByRole("region", { name: "Project decisions" })
      .getByRole("button", { name: "Content category", exact: true })
      .click();
    await expect(page.getByLabel("Decision source")).toBeVisible();
    await page.getByRole("button", { name: "Run", exact: true }).click();
    const reviewDialog = page.getByRole("dialog", { name: "Review a run" });
    await expect(reviewDialog).toBeVisible();
    await expect(reviewDialog.getByLabel("Fixture set")).toHaveValue(fixture.id);
    await reviewDialog.getByLabel(/^Lifetime attempts per case/).fill("3");
    await reviewDialog.getByLabel("Concurrency").fill("1");
    await reviewDialog.getByLabel(/^Timeout seconds/).fill("5");
    await reviewDialog.getByLabel(/^Deadline seconds/).fill("30");
    await reviewDialog.getByLabel("Rate/overload retries per case (0–1)").fill("0");
    await reviewDialog.getByRole("button", { name: "Review run" }).click();
    await expect(reviewDialog.getByRole("heading", { name: "Server-reviewed context" })).toBeVisible();
    await expect(reviewDialog.getByText("Dry run only. No model calls or run records are created by review.")).toBeVisible();
    const reviewHash = await reviewDialog.locator(".run-review-summary code").first().innerText();
    expect(reviewHash).toMatch(/^[a-f0-9]{64}$/);
    await expect(reviewDialog.locator(".run-case-review pre")).toHaveCount(0);
    const previewData = await page.request.get(
      `/api/v1/projects/${registrationId}/runs?limit=50`,
      { headers: await bootstrapHeaders() },
    );
    expect(previewData.status()).toBe(200);
    expect((await expectEnvelope(previewData) as { items: unknown[] }).items).toHaveLength(0);
    expect((await dispatchCounts()).fixture_dispatch_calls).toBe(initialDispatchCount);

    await screenshot("execution-review.png");
    await enterPhase("dry_review_and_request_opt_in");
    await reviewDialog.getByLabel("Reveal sanitized compiled request sources in this review").check();
    await reviewDialog.getByRole("button", { name: "Review run" }).click();
    await expect(reviewDialog.getByRole("heading", { name: "Server-reviewed context" })).toBeVisible();
    expect(await reviewDialog.locator(".run-review-summary code").first().innerText()).toBe(reviewHash);
    await expect(reviewDialog.locator(".run-case-review pre").first()).toBeVisible();
    await expect(reviewDialog.getByText(/request source was redacted/i)).toHaveCount(0);
    expect((await dispatchCounts()).fixture_dispatch_calls).toBe(initialDispatchCount);

    const reviewCases = await reviewDialog.locator(".run-case-review li").allInnerTexts();
    const eligibleCaseIds = reviewCases
      .map((text) => text.split(" · ")[0])
      .filter((id) => /^ex-\d{3}$/.test(id));
    if (eligibleCaseIds.length === 0)
      throw new Error("The authored demo preview contained no case review rows.");
    dispatchCaseId = eligibleCaseIds[0] ?? "";
    if (!dispatchCaseId) throw new Error("The authored demo case ID was unavailable.");
    holdPath = join(fixtureControlDirectory, `${dispatchCaseId}.hold`);
    await writeFile(holdPath, "hold\n", { flag: "wx" });

    let firstStartStatus = 0;
    const startBodies: Array<Record<string, unknown>> = [];
    let firstRunId: string | undefined;
    await page.route("**/api/v1/projects/*/runs", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      const requestBody = route.request().postDataJSON();
      if (!isRecord(requestBody) || !isRecord(requestBody.request))
        return route.continue();
      const response = await route.fetch();
      if (startBodies.length === 0) {
        startBodies.push(requestBody);
        firstStartStatus = response.status();
        expect(response.status()).toBe(202);
        const receipt: unknown = await response.json();
        expect(isRecord(receipt) && receipt.schema_version === 1).toBe(true);
        const accepted = isRecord(receipt) && isRecord(receipt.data) ? receipt.data : undefined;
        if (typeof accepted?.run_id === "string") firstRunId = accepted.run_id;
        await route.abort("failed");
        return;
      }
      startBodies.push(requestBody);
      await route.fulfill({ response });
    });

    await page.getByRole("button", { name: "Start reviewed run" }).click();
    await expect.poll(() => firstStartStatus).toBe(202);
    await expect(reviewDialog.getByRole("button", { name: "Retry original start request" })).toBeVisible();
    await expect(reviewDialog.getByRole("button", { name: "Start reviewed run" })).toBeDisabled();
    expect(firstRunId).toMatch(/^[A-Za-z0-9_-]+$/);
    const acceptedRunId = firstRunId;
    if (!acceptedRunId) throw new Error("The accepted run ID was not captured.");
    await waitForEntered(dispatchCaseId);
    await screenshot("execution-review-unknown-start.png");

    await enterPhase("unknown_start_and_exact_replay");
    const retryReceipt = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === `/api/v1/projects/${registrationId}/runs`,
    );
    await reviewDialog.getByRole("button", { name: "Retry original start request" }).click();
    const retryResponse = await retryReceipt;
    await recordFailure(retryResponse);
    expect(retryResponse.status()).toBe(202);
    const retryData = (await expectEnvelopeStatus(retryResponse, 202)) as ApiOperationData<"startRun">;
    expect(retryData.run_id).toBe(acceptedRunId);
    expect(retryData.replayed).toBe(true);
    expect(startBodies).toHaveLength(2);
    expect(startBodies[1]).toEqual(startBodies[0]);
    await expect(page.getByRole("heading", { name: `Run ${acceptedRunId}` })).toBeVisible();
    await page.unroute("**/api/v1/projects/*/runs");
    await expect(page.getByRole("button", { name: "Cancel run" })).toBeVisible();
    const cancelResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/runs/${acceptedRunId}/cancel`,
    );
    await page.getByRole("button", { name: "Cancel run" }).click();
    const cancelReceipt = await expectEnvelope(await cancelResponsePromise);
    expect((cancelReceipt as ApiOperationData<"cancelRun">).run_id).toBe(acceptedRunId);
    await expect(page.getByText(/Cancellation acknowledged/)).toBeVisible();

    await enterPhase("real_cancellation_and_resume");
    if (holdPath) await rm(holdPath, { force: true });
    holdPath = undefined;
    const inactiveRun = await waitForRunInactive(acceptedRunId);
    expect(inactiveRun.run_id).toBe(acceptedRunId);
    expect(inactiveRun.execution_active).toBe(false);
    const settledCounts = await dispatchCounts();
    expect(settledCounts.live_dispatch_calls).toBe(0);
    expect(settledCounts.fixture_dispatch_calls).toBeGreaterThan(initialDispatchCount);
    expect(settledCounts.for_case_calls[dispatchCaseId]).toBe(1);
    await expect(page.getByRole("heading", { name: "Review resume" })).toBeVisible();
    const resumePreviewPromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/runs/${acceptedRunId}/resume-preview`,
    );
    await page.getByRole("button", { name: "Preview resume" }).click();
    const resumePreview = await expectEnvelope(await resumePreviewPromise);
    expect((resumePreview as ApiOperationData<"previewRunResume">).run.run_id).toBe(acceptedRunId);
    await expect(page.getByRole("button", { name: "Resume run" })).toBeVisible();
    await expect(page.getByText(/Unknown retries: excluded/)).toBeVisible();
    const resumeResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/runs/${acceptedRunId}/resume`,
    );
    await page.getByRole("button", { name: "Resume run" }).click();
    const resumeReceipt = await expectEnvelopeStatus(await resumeResponsePromise, 202);
    expect((resumeReceipt as ApiOperationData<"resumeRun">).run_id).toBe(acceptedRunId);
    await expect(page.getByText(/Resume acknowledged for run/)).toBeVisible();
    const resumedRun = await waitForRunInactive(acceptedRunId);
    expect(resumedRun.run_id).toBe(acceptedRunId);
    await expect(page.getByRole("heading", { name: "Attempts and segments" })).toBeVisible();

    await enterPhase("frozen_result_inspection");
    await expect(page.getByRole("region", { name: "Run case outcomes" })).toBeVisible();
    const caseButton = page
      .getByRole("region", { name: "Run case outcomes" })
      .getByRole("button", { name: dispatchCaseId, exact: true });
    await caseButton.click();
    const inspector = page.getByRole("region", { name: `Case ${dispatchCaseId} inspection` });
    await expect(inspector).toBeVisible();
    for (const name of ["Include input", "Include request", "Include response", "Include attempts"])
      await expect(inspector.getByLabel(name)).not.toBeChecked();
    await screenshot("execution-run-inspection-default.png");
    await inspector.getByLabel("Include request").check();
    await expect(inspector.getByText("Sanitized request", { exact: true })).toBeVisible();
    await inspector.getByLabel("Include request").uncheck();
    await expect(inspector.getByText("Sanitized request", { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "Close inspection" }).click();
    await expect(page.getByText(/Sanitized request/)).toHaveCount(0);

    await page.setViewportSize({ width: 320, height: 720 });
    await enterPhase("mobile_run_inspection");
    const detailDocument = page.locator("article.run-detail");
    const detailBounds = await detailDocument.boundingBox();
    expect(detailBounds).not.toBeNull();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(overflow).toBe(false);
    await screenshot("execution-run-inspection-mobile-320.png");
    completed = true;
  } finally {
    if (holdPath) await rm(holdPath, { force: true }).catch(() => undefined);
    if (activePhase) phaseStatus.set(activePhase, completed ? "passed" : "failed");
    await recordProgress().catch(() => undefined);
  }
});
