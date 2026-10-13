import {
  expect,
  type Page,
  type Request,
  type Response,
  type Route,
  type TestInfo,
} from "@playwright/test";
import { readFile } from "node:fs/promises";
import { isAbsolute, join } from "node:path";
import { bodySha256 } from "./installed-debugging-support";
import type { ApiOperationData } from "../src/api/client";
import {
  assertExactArtifactBytes,
  assertCreateReportRequestBody,
  type BrowserReadTracker,
  captureResponse,
  captureOperation,
  decodeSuccessEnvelope,
  finishDebuggingQualification,
  installLostAcknowledgement,
  invokeReportWitness,
  openPreparedProject,
  readReportWitness,
  startDebuggingQualification,
  settleOnSandbox,
  waitForCountFile,
} from "./installed-debugging-support";

function object(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    throw new Error("Installed report evidence was malformed.");
  return value as Record<string, unknown>;
}

function safeId(value: unknown): string {
  if (typeof value !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(value))
    throw new Error("Installed report evidence identity was invalid.");
  return value;
}

type ReportKind = "run" | "evaluation" | "comparison" | "diagnostic" | "check";
type RawMode = "inputs" | "requests" | "responses";
type Target = {
  kind: ReportKind;
  id: string;
  rawMode?: RawMode;
  groupSnapshotId?: string;
  reportId?: string;
  jsonHash?: string;
  markdownHash?: string;
};

type ObservedMetadataRead = {
  response: Response;
  body: Buffer;
};

function observeNextReportMetadata(
  page: Page,
  registrationId: string,
): {
  result: Promise<ObservedMetadataRead>;
  armRequestArrivalDeadline: () => void;
  dispose: () => void;
} {
  const origin = new URL(page.url()).origin;
  const collectionPath = `/api/v1/projects/${registrationId}/reports/`;
  let retainedRequest: Request | undefined;
  let arrivalTimer: ReturnType<typeof setTimeout> | undefined;
  let headerTimer: ReturnType<typeof setTimeout> | undefined;
  let bodyTimer: ReturnType<typeof setTimeout> | undefined;
  let settled = false;
  let disposed = false;
  let resolveResult: (value: ObservedMetadataRead) => void = () => undefined;
  let rejectResult: (reason: Error) => void = () => undefined;
  const result = new Promise<ObservedMetadataRead>((resolve, reject) => {
    resolveResult = resolve;
    rejectResult = reject;
  });
  void result.catch(() => undefined);

  const clearTimers = () => {
    if (arrivalTimer) clearTimeout(arrivalTimer);
    if (headerTimer) clearTimeout(headerTimer);
    if (bodyTimer) clearTimeout(bodyTimer);
    arrivalTimer = undefined;
    headerTimer = undefined;
    bodyTimer = undefined;
  };
  const rejectOnce = (message: string) => {
    if (settled) return;
    settled = true;
    clearTimers();
    rejectResult(new Error(message));
  };
  const onRequest = (request: Request) => {
    if (settled || retainedRequest || request.method() !== "GET") return;
    const url = new URL(request.url());
    if (url.origin !== origin || !url.pathname.startsWith(collectionPath))
      return;
    const reportId = url.pathname.slice(collectionPath.length);
    if (!/^[A-Za-z0-9_-]{1,128}$/.test(reportId)) return;
    retainedRequest = request;
    if (arrivalTimer) clearTimeout(arrivalTimer);
    arrivalTimer = undefined;
    headerTimer = setTimeout(
      () => rejectOnce("Report metadata headers were not observed in time."),
      12_000,
    );
  };
  const onResponse = (response: Response) => {
    if (settled || !retainedRequest || response.request() !== retainedRequest)
      return;
    if (headerTimer) clearTimeout(headerTimer);
    headerTimer = undefined;
    bodyTimer = setTimeout(
      () => rejectOnce("Report metadata body was not completed in time."),
      12_000,
    );
    void response.body().then(
      (body) => {
        if (settled) return;
        settled = true;
        clearTimers();
        resolveResult({ response, body });
      },
      () => rejectOnce("Report metadata body observation failed."),
    );
  };
  const onRequestFailed = (request: Request) => {
    if (request === retainedRequest)
      rejectOnce("Report metadata request failed before its response.");
  };

  page.on("request", onRequest);
  page.on("response", onResponse);
  page.on("requestfailed", onRequestFailed);

  return {
    result,
    armRequestArrivalDeadline: () => {
      if (settled || retainedRequest || arrivalTimer) return;
      arrivalTimer = setTimeout(
        () => rejectOnce("Report metadata request was not observed in time."),
        12_000,
      );
    },
    dispose: () => {
      if (disposed) return;
      disposed = true;
      page.off("request", onRequest);
      page.off("response", onResponse);
      page.off("requestfailed", onRequestFailed);
      if (!settled)
        rejectOnce("Report metadata observation ended before completion.");
      else clearTimers();
    },
  };
}

async function openReportPage(
  page: Page,
  reads: BrowserReadTracker,
  registrationId: string,
  currentReportId?: string,
): Promise<ApiOperationData<"listReports"> | undefined> {
  const reportsHeading = page.getByRole("heading", {
    name: "Saved reports",
    exact: true,
  });
  const savedReportHeading = page.getByRole("heading", {
    name: "Saved report",
    exact: true,
  });
  const sandboxHeading = page.getByRole("heading", {
    name: "Sandbox",
    exact: true,
  });
  if (await reportsHeading.isVisible().catch(() => false)) {
    await expect(
      page
        .getByRole("list", { name: "Saved reports" })
        .or(page.getByText("No saved reports.", { exact: true })),
    ).toBeVisible();
    await reads.waitForIdle();
    return undefined;
  }
  if (await savedReportHeading.isVisible().catch(() => false)) {
    if (currentReportId)
      await expect(
        page.getByText(currentReportId, { exact: true }),
      ).toBeVisible();
    await expect(page.getByLabel("Pinned report identity")).toBeVisible();
  } else if (await sandboxHeading.isVisible().catch(() => false)) {
    await expect(sandboxHeading).toBeVisible();
  } else {
    await expect(
      page.getByRole("main").getByRole("heading").first(),
    ).toBeVisible();
  }
  await reads.waitForIdle();
  const response = await captureOperation(
    page,
    "listReports",
    { registration_id: registrationId },
    async () => {
      await page
        .getByRole("navigation", { name: "Utilities" })
        .getByRole("button", { name: "Reports", exact: true })
        .click();
      await expect(
        page.getByRole("heading", { name: "Saved reports", exact: true }),
      ).toBeVisible();
    },
  );
  const listing = decodeSuccessEnvelope<ApiOperationData<"listReports">>(
    await response.response.body(),
    200,
    response.response.status(),
  );
  if (listing.items.length === 0)
    await expect(
      page.getByText("No saved reports.", { exact: true }),
    ).toBeVisible();
  else
    await expect(
      page.getByRole("list", { name: "Saved reports" }),
    ).toBeVisible();
  await reads.waitForIdle();
  return listing;
}

