import { expect, test } from "@playwright/test";
import type { APIResponse, Request, Response } from "@playwright/test";
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

type DispatchCountSnapshot = {
  fixture_dispatch_calls: number;
  fixture_dispatch_by_case: Record<string, number>;
  for_case_calls: number;
  for_case_by_case: Record<string, number>;
  live_dispatch_calls: number;
};

type ResumeObserverStage =
  | "not_started"
  | "original_submit"
  | "unknown_ack"
  | "resume_replay"
  | "hold_released"
  | "terminal_read"
  | "completed"
  | "failed";

type SafeObservedRead = {
  status: number;
  response_elapsed_ms: number | null;
  body_elapsed_ms: number | null;
  code: string | null;
  reason: string | null;
  state: string | null;
  active: boolean | null;
  segment_count: number | null;
  attempt_count: number | null;
  pending_reads: number;
};

type ResumeObserver = {
  start(): void;
  acceptSegment(segmentId: string): void;
  replayAcknowledged(): void;
  barrierReleased(): void;
  waitForTerminal(): Promise<ApiOperationData<"readRun">>;
  renderedInactive(): void;
  dispose(): Promise<void>;
};

const RESUME_OBSERVER_CEILING_MS = 197_000;
const OBSERVED_RESPONSE_BODY_LIMIT_MS = 12_000;

function isReadRunData(value: unknown): value is ApiOperationData<"readRun"> {
  return (
    isRecord(value) &&
    typeof value.run_id === "string" &&
    typeof value.state === "string" &&
    typeof value.execution_active === "boolean" &&
    typeof value.attempt_limit === "string" &&
    typeof value.attempts_used === "string" &&
    Array.isArray(value.segment_ids) &&
    value.segment_ids.every((item) => typeof item === "string") &&
    Array.isArray(value.attempts) &&
    value.attempts.every(
      (item) => isRecord(item) && typeof item.attempt_id === "string",
    )
  );
}

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isCountMap(value: unknown): value is Record<string, number> {
  return isRecord(value) && Object.values(value).every(isCount);
}

function isDispatchCountSnapshot(
  value: unknown,
): value is DispatchCountSnapshot {
  return (
    isRecord(value) &&
    isCount(value.fixture_dispatch_calls) &&
    isCount(value.for_case_calls) &&
    isCount(value.live_dispatch_calls) &&
    isCountMap(value.fixture_dispatch_by_case) &&
    isCountMap(value.for_case_by_case)
  );
}