async function reopenSavedReport(
  page: Page,
  reads: BrowserReadTracker,
  registrationId: string,
  targetKind: ReportKind,
  targetId: string,
  reportId: string,
): Promise<ApiOperationData<"readReport">> {
  const listing = await openReportPage(page, reads, registrationId);
  if (!listing)
    throw new Error("A newly admitted saved report list was unavailable.");
  expect(
    listing.items.filter((item) => item.report_id === reportId),
  ).toHaveLength(1);
  const response = await captureOperation(
    page,
    "readReport",
    { registration_id: registrationId, report_id: reportId },
    async () => {
      const reportList = page.getByRole("list", { name: "Saved reports" });
      const reportRow = reportList
        .getByRole("listitem")
        .filter({ has: page.getByText(reportId, { exact: true }) });
      await expect(reportRow).toHaveCount(1);
      const targetButton = reportRow.getByRole("button", {
        name: `${targetKind}: ${targetId}`,
        exact: true,
      });
      await expect(targetButton).toHaveCount(1);
      await targetButton.click();
      await expect(
        page.getByRole("heading", { name: "Saved report", exact: true }),
      ).toBeVisible();
    },
  );
  const report = decodeSuccessEnvelope<ApiOperationData<"readReport">>(
    response.body,
    200,
    response.response.status(),
  );
  expect(report.report_id).toBe(reportId);
  expect(report.target_kind).toBe(targetKind);
  expect(report.target_id).toBe(targetId);
  await expect(page.getByText(reportId, { exact: true })).toBeVisible();
  await expect(page.getByLabel("Pinned report identity")).toBeVisible();
  await reads.waitForIdle();
  return report;
}

export async function runReportsWorkflow(
  page: Page,
  testInfo: TestInfo,
): Promise<void> {
  const context = await startDebuggingQualification(page, testInfo, "R");
  const { qualification, registrationId, reads } = context;
  let succeeded = false;
  try {
    await qualification.enterPhase("admit-c-and-g-evidence");
    const evidencePath = qualification.sourceEvidencePath;
    const secondaryPath = qualification.secondaryProjectPath;
    if (!evidencePath || !secondaryPath)
      throw new Error("Paired source evidence was unavailable.");
    const sourceEvidence = object(
      JSON.parse(await readFile(evidencePath, "utf8")),
    );
    if (sourceEvidence.workflow !== "G" || sourceEvidence.status !== "passed")
      throw new Error("The imported G workflow evidence was not accepted.");
    if (
      typeof sourceEvidence.playwright_output_path !== "string" ||
      !isAbsolute(sourceEvidence.playwright_output_path)
    )
      throw new Error("The imported G progress location was invalid.");
    const gOutput = sourceEvidence.playwright_output_path;
    const gProgress = object(
      JSON.parse(
        await readFile(join(gOutput, "debugging-progress.json"), "utf8"),
      ),
    );
    const groupWitnesses = object(gProgress.witnesses);
    const diagnosticGroup = safeId(groupWitnesses.diagnostic_group_id);
    const diagnosticSnapshot = safeId(groupWitnesses.diagnostic_snapshot_id);
    const checkGroup = safeId(groupWitnesses.check_group_id);
    const checkSnapshot = safeId(groupWitnesses.check_snapshot_id);
    const diagnosticReportId = safeId(groupWitnesses.diagnostic_report_id);
    const checkReportId = safeId(groupWitnesses.check_report_id);
    const diagnosticHashes = {
      json: safeId(groupWitnesses.diagnostic_report_json_sha256),
      markdown: safeId(groupWitnesses.diagnostic_report_markdown_sha256),
    };
    const checkHashes = {
      json: safeId(groupWitnesses.check_report_json_sha256),
      markdown: safeId(groupWitnesses.check_report_markdown_sha256),
    };
    qualification.setWitness("g_diagnostic_snapshot_id", diagnosticSnapshot);
    qualification.setWitness("g_check_snapshot_id", checkSnapshot);

    await qualification.enterPhase("read-c-comparison");
    const comparisonResponse = await captureOperation(
      page,
      "listComparisons",
      { registration_id: registrationId },
      async () => {
        await page
          .getByRole("navigation", { name: "Utilities" })
          .getByRole("button", { name: "Comparisons", exact: true })
          .click();
        await expect(
          page.getByRole("heading", { name: "Comparisons", exact: true }),
        ).toBeVisible();
      },
    );
    const comparisons = decodeSuccessEnvelope<
      ApiOperationData<"listComparisons">
    >(
      await comparisonResponse.response.body(),
      200,
      comparisonResponse.response.status(),
    );
    const forward = comparisons.items.filter((item) => {
      const counts = object(item.outcomes.primary_counts);
      return (
        item.left_evaluation_id === qualification.seedMetadata.evaluation_id &&
        item.left_result_snapshot_id ===
          qualification.seedMetadata.result_snapshot_id &&
        item.right_evaluation_id !== qualification.seedMetadata.evaluation_id &&
        item.right_result_snapshot_id !==
          qualification.seedMetadata.result_snapshot_id &&
        counts.both_correct === "6" &&
        counts.improved === "1" &&
        counts.regressed === "0" &&
        counts.both_wrong === "1" &&
        counts.unlabelled_agreement === "2" &&
        counts.unavailable_answer === "2"
      );
    });
    expect(forward).toHaveLength(1);
    const forwardComparison = forward[0];
    if (!forwardComparison)
      throw new Error("The expected saved comparison was unavailable.");
    const comparisonId = safeId(forwardComparison.comparison_id);
    const forwardCounts = object(forwardComparison.outcomes.primary_counts);
    const expectedBuckets = {
      left_only: "0",
      right_only: "0",
      changed_input: "0",
      changed_question_options: "0",
      changed_expectations: "0",
      unavailable_answer: "2",
      excluded_expectation: "0",
      unlabelled_agreement: "2",
      unlabelled_disagreement: "0",
      both_correct: "6",
      improved: "1",
      regressed: "0",
      both_wrong: "1",
    };
    expect(Object.keys(forwardCounts).sort()).toEqual(
      Object.keys(expectedBuckets).sort(),
    );
    expect(forwardCounts).toEqual(expectedBuckets);
    const forwardOutcomes = object(forwardComparison.outcomes);
    expect(forwardOutcomes.quality_denominator).toBe("8");
    expect(forwardOutcomes.left_correct_count).toBe("6");
    expect(forwardOutcomes.right_correct_count).toBe("7");
    expect(forwardOutcomes.unlabelled_denominator).toBe("2");
    expect(
      Object.values(forwardCounts).reduce(
        (total: bigint, count) => total + BigInt(String(count)),
        0n,
      ),
    ).toBe(12n);
    const rightEvaluationId = safeId(forwardComparison.right_evaluation_id);
    await page
      .getByLabel("Left saved evaluation ID", { exact: true })
      .fill(qualification.seedMetadata.evaluation_id);
    await page
      .getByLabel("Right saved evaluation ID", { exact: true })
      .fill(rightEvaluationId);
    const [rightEvaluationRead, leftEvaluationRead] = await Promise.all([
      captureOperation(
        page,
        "readEvaluation",
        { registration_id: registrationId, evaluation_id: rightEvaluationId },
        async () => {},
      ),
      captureOperation(
        page,
        "readEvaluation",
        {
          registration_id: registrationId,
          evaluation_id: qualification.seedMetadata.evaluation_id,
        },
        () =>
          page
            .getByRole("button", {
              name: "Verify saved evaluations",
              exact: true,
            })
            .click(),
      ),
    ]);
    expect(leftEvaluationRead.response.status()).toBe(200);
    expect(rightEvaluationRead.response.status()).toBe(200);
    const leftEvaluation = decodeSuccessEnvelope<
      ApiOperationData<"readEvaluation">
    >(leftEvaluationRead.body, 200, leftEvaluationRead.response.status());
    const rightEvaluation = decodeSuccessEnvelope<
      ApiOperationData<"readEvaluation">
    >(rightEvaluationRead.body, 200, rightEvaluationRead.response.status());
    expect(leftEvaluation).toMatchObject({
      evaluation_id: qualification.seedMetadata.evaluation_id,
      run_id: qualification.seedMetadata.run_id,
      content_hash: qualification.seedMetadata.evaluation_content_hash,
      result_snapshot_id: forwardComparison.left_result_snapshot_id,
      label_snapshot_id: qualification.seedMetadata.label_snapshot_id,
    });
    expect(rightEvaluation.evaluation_id).toBe(rightEvaluationId);
    expect(rightEvaluation.run_id).not.toBe(qualification.seedMetadata.run_id);
    expect(rightEvaluation.result_snapshot_id).toBe(
      forwardComparison.right_result_snapshot_id,
    );
    const rightMetrics = object(rightEvaluation.metrics);
    const rightSummary = object(rightMetrics.summary);
    const rightAccuracy = object(rightSummary.set_accuracy);
    expect(rightAccuracy.numerator).toBe("7");
    expect(rightAccuracy.denominator).toBe("8");
    expect(rightAccuracy.value).toBe("0.875000");
    await expect(
      page.locator('dl[aria-label="Verified evaluation context"]'),
    ).toContainText(
      `${qualification.seedMetadata.run_id} · original · result ${forwardComparison.left_result_snapshot_id} · labels ${qualification.seedMetadata.label_snapshot_id}`,
    );
    await expect(
      page.locator('dl[aria-label="Verified evaluation context"]'),
    ).toContainText(
      `${rightEvaluation.run_id} · ${rightEvaluation.mode} · result ${rightEvaluation.result_snapshot_id} · labels ${rightEvaluation.label_snapshot_id}`,
    );
    qualification.setWitness("comparison_id", comparisonId);
    await reads.waitForIdle();

    const cTargets: Target[] = [
      { kind: "run", id: qualification.seedMetadata.run_id, rawMode: "inputs" },
      {
        kind: "evaluation",
        id: qualification.seedMetadata.evaluation_id,
        rawMode: "requests",
      },
      { kind: "comparison", id: comparisonId, rawMode: "responses" },
    ];
    let replayUsed = false;
    let expectedReportCount = 0;
    const createdReports: Array<{
      target: Target;
      reportId: string;
      contentHash: string;
      bytes: Record<"json" | "markdown", Buffer>;
    }> = [];
    for (const target of cTargets) {
      await qualification.enterPhase("create-c-" + target.kind + "-report");
      await openReportPage(
        page,
        reads,
        registrationId,
        createdReports.at(-1)?.reportId,
      );
      await page
        .getByRole("button", {
          name: "Create report from verified target",
          exact: true,
        })
        .click();
      const dialog = page.getByRole("dialog", {
        name: "Create a pinned report",
        exact: true,
      });
      await dialog
        .getByRole("combobox", { name: "Target kind", exact: true })
        .selectOption(target.kind);
      await dialog.getByLabel("Target ID", { exact: true }).fill(target.id);
      if (target.kind === "run")
        await dialog
          .getByLabel("Saved evaluation ID (optional)", { exact: true })
          .fill(qualification.seedMetadata.evaluation_id);
      const operation =
        target.kind === "run"
          ? "readRun"
          : target.kind === "evaluation"
            ? "readEvaluation"
            : "readComparison";
      const params: Record<string, string> =
        target.kind === "run"
          ? { registration_id: registrationId, run_id: target.id }
          : target.kind === "evaluation"
            ? { registration_id: registrationId, evaluation_id: target.id }
            : { registration_id: registrationId, comparison_id: target.id };
      const savedEvaluationResponse =
        target.kind === "run"
          ? page.waitForResponse(
              (response) => {
                const url = new URL(response.url());
                return (
                  response.request().method() === "GET" &&
                  url.pathname ===
                    "/api/v1/projects/" +
                      registrationId +
                      "/evaluations/" +
                      qualification.seedMetadata.evaluation_id
                );
              },
              { timeout: 12_000 },
            )
          : undefined;
      const verified = await captureOperation(page, operation, params, () =>
        dialog
          .getByRole("button", {
            name: "Verify saved target",
            exact: true,
          })
          .click(),
      );
      expect(verified.response.status()).toBe(200);
      await verified.response.body();
      if (savedEvaluationResponse) {
        const savedEvaluation = await savedEvaluationResponse;
        expect(savedEvaluation.status()).toBe(200);
        await savedEvaluation.body();
      }
      await expect(
        dialog.locator('pre[aria-label="Verified report target"]'),
      ).toBeVisible();
      const verifiedText =
        (await dialog
          .locator('pre[aria-label="Verified report target"]')
          .textContent()) ?? "";
      if (target.kind === "run")
        expect(
          verifiedText.includes(
            `Evaluation ${qualification.seedMetadata.evaluation_id}`,
          ) &&
            verifiedText.includes(
              `Result ${qualification.seedMetadata.result_snapshot_id}`,
            ) &&
            verifiedText.includes(
              `Labels ${qualification.seedMetadata.label_snapshot_id}`,
            ),
        ).toBe(true);
      if (target.kind === "evaluation")
        expect(
          verifiedText.includes(
            `Evaluation ${qualification.seedMetadata.evaluation_id}`,
          ) &&
            verifiedText.includes(
              `Result ${qualification.seedMetadata.result_snapshot_id}`,
            ) &&
            verifiedText.includes(
              `Labels ${qualification.seedMetadata.label_snapshot_id}`,
            ),
        ).toBe(true);
      for (const raw of [
        "Include raw inputs",
        "Include raw requests",
        "Include raw responses",
      ])
        await expect(dialog.getByLabel(raw, { exact: true })).not.toBeChecked();
      const expectedRaw = {
        inputs: target.rawMode === "inputs",
        requests: target.rawMode === "requests",
        responses: target.rawMode === "responses",
      };
      const requestExpectation = {
        targetKind: target.kind,
        targetId: target.id,
        raw: expectedRaw,
        ...(target.kind === "run"
          ? {
              evaluationId: qualification.seedMetadata.evaluation_id,
              resultSnapshotId: qualification.seedMetadata.result_snapshot_id,
            }
          : {}),
      };
      if (target.rawMode) {
        const label = `Include raw ${target.rawMode}`;
        await dialog.getByLabel(label, { exact: true }).check();
      }

      const lost = replayUsed
        ? undefined
        : await installLostAcknowledgement(
            page,
            "/api/v1/projects/" + registrationId + "/reports",
            200,
          );
      const metadataObservation = observeNextReportMetadata(
        page,
        registrationId,
      );
      try {
        let reportId = "";
        if (lost) {
          await dialog
            .getByRole("button", { name: "Create report", exact: true })
            .click();
          await expect(
            dialog.getByRole("button", {
              name: "Retry original unchanged report",
              exact: true,
            }),
          ).toBeVisible();
          expect(lost.firstObservation()?.firstStatus).toBe(200);
          const replayResponse = await captureOperation(
            page,
            "createReport",
            { registration_id: registrationId },
            () =>
              dialog
                .getByRole("button", {
                  name: "Retry original unchanged report",
                  exact: true,
                })
                .click(),
          );
          expect(replayResponse.response.status()).toBe(200);
          const observed = lost.observation();
          expect(observed?.replayStatus).toBe(200);
          expect(observed?.sameRequestBytes).toBe(true);
          if (!observed)
            throw new Error(
              "The original report request body was unavailable.",
            );
          expect(bodySha256(observed.firstRequestBody)).toBe(
            observed.firstRequestHash,
          );
          assertCreateReportRequestBody(
            observed.firstRequestBody,
            requestExpectation,
          );
          const first = decodeSuccessEnvelope<ApiOperationData<"createReport">>(
            observed?.firstResponseBody ?? Buffer.alloc(0),
            200,
            observed?.firstStatus ?? 0,
          );
          const receipt = decodeSuccessEnvelope<
            ApiOperationData<"createReport">
          >(
            observed?.replayResponseBody ?? Buffer.alloc(0),
            200,
            observed?.replayStatus ?? 0,
          );
          expect(receipt.report_id).toBe(first.report_id);
          expect(receipt.target_kind).toBe(target.kind);
          expect(receipt.target_id).toBe(target.id);
          expect(first.raw).toEqual(expectedRaw);
          expect(receipt.raw).toEqual(expectedRaw);
          expect(receipt.content_hash).toBe(first.content_hash);
          if (target.kind === "run")
            expect(receipt.result_snapshot_ids).toContain(
              qualification.seedMetadata.result_snapshot_id,
            );
          if (target.kind === "run")
            expect(receipt.label_snapshot_ids).toContain(
              qualification.seedMetadata.label_snapshot_id,
            );
          if (target.kind === "evaluation") {
            expect(receipt.evaluation_ids).toContain(
              qualification.seedMetadata.evaluation_id,
            );
            expect(receipt.result_snapshot_ids).toContain(
              qualification.seedMetadata.result_snapshot_id,
            );
            expect(receipt.label_snapshot_ids).toContain(
              qualification.seedMetadata.label_snapshot_id,
            );
          }
          reportId = receipt.report_id;
          replayUsed = true;
          qualification.setWitness(
            "report_create_request_sha256",
            observed?.firstRequestHash ?? "",
          );
        } else {
          const created = await captureOperation(
            page,
            "createReport",
            { registration_id: registrationId },
            () =>
              dialog
                .getByRole("button", { name: "Create report", exact: true })
                .click(),
          );
          const receipt = decodeSuccessEnvelope<
            ApiOperationData<"createReport">
          >(await created.response.body(), 200, created.response.status());
          const requestBody = created.response.request().postDataBuffer();
          if (!requestBody)
            throw new Error(
              "The original report request body was unavailable.",
            );
          assertCreateReportRequestBody(requestBody, requestExpectation);
          expect(receipt.target_kind).toBe(target.kind);
          expect(receipt.target_id).toBe(target.id);
          expect(receipt.raw).toEqual(expectedRaw);
          if (target.kind === "run")
            expect(receipt.result_snapshot_ids).toContain(
              qualification.seedMetadata.result_snapshot_id,
            );
          if (target.kind === "run")
            expect(receipt.label_snapshot_ids).toContain(
              qualification.seedMetadata.label_snapshot_id,
            );
          if (target.kind === "evaluation") {
            expect(receipt.evaluation_ids).toContain(
              qualification.seedMetadata.evaluation_id,
            );
            expect(receipt.result_snapshot_ids).toContain(
              qualification.seedMetadata.result_snapshot_id,
            );
            expect(receipt.label_snapshot_ids).toContain(
              qualification.seedMetadata.label_snapshot_id,
            );
          }
          reportId = receipt.report_id;
        }
        qualification.setWitness(target.kind + "_report_id", reportId);
        metadataObservation.armRequestArrivalDeadline();
        const metadata = await metadataObservation.result;
        const metadataResponse = metadata.response;
        expect(new URL(metadataResponse.url()).pathname).toBe(
          "/api/v1/projects/" + registrationId + "/reports/" + reportId,
        );
        const metadataBody = metadata.body;
        await expect(
          page.getByRole("heading", { name: "Saved report", exact: true }),
        ).toBeVisible();
        const report = decodeSuccessEnvelope<ApiOperationData<"readReport">>(
          metadataBody,
          200,
          metadataResponse.status(),
        );
        expect(report.report_id).toBe(reportId);
        expect(report.target_kind).toBe(target.kind);
        expect(report.target_id).toBe(target.id);
        expect(report.raw).toEqual(expectedRaw);
        if (target.kind === "run" || target.kind === "evaluation")
          expect(report.label_snapshot_ids).toContain(
            qualification.seedMetadata.label_snapshot_id,
          );
        expectedReportCount += 1;
        const listing = await openReportPage(
          page,
          reads,
          registrationId,
          reportId,
        );
        if (!listing)
          throw new Error("The saved report list was not freshly admitted.");
        expect(listing.total).toBe(String(expectedReportCount));
        expect(
          listing.items.filter((item) => item.report_id === reportId),
        ).toHaveLength(1);
        expect(listing.items).toHaveLength(expectedReportCount);
        const reportList = page.getByRole("list", { name: "Saved reports" });
        await expect(reportList.getByRole("listitem")).toHaveCount(
          expectedReportCount,
        );
        const createdReportRow = reportList
          .getByRole("listitem")
          .filter({ has: page.getByText(reportId, { exact: true }) });
        await expect(createdReportRow).toHaveCount(1);
        await expect(
          createdReportRow.getByRole("button", {
            name: `${target.kind}: ${target.id}`,
            exact: true,
          }),
        ).toHaveCount(1);
        await reads.waitForIdle();
        const witnessPath = testInfo.outputPath(
          "report-" + reportId + "-witness.json",
        );
        await settleOnSandbox(page, reads);
        await invokeReportWitness(
          qualification,
          qualification.projectPath,
          reportId,
          witnessPath,
        );
        const witness = await readReportWitness(witnessPath, reportId);
        const afterWitness = await reopenSavedReport(
          page,
          reads,
          registrationId,
          target.kind,
          target.id,
          reportId,
        );
        expect(afterWitness.content_hash).toBe(report.content_hash);
        expect(afterWitness.raw).toEqual(expectedRaw);
        const downloadedBytes = {} as Record<"json" | "markdown", Buffer>;
        for (const format of ["json", "markdown"] as const) {
          await page
            .getByRole("combobox", { name: "Download format", exact: true })
            .selectOption(format);
          const response = await captureOperation(
            page,
            "downloadReport",
            { registration_id: registrationId, report_id: reportId },
            () =>
              page
                .getByRole("button", {
                  name: "Preview report bytes",
                  exact: true,
                })
                .click(),
            (query) => query.get("format") === format,
          );
          await assertReportDownload(response.response, format);
          const bytes = await response.response.body();
          downloadedBytes[format] = bytes;
          expect(bytes.byteLength).toBeLessThanOrEqual(8 * 1024 * 1024);
          const expected = witness[format];
          expect(
            await assertExactArtifactBytes(
              bytes,
              join(testInfo.outputDir, expected.file),
              expected.bytes_hash,
            ),
          ).toBe(true);
          qualification.setWitness(
            target.kind + "_report_" + format + "_sha256",
            expected.bytes_hash,
          );
          await expect(
            page.getByRole("status").filter({
              hasText:
                "Read " + bytes.byteLength + " report bytes as " + format,
            }),
          ).toBeVisible();
        }
        if (target.kind === "run")
          await exerciseKnownReportDownloadFailures(
            page,
            reads,
            registrationId,
            target.id,
            reportId,
            {
              json: {
                path: join(testInfo.outputDir, witness.json.file),
                hash: witness.json.bytes_hash,
              },
              markdown: {
                path: join(testInfo.outputDir, witness.markdown.file),
                hash: witness.markdown.bytes_hash,
              },
            },
          );
        createdReports.push({
          target,
          reportId,
          contentHash: report.content_hash,
          bytes: downloadedBytes,
        });
      } finally {
        try {
          metadataObservation.dispose();
        } finally {
          await lost?.dispose();
        }
      }
      await reads.waitForIdle();
    }

    await qualification.enterPhase("change-current-label-after-reports");
    const runs = await captureOperation(
      page,
      "listRuns",
      { registration_id: registrationId },
      () =>
        page
          .getByRole("navigation", { name: "Utilities" })
          .getByRole("button", { name: "Runs", exact: true })
          .click(),
    );
    const runPage = decodeSuccessEnvelope<ApiOperationData<"listRuns">>(
      runs.body,
      200,
      runs.response.status(),
    );
    expect(
      runPage.items.some(
        (item) => item.run_id === qualification.seedMetadata.run_id,
      ),
    ).toBe(true);
    const results = await captureOperation(
      page,
      "listResults",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
      },
      () =>
        page
          .getByRole("button", {
            name: qualification.seedMetadata.run_id,
            exact: true,
          })
          .click(),
      (query) => !query.has("evaluation_id"),
    );
    const resultPage = decodeSuccessEnvelope<ApiOperationData<"listResults">>(
      results.body,
      200,
      results.response.status(),
    );
    expect(resultPage.result_snapshot_id).toBe(
      qualification.seedMetadata.result_snapshot_id,
    );
    const pinnedResults = await captureOperation(
      page,
      "listResults",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
      },
      async () => {
        await page
          .getByRole("combobox", {
            name: "Evaluation snapshot",
            exact: true,
          })
          .selectOption(qualification.seedMetadata.evaluation_id);
      },
      (query) =>
        query.get("evaluation_id") === qualification.seedMetadata.evaluation_id,
    );
    decodeSuccessEnvelope<ApiOperationData<"listResults">>(
      pinnedResults.body,
      200,
      pinnedResults.response.status(),
    );
    await reads.waitForIdle();
    const caseRow = page
      .getByRole("table", { name: "Frozen result rows" })
      .getByRole("row")
      .filter({ hasText: "ex-003" });
    await caseRow.getByRole("button", { name: "ex-003", exact: true }).click();
    const inspector = page.getByRole("region", {
      name: "Case ex-003 inspection",
    });
    const labelDialog = page.getByRole("dialog", {
      name: "Review current label",
      exact: true,
    });
    await inspector
      .getByRole("button", { name: "Review current label", exact: true })
      .click();
    const question = labelDialog.getByLabel("Question · question", {
      exact: true,
    });
    const report = labelDialog.getByLabel("Report · report", { exact: true });
    await expect(question).toBeChecked();
    await expect(report).not.toBeChecked();
    await question.uncheck();
    await report.check();
    const labelWrite = await captureOperation(
      page,
      "batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post",
      {
        registration_id: registrationId,
        decision_id: qualification.seedMetadata.decision_id,
        dataset_id: qualification.seedMetadata.dataset_id,
      },
      () =>
        labelDialog
          .getByRole("button", { name: "Save current label", exact: true })
          .click(),
    );
    const labelReceipt = decodeSuccessEnvelope<
      ApiOperationData<"batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post">
    >(labelWrite.body, 200, labelWrite.response.status());
    expect(labelReceipt.changes).toHaveLength(1);
    expect(labelReceipt.changes[0]?.case_id).toBe("ex-003");
    expect(labelReceipt.changes[0]?.label?.acceptable_option_ids).toEqual([
      "report",
    ]);
    await reads.waitForIdle();
    await expect(
      labelDialog.getByRole("region", {
        name: "Current mutable label",
        exact: true,
      }),
    ).toContainText("label report");
    await expect(labelDialog.getByRole("status")).toContainText(
      "Label receipt recorded",
    );
    await expect(report).toBeChecked();
    await expect(question).not.toBeChecked();
    await page.keyboard.press("Escape");
    await expect(labelDialog).toBeHidden();
    await expect(
      page.getByRole("dialog", {
        name: "Discard current label changes",
        exact: true,
      }),
    ).toHaveCount(0);
    await expect(caseRow).toContainText("question");
    const refreshedListing = await openReportPage(page, reads, registrationId);
    if (!refreshedListing)
      throw new Error("The saved report list did not refresh after labeling.");
    expect(refreshedListing.items).toHaveLength(createdReports.length);
    for (const saved of createdReports) {
      const reportButton = page.getByRole("button", {
        name: `${saved.target.kind}: ${saved.target.id}`,
        exact: true,
      });
      const metadata = await captureOperation(
        page,
        "readReport",
        { registration_id: registrationId, report_id: saved.reportId },
        async () => {
          await reportButton.click();
          await expect(
            page.getByRole("heading", { name: "Saved report", exact: true }),
          ).toBeVisible();
        },
      );
      const unchanged = decodeSuccessEnvelope<ApiOperationData<"readReport">>(
        metadata.body,
        200,
        metadata.response.status(),
      );
      expect(unchanged.report_id).toBe(saved.reportId);
      expect(unchanged.content_hash).toBe(saved.contentHash);
      expect(unchanged.target_kind).toBe(saved.target.kind);
      expect(unchanged.target_id).toBe(saved.target.id);
      expect(unchanged.raw).toEqual({
        inputs: saved.target.rawMode === "inputs",
        requests: saved.target.rawMode === "requests",
        responses: saved.target.rawMode === "responses",
      });
      for (const format of ["json", "markdown"] as const) {
        await page
          .getByRole("combobox", { name: "Download format", exact: true })
          .selectOption(format);
        const bytes = await captureOperation(
          page,
          "downloadReport",
          { registration_id: registrationId, report_id: saved.reportId },
          () =>
            page
              .getByRole("button", {
                name: "Preview report bytes",
                exact: true,
              })
              .click(),
          (query) => query.get("format") === format,
        );
        await assertReportDownload(bytes.response, format);
        expect(
          Buffer.compare(await bytes.response.body(), saved.bytes[format]),
        ).toBe(0);
      }
      await reads.waitForIdle();
      const listing = await openReportPage(
        page,
        reads,
        registrationId,
        saved.reportId,
      );
      if (!listing)
        throw new Error(
          "The reports view did not remount after a report read.",
        );
    }

    await qualification.enterPhase("read-g-saved-report-bytes");
    const gProject = await openPreparedProject(page, secondaryPath);
    await expect(
      page.getByRole("main").getByRole("heading").first(),
    ).toBeVisible();
    await reads.waitForIdle();
    let currentGReportId: string | undefined;
    for (const target of [
      {
        kind: "diagnostic" as const,
        id: diagnosticGroup,
        snapshot: diagnosticSnapshot,
        reportId: diagnosticReportId,
        hashes: diagnosticHashes,
      },
      {
        kind: "check" as const,
        id: checkGroup,
        snapshot: checkSnapshot,
        reportId: checkReportId,
        hashes: checkHashes,
      },
    ]) {
      if (currentGReportId) {
        await expect(
          page.getByText(currentGReportId, { exact: true }),
        ).toBeVisible();
        await expect(page.getByLabel("Pinned report identity")).toBeVisible();
      } else {
        await expect(
          page.getByRole("main").getByRole("heading").first(),
        ).toBeVisible();
      }
      await reads.waitForIdle();
      const reportRead = await captureOperation(
        page,
        "readReport",
        {
          registration_id: gProject.registrationId,
          report_id: target.reportId,
        },
        async () => {
          if (
            !(await page
              .getByRole("heading", { name: "Saved reports", exact: true })
              .isVisible()
              .catch(() => false))
          ) {
            await page
              .getByRole("navigation", { name: "Utilities" })
              .getByRole("button", { name: "Reports", exact: true })
              .click();
            await expect(
              page.getByRole("heading", { name: "Saved reports", exact: true }),
            ).toBeVisible();
          }
          const reportList = page.getByRole("list", {
            name: "Saved reports",
          });
          await expect(reportList).toBeVisible();
          await reads.waitForIdle();
          const reportRow = reportList
            .getByRole("listitem")
            .filter({ has: page.getByText(target.reportId, { exact: true }) });
          await expect(reportRow).toHaveCount(1);
          const existing = reportRow.getByRole("button", {
            name: `${target.kind}: ${target.id}`,
            exact: true,
          });
          await expect(existing).toHaveCount(1);
          await existing.click();
          await expect(
            page.locator('pre[aria-label="Pinned report identity"]'),
          ).toContainText(target.snapshot);
        },
      );
      const report = decodeSuccessEnvelope<ApiOperationData<"readReport">>(
        await reportRead.response.body(),
        200,
        reportRead.response.status(),
      );
      expect(report.report_id).toBe(target.reportId);
      expect(report.target_kind).toBe(target.kind);
      expect(report.target_id).toBe(target.id);
      expect(report.raw).toEqual({
        inputs: false,
        requests: false,
        responses: false,
      });
      expect(
        target.kind === "diagnostic"
          ? report.diagnostic_snapshot_id
          : report.check_snapshot_id,
      ).toBe(target.snapshot);
      await expect(
        page.getByText(target.reportId, { exact: true }),
      ).toBeVisible();
      await expect(page.getByLabel("Pinned report identity")).toBeVisible();
      await reads.waitForIdle();
      currentGReportId = target.reportId;
      const witnessPath = testInfo.outputPath(
        "imported-" + target.reportId + "-witness.json",
      );
      await settleOnSandbox(page, reads);
      await importReportWitness(
        qualification,
        secondaryPath,
        target.reportId,
        witnessPath,
      );
      const witness = await readReportWitness(witnessPath, target.reportId);
      expect(witness.json.bytes_hash).toBe(target.hashes.json);
      expect(witness.markdown.bytes_hash).toBe(target.hashes.markdown);
      const afterWitness = await reopenSavedReport(
        page,
        reads,
        gProject.registrationId,
        target.kind,
        target.id,
        target.reportId,
      );
      expect(afterWitness.content_hash).toBe(report.content_hash);
      expect(afterWitness.raw).toEqual(report.raw);
      for (const format of ["json", "markdown"] as const) {
        await page
          .getByRole("combobox", { name: "Download format", exact: true })
          .selectOption(format);
        const download = await captureOperation(
          page,
          "downloadReport",
          {
            registration_id: gProject.registrationId,
            report_id: target.reportId,
          },
          () =>
            page
              .getByRole("button", {
                name: "Preview report bytes",
                exact: true,
              })
              .click(),
          (query) => query.get("format") === format,
        );
        await assertReportDownload(download.response, format);
        const bytes = await download.response.body();
        expect(
          await assertExactArtifactBytes(
            bytes,
            join(testInfo.outputDir, witness[format].file),
            witness[format].bytes_hash,
          ),
        ).toBe(true);
        expect(witness[format].bytes_hash).toBe(
          format === "json" ? target.hashes.json : target.hashes.markdown,
        );
      }
      await reads.waitForIdle();
    }
    await qualification.enterPhase("zero-new-report-dispatches");
    const counts = await waitForCountFile(
      qualification.controlDirectory,
      (value) =>
        value.fixture_dispatch_calls === 0 &&
        value.for_case_calls === 0 &&
        value.live_dispatch_calls === 0,
    );
    expect(counts).toMatchObject({
      fixture_dispatch_calls: 0,
      for_case_calls: 0,
      live_dispatch_calls: 0,
    });
    qualification.setCounts(counts);
    if (currentGReportId) {
      await expect(
        page.getByText(currentGReportId, { exact: true }),
      ).toBeVisible();
      await expect(page.getByLabel("Pinned report identity")).toBeVisible();
    }
    await reads.waitForIdle();
    await page.getByRole("button", { name: "Sandbox", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Sandbox", exact: true }),
    ).toBeVisible();
    await qualification.captureScreenshot(page, "m12-report-metadata.png");
    succeeded = true;
  } finally {
    await finishDebuggingQualification(qualification, reads, succeeded);
  }
}