test("installed browser reviews and inspects fixture execution", async ({
  page,
}, testInfo) => {
  page.setDefaultTimeout(12_000);
  const controlDirectory = process.env.DEYKIT_FIXTURE_CONTROL_DIRECTORY;
  if (!controlDirectory)
    throw new Error(
      "The installed driver must set the fixture control directory.",
    );
  const fixtureControlDirectory: string = controlDirectory;

  const phaseIds = [
    "demo_and_fixture_choices",
    "dry_review_and_request_opt_in",
    "unknown_start_and_exact_replay",
    "real_cancellation_and_resume",
    "frozen_result_inspection",
    "mobile_run_inspection",
  ];
  const phaseStatus = new Map<
    string,
    "pending" | "running" | "passed" | "failed"
  >(phaseIds.map((id) => [id, "pending"]));
  const apiFailures: SafeFailure[] = [];
  const screenshots: string[] = [];
  let activePhase: string | null = null;
  let activePhaseStartedAt: number | null = null;
  let completed = false;
  let capability: string | undefined;
  let bootstrapOrigin: string | undefined;
  let resumeObserver: ResumeObserver | undefined;
  let observerStage: ResumeObserverStage = "not_started";
  let observerStageStartedAt: number | null = null;
  let observerStartedAt: number | null = null;
  let observerFailureReason: string | null = null;
  let observedReadCount = 0;
  let pendingObserverReads = 0;
  const observedReads: SafeObservedRead[] = [];
  let latestDispatchTotals: { fixture: number; live: number } | null = null;
  let progressWriteQueue: Promise<void> = Promise.resolve();
  const progressPath = testInfo.outputPath("execution-progress.json");

  function recordProgress(): Promise<void> {
    const body = `${JSON.stringify({
      phases: [...phaseStatus].map(([id, status]) => ({ id, status })),
      completed_phases: [...phaseStatus]
        .filter(([, status]) => status === "passed")
        .map(([id]) => id),
      screenshots,
      active_phase: activePhase,
      active_phase_elapsed_ms:
        activePhaseStartedAt === null
          ? null
          : Math.round(performance.now() - activePhaseStartedAt),
      resume_observer: {
        stage: observerStage,
        elapsed_ms:
          observerStartedAt === null
            ? null
            : Math.round(performance.now() - observerStartedAt),
        stage_elapsed_ms:
          observerStageStartedAt === null
            ? null
            : Math.round(performance.now() - observerStageStartedAt),
        failure_reason: observerFailureReason,
        read_count: observedReadCount,
        pending_reads: pendingObserverReads,
        reads: observedReads,
        actual_dispatch_totals: latestDispatchTotals,
      },
      api_failures: apiFailures,
    })}\n`;
    const write = progressWriteQueue.then(() =>
      writeFile(progressPath, body, "utf8"),
    );
    progressWriteQueue = write.catch(() => undefined);
    return write;
  }

  async function enterPhase(id: string) {
    if (!phaseStatus.has(id))
      throw new Error("Unknown installed execution phase.");
    if (activePhase) phaseStatus.set(activePhase, "passed");
    activePhase = id;
    activePhaseStartedAt = performance.now();
    phaseStatus.set(id, "running");
    await recordProgress();
  }

  async function recordFailure(response: APIResponse | Response) {
    if (response.status() < 400) return;
    const body: unknown = await response.json().catch(() => undefined);
    const error =
      isRecord(body) && isRecord(body.error) ? body.error : undefined;
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
    if (!isDispatchCountSnapshot(value))
      throw new Error("The installed fixture count witness was invalid.");
    expect(value).toMatchObject({ live_dispatch_calls: 0 });
    latestDispatchTotals = {
      fixture: value.fixture_dispatch_calls,
      live: value.live_dispatch_calls,
    };
    void recordProgress().catch(() => undefined);
    return value;
  }

  function createResumeObserver(
    registrationId: string,
    runId: string,
  ): ResumeObserver {
    const path = `/api/v1/projects/${registrationId}/runs/${runId}`;
    const starts = new WeakMap<Request, number>();
    const tasks = new Set<Promise<void>>();
    let acceptedSegmentId: string | undefined;
    let replayAt: number | undefined;
    let releasedAt: number | undefined;
    let ceilingAt: number | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let terminalRun: ApiOperationData<"readRun"> | undefined;
    let resolveTerminal: (run: ApiOperationData<"readRun">) => void = () => {};
    let rejectTerminal: (error: Error) => void = () => {};
    const terminal = new Promise<ApiOperationData<"readRun">>(
      (resolve, reject) => {
        resolveTerminal = resolve;
        rejectTerminal = reject;
      },
    );
    void terminal.catch(() => undefined);

    function stage(value: ResumeObserverStage) {
      observerStage = value;
      observerStageStartedAt = performance.now();
      void recordProgress().catch(() => undefined);
    }

    function fail(reason: string) {
      if (terminalRun || observerFailureReason !== null) return;
      observerFailureReason = reason;
      stage("failed");
      rejectTerminal(new Error(`Resume progress observer failed: ${reason}`));
    }

    function addRead(read: SafeObservedRead) {
      observedReadCount += 1;
      observedReads.push(read);
      if (observedReads.length > 64) observedReads.shift();
    }

    async function consume(response: Response, requestAt: number | undefined) {
      const responseAt = performance.now();
      const responseElapsed =
        requestAt === undefined
          ? null
          : Math.max(0, Math.round(responseAt - requestAt));
      const remaining = (ceilingAt ?? responseAt) - responseAt;
      if (remaining <= 0) return fail("completion_ceiling");
      const bodyStartedAt = performance.now();
      const bodyPromise = response.json();
      void bodyPromise.catch(() => undefined);
      let bodyTimer: ReturnType<typeof setTimeout> | undefined;
      let timedOut = false;
      const timeout = new Promise<never>((_resolve, reject) => {
        bodyTimer = setTimeout(
          () => {
            timedOut = true;
            reject(new Error("body_timeout"));
          },
          Math.min(OBSERVED_RESPONSE_BODY_LIMIT_MS, remaining),
        );
      });
      let body: unknown;
      try {
        body = await Promise.race([bodyPromise, timeout]);
      } catch {
        addRead({
          status: response.status(),
          response_elapsed_ms: responseElapsed,
          body_elapsed_ms: Math.round(performance.now() - bodyStartedAt),
          code: null,
          reason: timedOut ? "body_timeout" : "body_unreadable",
          state: null,
          active: null,
          segment_count: null,
          attempt_count: null,
          pending_reads: pendingObserverReads,
        });
        if (response.status() === 200)
          fail(timedOut ? "body_timeout" : "body_unreadable");
        await recordProgress();
        return;
      } finally {
        if (bodyTimer !== undefined) clearTimeout(bodyTimer);
      }

      const bodyElapsed = Math.round(performance.now() - bodyStartedAt);
      if (response.status() !== 200) {
        const error =
          isRecord(body) && isRecord(body.error) ? body.error : undefined;
        addRead({
          status: response.status(),
          response_elapsed_ms: responseElapsed,
          body_elapsed_ms: bodyElapsed,
          code: safeIdentifier(error?.code),
          reason: safeIdentifier(error?.reason),
          state: null,
          active: null,
          segment_count: null,
          attempt_count: null,
          pending_reads: pendingObserverReads,
        });
        await recordProgress();
        return;
      }
      if (
        !isRecord(body) ||
        body.schema_version !== 1 ||
        !isReadRunData(body.data)
      ) {
        addRead({
          status: 200,
          response_elapsed_ms: responseElapsed,
          body_elapsed_ms: bodyElapsed,
          code: null,
          reason: "invalid_progress_envelope",
          state: null,
          active: null,
          segment_count: null,
          attempt_count: null,
          pending_reads: pendingObserverReads,
        });
        fail("invalid_progress_envelope");
        await recordProgress();
        return;
      }
      const run = body.data;
      if (run.run_id !== runId) {
        addRead({
          status: 200,
          response_elapsed_ms: responseElapsed,
          body_elapsed_ms: bodyElapsed,
          code: null,
          reason: "run_association_mismatch",
          state: null,
          active: null,
          segment_count: null,
          attempt_count: null,
          pending_reads: pendingObserverReads,
        });
        fail("run_association_mismatch");
        await recordProgress();
        return;
      }
      addRead({
        status: 200,
        response_elapsed_ms: responseElapsed,
        body_elapsed_ms: bodyElapsed,
        code: null,
        reason: null,
        state: safeIdentifier(run.state),
        active: run.execution_active,
        segment_count: run.segment_ids.length,
        attempt_count: run.attempts.length,
        pending_reads: pendingObserverReads,
      });
      const terminalRead =
        acceptedSegmentId !== undefined &&
        replayAt !== undefined &&
        releasedAt !== undefined &&
        requestAt !== undefined &&
        requestAt >= replayAt &&
        requestAt >= releasedAt &&
        responseAt >= releasedAt &&
        !run.execution_active &&
        run.segment_ids.includes(acceptedSegmentId);
      if (terminalRead) {
        terminalRun = run;
        stage("terminal_read");
        await recordProgress();
        resolveTerminal(run);
        return;
      }
      await recordProgress();
    }

    const onRequest = (request: Request) => {
      if (
        request.method() === "GET" &&
        new URL(request.url()).pathname === path
      )
        starts.set(request, performance.now());
    };
    const onResponse = (response: Response) => {
      const request = response.request();
      if (
        request.method() !== "GET" ||
        new URL(response.url()).pathname !== path
      )
        return;
      pendingObserverReads += 1;
      const task = consume(response, starts.get(request))
        .catch(() => fail("read_observer_failed"))
        .finally(() => {
          pendingObserverReads = Math.max(0, pendingObserverReads - 1);
          tasks.delete(task);
          void recordProgress().catch(() => undefined);
        });
      tasks.add(task);
      void recordProgress().catch(() => undefined);
    };
    page.on("request", onRequest);
    page.on("response", onResponse);

    return {
      start() {
        observerStartedAt = performance.now();
        ceilingAt = observerStartedAt + RESUME_OBSERVER_CEILING_MS;
        stage("original_submit");
        timer = setTimeout(
          () => fail("completion_ceiling"),
          RESUME_OBSERVER_CEILING_MS,
        );
      },
      acceptSegment(segmentId) {
        acceptedSegmentId = segmentId;
        stage("unknown_ack");
      },
      replayAcknowledged() {
        replayAt = performance.now();
        stage("resume_replay");
      },
      barrierReleased() {
        releasedAt = performance.now();
        stage("hold_released");
      },
      waitForTerminal() {
        return terminal;
      },
      renderedInactive() {
        if (!terminalRun) return fail("inactive_view_missing");
        stage("completed");
        if (timer !== undefined) clearTimeout(timer);
      },
      async dispose() {
        page.off("request", onRequest);
        page.off("response", onResponse);
        if (timer !== undefined) clearTimeout(timer);
        if (!terminalRun && observerFailureReason === null)
          fail("observer_disposed");
        await Promise.allSettled([...tasks]);
      },
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
    throw new Error(
      "The fixture dispatch did not enter the configured barrier.",
    );
  }

  async function readRunWithBusyRetry(runId: string, deadline: number) {
    const backoffMs = [250, 500, 1_000, 2_000];
    let busyReads = 0;
    while (Date.now() < deadline) {
      const response = await page.request.get(
        `/api/v1/projects/${registrationId}/runs/${runId}`,
        { headers: await bootstrapHeaders() },
      );
      if (response.status() === 200) {
        const run = (await expectEnvelope(
          response,
        )) as ApiOperationData<"readRun">;
        if (run.run_id !== runId)
          throw new Error("The installed progress read returned another run.");
        return run;
      }
      const body: unknown = await response.json().catch(() => undefined);
      const error =
        isRecord(body) && isRecord(body.error) ? body.error : undefined;
      const sourceBusy =
        response.status() === 409 &&
        error?.code === "conflict" &&
        error?.reason === "source_busy";
      await recordFailure(response);
      if (!sourceBusy)
        throw new Error("The installed run progress read failed.");
      const delay = backoffMs[Math.min(busyReads, backoffMs.length - 1)];
      busyReads += 1;
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
    throw new Error(
      "The installed run progress read stayed busy past its bound.",
    );
  }

  async function waitForRunInactive(runId: string) {
    const deadline = Date.now() + 25_000;
    while (Date.now() < deadline) {
      const run = await readRunWithBusyRetry(runId, deadline);
      if (!run.execution_active) return run;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    throw new Error(
      "The installed run did not become inactive within the bound.",
    );
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
      throw new Error(
        "The fixture demo did not return a project registration.",
      );
    registrationId = demoData.registration.registration_id;
    await expect(
      page.getByRole("heading", { name: "Sandbox", exact: true }),
    ).toBeVisible();

    const fixturesResponse = await page.request.get(
      `/api/v1/projects/${registrationId}/fixtures?limit=50`,
      { headers: await bootstrapHeaders() },
    );
    const fixturePage = (await expectEnvelope(fixturesResponse)) as {
      items: Array<{ id: string; decision_id: string; dataset_id: string }>;
    };
    const fixture = fixturePage.items[0];
    if (!fixture)
      throw new Error("The support demo has no authored fixture set.");
    const countsBeforeReview = await dispatchCounts();
    initialDispatchCount = countsBeforeReview.fixture_dispatch_calls;
    expect(initialDispatchCount).toBe(0);
    expect(countsBeforeReview.live_dispatch_calls).toBe(0);

    await page
      .getByRole("region", { name: "Project decisions" })
      .getByRole("button", { name: "Content category", exact: true })
      .click();
    await page.getByRole("button", { name: "Run", exact: true }).click();
    const reviewDialog = page.getByRole("dialog", { name: "Review a run" });
    await expect(reviewDialog).toBeVisible();
    await expect(reviewDialog.getByLabel("Fixture set")).toHaveValue(
      fixture.id,
    );
    await reviewDialog
      .getByLabel(/^Lifetime (?:request cap|attempts per case)/)
      .fill("12");
    await reviewDialog.getByLabel("Concurrency").fill("1");
    await reviewDialog.getByLabel(/^Timeout seconds/).fill("30");
    await reviewDialog.getByLabel(/^Deadline seconds/).fill("120");
    await reviewDialog
      .getByLabel("Rate/overload retries per case (0–1)")
      .fill("0");
    const initialReviewResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/runs/preview`,
    );
    await reviewDialog.getByRole("button", { name: "Review run" }).click();
    const initialReview = (await expectEnvelope(
      await initialReviewResponsePromise,
    )) as ApiOperationData<"previewRun">;
    await expect(
      reviewDialog.getByRole("heading", { name: "Server-reviewed context" }),
    ).toBeVisible();
    await expect(
      reviewDialog.getByText(
        "Dry run only. No model calls or run records are created by review.",
      ),
    ).toBeVisible();
    const reviewHash = await reviewDialog
      .locator(".run-review-summary code")
      .first()
      .innerText();
    expect(reviewHash).toMatch(/^[a-f0-9]{64}$/);
    await expect(reviewDialog.locator(".run-case-review pre")).toHaveCount(0);
    const previewData = await page.request.get(
      `/api/v1/projects/${registrationId}/runs?limit=50`,
      { headers: await bootstrapHeaders() },
    );
    expect(previewData.status()).toBe(200);
    expect(
      ((await expectEnvelope(previewData)) as { items: unknown[] }).items,
    ).toHaveLength(0);
    expect((await dispatchCounts()).fixture_dispatch_calls).toBe(
      initialDispatchCount,
    );

    await screenshot("execution-review.png");
    await enterPhase("dry_review_and_request_opt_in");
    await reviewDialog
      .getByLabel("Reveal sanitized compiled request sources in this review")
      .check();
    await reviewDialog.getByRole("button", { name: "Review run" }).click();
    await expect(
      reviewDialog.getByRole("heading", { name: "Server-reviewed context" }),
    ).toBeVisible();
    expect(
      await reviewDialog
        .locator(".run-review-summary code")
        .first()
        .innerText(),
    ).toBe(reviewHash);
    await expect(
      reviewDialog.locator(".run-case-review pre").first(),
    ).toBeVisible();
    await expect(
      reviewDialog.getByText(/request source was redacted/i),
    ).toHaveCount(0);
    expect((await dispatchCounts()).fixture_dispatch_calls).toBe(
      initialDispatchCount,
    );

    expect(await reviewDialog.locator(".run-case-review li").count()).toBe(
      initialReview.case_reviews.length,
    );
    const invalidInputCases = initialReview.case_reviews.filter(
      (item) =>
        item.input_error?.code === "validation_error" &&
        item.input_error.reason === "input_schema_mismatch",
    );
    expect(invalidInputCases).toHaveLength(1);
    const invalidInputCaseId = invalidInputCases[0]?.case_id;
    if (!invalidInputCaseId)
      throw new Error("The authored invalid-input case ID was unavailable.");
    expect(invalidInputCases[0]?.request_hash).toBeNull();
    expect(invalidInputCases[0]?.request_source).toBeNull();
    const eligibleCaseIds = initialReview.case_reviews
      .filter((item) => item.input_error === null && item.request_hash !== null)
      .map((item) => item.case_id);
    expect(initialReview.selected_case_ids).toHaveLength(12);
    expect(initialReview.initial_requests).toBe("11");
    expect(eligibleCaseIds).toHaveLength(11);
    expect(initialReview.invalid_cases).toHaveLength(1);
    const laterEligibleCaseIds = eligibleCaseIds.slice(1);
    dispatchCaseId = eligibleCaseIds[0] ?? "";
    if (!dispatchCaseId)
      throw new Error("The authored demo case ID was unavailable.");
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
        const accepted =
          isRecord(receipt) && isRecord(receipt.data)
            ? receipt.data
            : undefined;
        if (typeof accepted?.run_id === "string") firstRunId = accepted.run_id;
        await route.abort("failed");
        return;
      }
      startBodies.push(requestBody);
      await route.fulfill({ response });
    });

    await page.getByRole("button", { name: "Start reviewed run" }).click();
    await expect.poll(() => firstStartStatus).toBe(202);
    await expect(
      reviewDialog.getByRole("button", {
        name: "Retry original start request",
      }),
    ).toBeVisible();
    await expect(
      reviewDialog.getByRole("button", { name: "Start reviewed run" }),
    ).toBeDisabled();
    expect(firstRunId).toMatch(/^[A-Za-z0-9_-]+$/);
    const acceptedRunId = firstRunId;
    if (!acceptedRunId)
      throw new Error("The accepted run ID was not captured.");
    await waitForEntered(dispatchCaseId);
    await screenshot("execution-review-unknown-start.png");

    await enterPhase("unknown_start_and_exact_replay");
    const retryReceipt = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/runs`,
    );
    await reviewDialog
      .getByRole("button", { name: "Retry original start request" })
      .click();
    const retryResponse = await retryReceipt;
    expect(retryResponse.status()).toBe(202);
    const retryData = (await expectEnvelopeStatus(
      retryResponse,
      202,
    )) as ApiOperationData<"startRun">;
    expect(retryData.run_id).toBe(acceptedRunId);
    expect(retryData.replayed).toBe(true);
    expect(startBodies).toHaveLength(2);
    expect(startBodies[1]).toEqual(startBodies[0]);
    expect(startBodies[0]).toMatchObject({
      request: {
        settings: {
          max_attempts: 12,
          concurrency: 1,
          timeout_seconds: 30,
          deadline_seconds: 120,
          max_retries_per_case: 0,
        },
      },
    });
    await expect(
      page.getByRole("heading", { name: `Run ${acceptedRunId}` }),
    ).toBeVisible();
    await page.unroute("**/api/v1/projects/*/runs");
    await expect(
      page.getByRole("button", { name: "Cancel run" }),
    ).toBeVisible();
    const cancelResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/runs/${acceptedRunId}/cancel`,
    );
    await page.getByRole("button", { name: "Cancel run" }).click();
    const cancelReceipt = await expectEnvelope(await cancelResponsePromise);
    expect((cancelReceipt as ApiOperationData<"cancelRun">).run_id).toBe(
      acceptedRunId,
    );
    await expect(page.getByText(/Cancellation acknowledged/)).toBeVisible();

    await enterPhase("real_cancellation_and_resume");
    if (holdPath) await rm(holdPath, { force: true });
    holdPath = undefined;
    const inactiveRun = await waitForRunInactive(acceptedRunId);
    expect(inactiveRun.run_id).toBe(acceptedRunId);
    expect(inactiveRun.execution_active).toBe(false);
    expect(inactiveRun.attempt_limit).toBe("12");
    const settledCounts = await dispatchCounts();
    expect(settledCounts.live_dispatch_calls).toBe(0);
    expect(settledCounts.fixture_dispatch_calls).toBeGreaterThan(
      initialDispatchCount,
    );
    expect(settledCounts.for_case_by_case[dispatchCaseId]).toBe(1);
    expect(settledCounts.fixture_dispatch_by_case[dispatchCaseId]).toBe(1);
    const outcomesByCase = new Map(
      inactiveRun.cases.map((item) => [item.case_id, item]),
    );
    for (const caseId of laterEligibleCaseIds) {
      const outcome = outcomesByCase.get(caseId);
      expect(outcome?.status).toBe("pending");
      expect(outcome?.attempt_id).toBeNull();
      expect(
        inactiveRun.attempts.some((attempt) => attempt.case_id === caseId),
      ).toBe(false);
      expect(settledCounts.for_case_by_case[caseId] ?? 0).toBe(0);
      expect(settledCounts.fixture_dispatch_by_case[caseId] ?? 0).toBe(0);
    }
    await expect(
      page.getByRole("heading", { name: "Review resume" }),
    ).toBeVisible();
    await page.getByLabel(/^Proposed lifetime attempt cap/).fill("13");
    const resumePreviewPromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/runs/${acceptedRunId}/resume-preview`,
    );
    await page.getByRole("button", { name: "Preview resume" }).click();
    const resumePreview = await expectEnvelope(await resumePreviewPromise);
    expect(
      (resumePreview as ApiOperationData<"previewRunResume">).run.run_id,
    ).toBe(acceptedRunId);
    const resumePreviewData =
      resumePreview as ApiOperationData<"previewRunResume">;
    expect(resumePreviewData.retry_unknown).toBe(false);
    expect(resumePreviewData.proposed_attempt_limit).toBe("13");
    const resumeHoldCaseId = laterEligibleCaseIds[0];
    if (!resumeHoldCaseId)
      throw new Error(
        "The cancelled run had no later eligible case to resume.",
      );
    holdPath = join(fixtureControlDirectory, `${resumeHoldCaseId}.hold`);
    await writeFile(holdPath, "hold\n", { flag: "wx" });
    await expect(
      page.getByRole("button", { name: "Resume run" }),
    ).toBeVisible();
    await expect(page.getByText(/Unknown retries: excluded/)).toBeVisible();
    const resumeBodies: Array<Record<string, unknown>> = [];
    let firstResumeReceipt: ApiOperationData<"resumeRun"> | undefined;
    resumeObserver = createResumeObserver(registrationId, acceptedRunId);
    await page.route(
      `**/api/v1/projects/${registrationId}/runs/${acceptedRunId}/resume`,
      async (route) => {
        if (route.request().method() !== "POST") return route.continue();
        const requestBody = route.request().postDataJSON();
        if (!isRecord(requestBody)) return route.continue();
        resumeBodies.push(requestBody);
        const response = await route.fetch();
        if (resumeBodies.length === 1) {
          expect(response.status()).toBe(202);
          const envelope: unknown = await response.json();
          expect(
            isRecord(envelope) &&
              envelope.schema_version === 1 &&
              isRecord(envelope.data),
          ).toBe(true);
          firstResumeReceipt = (
            envelope as { data: ApiOperationData<"resumeRun"> }
          ).data;
          await route.abort("failed");
          return;
        }
        await route.fulfill({ response });
      },
    );
    resumeObserver.start();
    await page.getByRole("button", { name: "Resume run" }).click();
    await expect(
      page.getByRole("button", { name: "Retry original resume request" }),
    ).toBeVisible();
    if (!firstResumeReceipt)
      throw new Error("The first resume acknowledgement was not captured.");
    if (!firstResumeReceipt.segment_id)
      throw new Error("The first resume acknowledgement had no segment ID.");
    resumeObserver.acceptSegment(firstResumeReceipt.segment_id);
    await waitForEntered(resumeHoldCaseId);
    const countsBeforeResumeReplay = await dispatchCounts();
    const retryResumeResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/runs/${acceptedRunId}/resume`,
    );
    await page
      .getByRole("button", { name: "Retry original resume request" })
      .click();
    const retryResumeResponse = await retryResumeResponsePromise;
    const retryResumeReceipt = (await expectEnvelopeStatus(
      retryResumeResponse,
      202,
    )) as ApiOperationData<"resumeRun">;
    expect(retryResumeReceipt.run_id).toBe(acceptedRunId);
    expect(retryResumeReceipt.replayed).toBe(true);
    expect(retryResumeReceipt.operation_id).toBe(
      firstResumeReceipt.operation_id,
    );
    expect(retryResumeReceipt.segment_id).toBe(firstResumeReceipt.segment_id);
    expect(resumeBodies).toHaveLength(2);
    expect(resumeBodies[1]).toEqual(resumeBodies[0]);
    expect(resumeBodies[0]).toMatchObject({
      retry_unknown: false,
      max_attempts: 13,
    });
    resumeObserver.replayAcknowledged();
    const countsAfterResumeReplay = await dispatchCounts();
    expect(countsAfterResumeReplay.fixture_dispatch_calls).toBe(
      countsBeforeResumeReplay.fixture_dispatch_calls,
    );
    expect(countsAfterResumeReplay.fixture_dispatch_by_case).toEqual(
      countsBeforeResumeReplay.fixture_dispatch_by_case,
    );
    expect(countsAfterResumeReplay.for_case_by_case).toEqual(
      countsBeforeResumeReplay.for_case_by_case,
    );
    await page.unroute(
      `**/api/v1/projects/${registrationId}/runs/${acceptedRunId}/resume`,
    );
    if (holdPath) await rm(holdPath, { force: true });
    holdPath = undefined;
    resumeObserver.barrierReleased();
    const resumedRun = await resumeObserver.waitForTerminal();
    await expect(
      page.locator("article.run-detail p.lead").getByText(/· inactive/),
    ).toBeVisible();
    resumeObserver.renderedInactive();
    expect(resumedRun.run_id).toBe(acceptedRunId);
    expect(resumedRun.attempt_limit).toBe("13");
    expect(resumedRun.attempts_used).toBe("11");
    expect(resumedRun.attempts).toHaveLength(11);
    expect(
      new Set(resumedRun.attempts.map((attempt) => attempt.attempt_id)).size,
    ).toBe(11);
    expect(resumedRun.segment_ids).toHaveLength(
      inactiveRun.segment_ids.length + 1,
    );
    for (const segmentId of inactiveRun.segment_ids)
      expect(resumedRun.segment_ids).toContain(segmentId);
    expect(resumedRun.segment_ids).toContain(firstResumeReceipt.segment_id);
    const completedCounts = await dispatchCounts();
    expect(completedCounts.fixture_dispatch_calls).toBe(11);
    expect(completedCounts.for_case_calls).toBe(11);
    expect(completedCounts.live_dispatch_calls).toBe(0);
    for (const caseId of eligibleCaseIds) {
      expect(completedCounts.for_case_by_case[caseId] ?? 0).toBe(1);
      expect(completedCounts.fixture_dispatch_by_case[caseId] ?? 0).toBe(1);
    }
    expect(completedCounts.for_case_by_case[invalidInputCaseId] ?? 0).toBe(0);
    expect(
      completedCounts.fixture_dispatch_by_case[invalidInputCaseId] ?? 0,
    ).toBe(0);
    await expect(
      page.getByRole("heading", { name: "Attempts and segments" }),
    ).toBeVisible();

    await enterPhase("frozen_result_inspection");
    await expect(
      page.getByRole("region", { name: "Run case outcomes" }),
    ).toBeVisible();
    const caseButton = page
      .getByRole("region", { name: "Run case outcomes" })
      .getByRole("button", { name: dispatchCaseId, exact: true });
    await caseButton.click();
    const inspector = page.getByRole("region", {
      name: `Case ${dispatchCaseId} inspection`,
    });
    await expect(inspector).toBeVisible();
    for (const name of [
      "Include input",
      "Include request",
      "Include response",
      "Include attempts",
    ])
      await expect(inspector.getByLabel(name)).not.toBeChecked();
    await screenshot("execution-run-inspection-default.png");
    await inspector.getByLabel("Include request").check();
    await expect(
      inspector.getByText("Sanitized request", { exact: true }),
    ).toBeVisible();
    await inspector.getByLabel("Include request").uncheck();
    await expect(
      inspector.getByText("Sanitized request", { exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Close inspection" }).click();
    await expect(page.getByText(/Sanitized request/)).toHaveCount(0);

    await page.setViewportSize({ width: 320, height: 720 });
    await enterPhase("mobile_run_inspection");
    const detailDocument = page.locator("article.run-detail");
    const detailBounds = await detailDocument.boundingBox();
    expect(detailBounds).not.toBeNull();
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
    );
    expect(overflow).toBe(false);
    await screenshot("execution-run-inspection-mobile-320.png");
    completed = true;
  } finally {
    if (holdPath) await rm(holdPath, { force: true }).catch(() => undefined);
    if (resumeObserver) await resumeObserver.dispose();
    if (activePhase)
      phaseStatus.set(activePhase, completed ? "passed" : "failed");
    await recordProgress().catch(() => undefined);
  }
});