async function exerciseKnownReportDownloadFailures(
  page: Page,
  reads: BrowserReadTracker,
  registrationId: string,
  runId: string,
  reportId: string,
  expectedArtifacts: Record<
    "json" | "markdown",
    { path: string; hash: string }
  >,
): Promise<void> {
  const path = `/api/v1/projects/${registrationId}/reports/${reportId}/download`;
  const metadataPath = `/api/v1/projects/${registrationId}/reports/${reportId}`;
  await expect(
    page.getByRole("heading", { name: "Saved report", exact: true }),
  ).toBeVisible();
  await expect(page.getByText(reportId, { exact: true })).toBeVisible();
  await expect(page.getByLabel("Pinned report identity")).toBeVisible();
  await reads.waitForIdle();
  let reportPosts = 0;
  const countReportPost = (request: Request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname ===
        `/api/v1/projects/${registrationId}/reports`
    )
      reportPosts += 1;
  };
  page.on("request", countReportPost);
  try {
    let metadataForwarded = 0;
    const metadataRoute = async (route: Route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      const actual = await route.fetch({ maxRetries: 0, maxRedirects: 0 });
      const actualBytes = await actual.body();
      metadataForwarded += 1;
      expect(actual.status()).toBe(200);
      expect(bodySha256(actualBytes)).toMatch(/^[a-f0-9]{64}$/);
      const errorBody = JSON.stringify({
        schema_version: 1,
        error: {
          code: "internal_error",
          message: "Request failed.",
          reason: "storage_io",
        },
      });
      await route.fulfill({
        response: actual,
        status: 503,
        headers: {
          "content-type": "application/json",
          "content-length": String(Buffer.byteLength(errorBody)),
        },
        body: errorBody,
      });
    };
    const metadataMatcher = (url: URL) => url.pathname === metadataPath;
    await page.route(metadataMatcher, metadataRoute);
    try {
      const metadataFailure = await captureResponse(
        page,
        (response) =>
          response.request().method() === "GET" &&
          new URL(response.url()).pathname === metadataPath,
        async () => {
          await page.reload();
        },
      );
      expect(metadataFailure.response.status()).toBe(503);
      await metadataFailure.response.body();
      expect(metadataForwarded).toBe(1);
      await expect(page.getByRole("alert")).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Try again", exact: true }),
      ).toBeEnabled();
    } finally {
      await page.unroute(metadataMatcher, metadataRoute);
    }
    const metadataRecovery = await captureOperation(
      page,
      "readReport",
      { registration_id: registrationId, report_id: reportId },
      () =>
        page.getByRole("button", { name: "Try again", exact: true }).click(),
    );
    const recoveredMetadata = decodeSuccessEnvelope<
      ApiOperationData<"readReport">
    >(metadataRecovery.body, 200, metadataRecovery.response.status());
    expect(recoveredMetadata.report_id).toBe(reportId);
    expect(recoveredMetadata.target_kind).toBe("run");
    expect(recoveredMetadata.raw).toEqual({
      inputs: true,
      requests: false,
      responses: false,
    });
    await expect(page.getByText(reportId, { exact: true })).toBeVisible();
    await expect(page.getByLabel("Pinned report identity")).toBeVisible();
    await reads.waitForIdle();
    expect(reportPosts).toBe(0);

    const cases = [
      "preview-service-unavailable",
      "download-service-unavailable",
      "bad-content-type",
      "oversized",
      "redirect",
    ] as const;
    let previousFormat: "json" | "markdown" = "markdown";
    for (const fault of cases) {
      const format: "json" | "markdown" =
        previousFormat === "json" ? "markdown" : "json";
      previousFormat = format;
      await page
        .getByRole("combobox", { name: "Download format", exact: true })
        .selectOption(format);
      let forwardedCalls = 0;
      const routeHandler = async (route: Route) => {
        const actual = await route.fetch({ maxRetries: 0, maxRedirects: 0 });
        const actualBytes = await actual.body();
        forwardedCalls += 1;
        expect(actual.status()).toBe(200);
        expect(bodySha256(actualBytes)).toMatch(/^[a-f0-9]{64}$/);
        if (
          fault === "preview-service-unavailable" ||
          fault === "download-service-unavailable"
        ) {
          const body = JSON.stringify({
            schema_version: 1,
            error: {
              code: "internal_error",
              message: "Request failed.",
              reason: "storage_io",
            },
          });
          await route.fulfill({
            response: actual,
            status: 503,
            headers: {
              "content-type": "application/json",
              "content-length": String(Buffer.byteLength(body)),
            },
            body,
          });
        } else if (fault === "bad-content-type") {
          await route.fulfill({
            response: actual,
            headers: { "content-type": "application/json" },
            body: actualBytes,
          });
        } else if (fault === "oversized") {
          await route.fulfill({
            response: actual,
            headers: {
              "content-type":
                format === "json"
                  ? "application/octet-stream"
                  : "text/plain; charset=utf-8",
              "content-length": String(8 * 1024 * 1024 + 1),
            },
            body: Buffer.alloc(8 * 1024 * 1024 + 1, 0x61),
          });
        } else {
          await route.fulfill({
            status: 302,
            headers: { location: `${path}?format=${format}` },
            body: "",
          });
        }
      };
      const matcher = (url: URL) =>
        url.pathname === path && url.searchParams.get("format") === format;
      await page.route(matcher, routeHandler);
      try {
        const action =
          fault === "download-service-unavailable"
            ? `Download ${format === "json" ? "JSON" : "Markdown"}`
            : "Preview report bytes";
        const observed = await captureResponse(
          page,
          (response) => {
            const url = new URL(response.url());
            return (
              response.request().method() === "GET" &&
              url.pathname === path &&
              url.searchParams.get("format") === format
            );
          },
          () => page.getByRole("button", { name: action, exact: true }).click(),
        );
        expect(observed.response.status()).toBe(
          fault.includes("service-unavailable")
            ? 503
            : fault === "redirect"
              ? 302
              : 200,
        );
        expect(forwardedCalls).toBe(1);
        await expect(page.getByRole("alert")).toBeVisible();
        await expect(
          page.getByRole("heading", {
            name: "Inert text preview",
            exact: true,
          }),
        ).toHaveCount(0);
        await expect(
          page.getByRole("button", { name: action, exact: true }),
        ).toBeEnabled();
      } finally {
        await page.unroute(matcher, routeHandler);
      }
      const recovered = await captureOperation(
        page,
        "downloadReport",
        { registration_id: registrationId, report_id: reportId },
        () =>
          page
            .getByRole("button", { name: "Preview report bytes", exact: true })
            .click(),
        (query) => query.get("format") === format,
      );
      await assertReportDownload(recovered.response, format);
      const bytes = await recovered.response.body();
      expect(
        await assertExactArtifactBytes(
          bytes,
          expectedArtifacts[format].path,
          expectedArtifacts[format].hash,
        ),
      ).toBe(true);
      expect(new URL(recovered.response.url()).pathname).toBe(path);
    }
    expect(reportPosts).toBe(0);
    await expect(page.getByText(reportId, { exact: true })).toBeVisible();
    await expect(page.getByLabel("Pinned report identity")).toBeVisible();
    await reads.waitForIdle();
    const retained = await captureOperation(
      page,
      "readReport",
      { registration_id: registrationId, report_id: reportId },
      async () => {
        await page
          .getByRole("navigation", { name: "Utilities" })
          .getByRole("button", { name: "Reports", exact: true })
          .click();
        await expect(
          page.getByRole("heading", { name: "Saved reports", exact: true }),
        ).toBeVisible();
        const reportList = page.getByRole("list", { name: "Saved reports" });
        const reportRow = reportList
          .getByRole("listitem")
          .filter({ has: page.getByText(reportId, { exact: true }) });
        await expect(reportRow).toHaveCount(1);
        const targetButton = reportRow.getByRole("button", {
          name: `run: ${runId}`,
          exact: true,
        });
        await expect(targetButton).toHaveCount(1);
        await targetButton.click();
        await expect(
          page.getByRole("heading", { name: "Saved report", exact: true }),
        ).toBeVisible();
      },
    );
    const report = decodeSuccessEnvelope<ApiOperationData<"readReport">>(
      retained.body,
      200,
      retained.response.status(),
    );
    expect(report.report_id).toBe(reportId);
    expect(report.target_kind).toBe("run");
    expect(report.raw).toEqual({
      inputs: true,
      requests: false,
      responses: false,
    });
    await expect(page.getByText(reportId, { exact: true })).toBeVisible();
    await expect(page.getByLabel("Pinned report identity")).toBeVisible();
    await reads.waitForIdle();
    expect(reportPosts).toBe(0);
  } finally {
    page.off("request", countReportPost);
  }
}

async function assertReportDownload(
  response: Response,
  format: "json" | "markdown",
): Promise<void> {
  expect(response.status()).toBe(200);
  const headers = await response.allHeaders();
  expect(headers["content-type"]).toBe(
    format === "json"
      ? "application/octet-stream"
      : "text/plain; charset=utf-8",
  );
  expect(headers["cache-control"]).toContain("no-store");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(
    Number(response.headers()["content-length"] ?? "0"),
  ).toBeLessThanOrEqual(8 * 1024 * 1024);
}

async function importReportWitness(
  qualification: Awaited<
    ReturnType<typeof startDebuggingQualification>
  >["qualification"],
  projectPath: string,
  reportId: string,
  outputPath: string,
): Promise<void> {
  await import("./installed-debugging-support").then(
    ({ invokeReportWitness }) =>
      invokeReportWitness(qualification, projectPath, reportId, outputPath),
  );
}
