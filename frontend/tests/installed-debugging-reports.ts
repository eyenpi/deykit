import { expect, type Page, type Request, type Response, type Route, type TestInfo } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { isAbsolute, join } from "node:path";
import { bodySha256 } from "./installed-debugging-support";
import type { ApiOperationData } from "../src/api/client";
import {
  assertExactArtifactBytes,
  captureResponse,
  captureOperation,
  decodeSuccessEnvelope,
  finishDebuggingQualification,
  installLostAcknowledgement,
  invokeReportWitness,
  openPreparedProject,
  readReportWitness,
  startDebuggingQualification,
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
type Target = { kind: ReportKind; id: string; rawMode?: RawMode; groupSnapshotId?: string; reportId?: string; jsonHash?: string; markdownHash?: string };

async function openReportPage(page: Page, registrationId: string): Promise<void> {
  const response = await captureOperation(
    page,
    "listReports",
    { registration_id: registrationId },
    async () => {
      await page.getByRole("button", { name: "Reports", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Saved reports", exact: true })).toBeVisible();
    },
  );
  decodeSuccessEnvelope<ApiOperationData<"listReports">>(await response.response.body(), 200, response.response.status());
}

export async function runReportsWorkflow(page: Page, testInfo: TestInfo): Promise<void> {
  const context = await startDebuggingQualification(page, testInfo, "R");
  const { qualification, registrationId, reads } = context;
  let succeeded = false;
  try {
    await qualification.enterPhase("admit-c-and-g-evidence");
    const evidencePath = qualification.sourceEvidencePath;
    const secondaryPath = qualification.secondaryProjectPath;
    if (!evidencePath || !secondaryPath) throw new Error("Paired source evidence was unavailable.");
    const sourceEvidence = object(JSON.parse(await readFile(evidencePath, "utf8")));
    if (sourceEvidence.workflow !== "G" || sourceEvidence.status !== "passed")
      throw new Error("The imported G workflow evidence was not accepted.");
    if (typeof sourceEvidence.playwright_output_path !== "string" || !isAbsolute(sourceEvidence.playwright_output_path))
      throw new Error("The imported G progress location was invalid.");
    const gOutput = sourceEvidence.playwright_output_path;
    const gProgress = object(JSON.parse(await readFile(join(gOutput, "debugging-progress.json"), "utf8")));
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
    qualification.setWitness("G_diagnostic_snapshot_id", diagnosticSnapshot);
    qualification.setWitness("G_check_snapshot_id", checkSnapshot);

    await qualification.enterPhase("read-c-comparison");
    const comparisonResponse = await captureOperation(
      page,
      "listComparisons",
      { registration_id: registrationId },
      async () => {
        await page.getByRole("button", { name: "Comparisons", exact: true }).click();
        await expect(page.getByRole("heading", { name: "Comparisons", exact: true })).toBeVisible();
      },
    );
    const comparisons = decodeSuccessEnvelope<ApiOperationData<"listComparisons">>(
      await comparisonResponse.response.body(), 200, comparisonResponse.response.status(),
    );
    const forward = comparisons.items.filter((item) =>
      item.left_evaluation_id === qualification.seedMetadata.evaluation_id &&
      item.outcomes.primary_counts.improved === "1" &&
      item.outcomes.primary_counts.regressed === "0",
    );
    expect(forward).toHaveLength(1);
    const comparisonId = safeId(forward[0]?.comparison_id);
    qualification.setWitness("comparison_id", comparisonId);
    await reads.waitForIdle();

    const cTargets: Target[] = [
      { kind: "run", id: qualification.seedMetadata.run_id, rawMode: "inputs" },
      { kind: "evaluation", id: qualification.seedMetadata.evaluation_id, rawMode: "requests" },
      { kind: "comparison", id: comparisonId, rawMode: "responses" },
    ];
    let replayUsed = false;
    for (const target of cTargets) {
      await qualification.enterPhase("create-c-" + target.kind + "-report");
      await openReportPage(page, registrationId);
      await page.getByRole("button", { name: "Create report from verified target", exact: true }).click();
      const dialog = page.getByRole("dialog", { name: "Create a pinned report", exact: true });
      await dialog.getByLabel("Target kind", { exact: true }).selectOption(target.kind);
      await dialog.getByLabel("Target ID", { exact: true }).fill(target.id);
      const operation = target.kind === "run" ? "readRun" : target.kind === "evaluation" ? "readEvaluation" : "readComparison";
      const params = target.kind === "run"
        ? { registration_id: registrationId, run_id: target.id }
        : target.kind === "evaluation"
          ? { registration_id: registrationId, evaluation_id: target.id }
          : { registration_id: registrationId, comparison_id: target.id };
      const verified = await captureOperation(
        page,
        operation,
        params,
        () => dialog.getByRole("button", { name: "Verify saved target", exact: true }).click(),
      );
      expect(verified.response.status()).toBe(200);
      await verified.response.body();
      await expect(dialog.getByRole("pre", { name: "Verified report target" })).toBeVisible();
      for (const raw of ["Include raw inputs", "Include raw requests", "Include raw responses"])
        await expect(dialog.getByLabel(raw, { exact: true })).not.toBeChecked();
      const expectedRaw = {
        inputs: target.rawMode === "inputs",
        requests: target.rawMode === "requests",
        responses: target.rawMode === "responses",
      };
      if (target.rawMode) {
        const label = `Include raw ${target.rawMode}`;
        await dialog.getByLabel(label, { exact: true }).check();
      }

      const lost = replayUsed ? undefined : await installLostAcknowledgement(page, "/api/v1/projects/" + registrationId + "/reports", 200);
      try {
        const reportReadPromise = page.waitForResponse((response) => {
          const url = new URL(response.url());
          return response.request().method() === "GET" &&
            url.pathname.startsWith("/api/v1/projects/" + registrationId + "/reports/") &&
            !url.pathname.endsWith("/download");
        }, { timeout: 12_000 });
        void reportReadPromise.catch(() => undefined);
        let reportId = "";
        if (lost) {
          await dialog.getByRole("button", { name: "Create report", exact: true }).click();
          await expect(dialog.getByRole("button", { name: "Retry original unchanged report", exact: true })).toBeVisible();
          expect(lost.firstObservation()?.firstStatus).toBe(200);
          await dialog.getByRole("button", { name: "Retry original unchanged report", exact: true }).click();
          const observed = lost.observation();
          expect(observed?.replayStatus).toBe(200);
          expect(observed?.sameRequestBytes).toBe(true);
          const first = decodeSuccessEnvelope<ApiOperationData<"createReport">>(observed?.firstResponseBody ?? Buffer.alloc(0), 200, observed?.firstStatus ?? 0);
          const receipt = decodeSuccessEnvelope<ApiOperationData<"createReport">>(observed?.replayResponseBody ?? Buffer.alloc(0), 200, observed?.replayStatus ?? 0);
          expect(receipt.report_id).toBe(first.report_id);
          expect(first.raw).toEqual(expectedRaw);
          expect(receipt.raw).toEqual(expectedRaw);
          expect(first.replayed).toBe(false);
          expect(receipt.replayed).toBe(true);
          reportId = receipt.report_id;
          replayUsed = true;
          qualification.setWitness("report_create_request_sha256", observed?.firstRequestHash ?? "");
        } else {
          const created = await captureOperation(
            page,
            "createReport",
            { registration_id: registrationId },
            () => dialog.getByRole("button", { name: "Create report", exact: true }).click(),
          );
          const receipt = decodeSuccessEnvelope<ApiOperationData<"createReport">>(await created.response.body(), 200, created.response.status());
          expect(receipt.target_kind).toBe(target.kind);
          expect(receipt.target_id).toBe(target.id);
          expect(receipt.replayed).toBe(false);
          expect(receipt.raw).toEqual(expectedRaw);
          reportId = receipt.report_id;
        }
        qualification.setWitness(target.kind + "_report_id", reportId);
        const metadataResponse = await reportReadPromise;
        expect(new URL(metadataResponse.url()).pathname).toBe("/api/v1/projects/" + registrationId + "/reports/" + reportId);
        const metadataBody = await metadataResponse.body();
        await expect(page.getByRole("heading", { name: "Saved report", exact: true })).toBeVisible();
        const report = decodeSuccessEnvelope<ApiOperationData<"readReport">>(metadataBody, 200, metadataResponse.status());
        expect(report.report_id).toBe(reportId);
        expect(report.target_kind).toBe(target.kind);
        expect(report.target_id).toBe(target.id);
        expect(report.raw).toEqual(expectedRaw);
        await reads.waitForIdle();
        const witnessPath = testInfo.outputPath("report-" + reportId + "-witness.json");
        await invokeReportWitness(qualification, qualification.projectPath, reportId, witnessPath);
        const witness = await readReportWitness(witnessPath, reportId);
        for (const format of ["json", "markdown"] as const) {
          await page.getByLabel("Download format", { exact: true }).selectOption(format);
          const response = await captureOperation(
            page,
            "downloadReport",
            { registration_id: registrationId, report_id: reportId },
            () => page.getByRole("button", { name: "Preview report bytes", exact: true }).click(),
            (query) => query.get("format") === format,
          );
          await assertReportDownload(response.response, format);
          const bytes = await response.response.body();
          expect(bytes.byteLength).toBeLessThanOrEqual(8 * 1024 * 1024);
          const expected = witness[format];
          expect(await assertExactArtifactBytes(bytes, join(testInfo.outputDir, expected.file), expected.bytes_hash)).toBe(true);
          qualification.setWitness(target.kind + "_report_" + format + "_sha256", expected.bytes_hash);
          await expect(page.getByRole("status").filter({ hasText: "Read " + bytes.byteLength + " report bytes as " + format })).toBeVisible();
        }
        if (target.kind === "run")
          await exerciseKnownReportDownloadFailures(
            page,
            registrationId,
            reportId,
            {
              json: { path: join(testInfo.outputDir, witness.json.file), hash: witness.json.bytes_hash },
              markdown: { path: join(testInfo.outputDir, witness.markdown.file), hash: witness.markdown.bytes_hash },
            },
          );
      } finally {
        await lost?.dispose();
      }
      await reads.waitForIdle();
    }

    await qualification.enterPhase("read-g-saved-report-bytes");
    const gProject = await openPreparedProject(page, secondaryPath);
    for (const target of [
      { kind: "diagnostic" as const, id: diagnosticGroup, snapshot: diagnosticSnapshot, reportId: diagnosticReportId, hashes: diagnosticHashes },
      { kind: "check" as const, id: checkGroup, snapshot: checkSnapshot, reportId: checkReportId, hashes: checkHashes },
    ]) {
      const reportRead = await captureOperation(
        page,
        "readReport",
        { registration_id: gProject.registrationId, report_id: target.reportId },
        async () => {
          if (!(await page.getByRole("heading", { name: "Saved reports", exact: true }).isVisible().catch(() => false))) {
            await page.getByRole("button", { name: "Reports", exact: true }).click();
            await expect(page.getByRole("heading", { name: "Saved reports", exact: true })).toBeVisible();
          }
          const existing = page.getByRole("button", { name: new RegExp("^" + target.kind + ": " + target.id) });
          await existing.click();
          await expect(page.locator('pre[aria-label="Pinned report identity"]')).toContainText(target.snapshot);
        },
      );
      const report = decodeSuccessEnvelope<ApiOperationData<"readReport">>(await reportRead.response.body(), 200, reportRead.response.status());
      expect(report.report_id).toBe(target.reportId);
      expect(report.target_kind).toBe(target.kind);
      expect(report.target_id).toBe(target.id);
      expect(target.kind === "diagnostic" ? report.diagnostic_snapshot_id : report.check_snapshot_id).toBe(target.snapshot);
      await reads.waitForIdle();
      const witnessPath = testInfo.outputPath("imported-" + target.reportId + "-witness.json");
      await importReportWitness(qualification, secondaryPath, target.reportId, witnessPath);
      const witness = await readReportWitness(witnessPath, target.reportId);
      expect(witness.json.bytes_hash).toBe(target.hashes.json);
      expect(witness.markdown.bytes_hash).toBe(target.hashes.markdown);
      for (const format of ["json", "markdown"] as const) {
        await page.getByLabel("Download format", { exact: true }).selectOption(format);
        const download = await captureOperation(
          page,
          "downloadReport",
          { registration_id: gProject.registrationId, report_id: target.reportId },
          () => page.getByRole("button", { name: "Preview report bytes", exact: true }).click(),
          (query) => query.get("format") === format,
        );
        await assertReportDownload(download.response, format);
        const bytes = await download.response.body();
        expect(await assertExactArtifactBytes(bytes, join(testInfo.outputDir, witness[format].file), witness[format].bytes_hash)).toBe(true);
        expect(witness[format].bytes_hash).toBe(format === "json" ? target.hashes.json : target.hashes.markdown);
      }
      await reads.waitForIdle();
    }
    await qualification.enterPhase("zero-new-report-dispatches");
    const counts = await waitForCountFile(qualification.controlDirectory, (value) => value.fixture_dispatch_calls === 0 && value.for_case_calls === 0 && value.live_dispatch_calls === 0);
    expect(counts).toMatchObject({ fixture_dispatch_calls: 0, for_case_calls: 0, live_dispatch_calls: 0 });
    qualification.setCounts(counts);
    await page.getByRole("button", { name: "Sandbox", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Sandbox", exact: true })).toBeVisible();
    await qualification.captureScreenshot(page, "m12-report-metadata.png");
    succeeded = true;
  } finally {
    await finishDebuggingQualification(qualification, reads, succeeded);
  }
}

async function exerciseKnownReportDownloadFailures(
  page: Page,
  registrationId: string,
  reportId: string,
  expectedArtifacts: Record<"json" | "markdown", { path: string; hash: string }>,
): Promise<void> {
  const path = `/api/v1/projects/${registrationId}/reports/${reportId}/download`;
  let reportPosts = 0;
  const countReportPost = (request: Request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === `/api/v1/projects/${registrationId}/reports`)
      reportPosts += 1;
  };
  page.on("request", countReportPost);
  try {
    const cases = [
      "preview-service-unavailable",
      "download-service-unavailable",
      "bad-content-type",
      "oversized",
      "redirect",
    ] as const;
    let previousFormat: "json" | "markdown" = "markdown";
    for (const fault of cases) {
      const format = previousFormat === "json" ? "markdown" : "json";
      previousFormat = format;
      await page.getByLabel("Download format", { exact: true }).selectOption(format);
      const routeHandler = async (route: Route) => {
        const actual = await route.fetch({ maxRetries: 0, maxRedirects: 0 });
        const actualBytes = await actual.body();
        expect(actual.status()).toBe(200);
        expect(bodySha256(actualBytes)).toMatch(/^[a-f0-9]{64}$/);
        if (fault === "preview-service-unavailable" || fault === "download-service-unavailable") {
          const body = JSON.stringify({
            schema_version: 1,
            error: { code: "internal_error", message: "Request failed.", reason: "storage_io" },
          });
          await route.fulfill({
            response: actual,
            status: 503,
            headers: { "content-type": "application/json", "content-length": String(Buffer.byteLength(body)) },
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
              "content-type": "application/octet-stream",
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
      const matcher = (url: URL) => url.pathname === path && url.searchParams.get("format") === format;
      await page.route(matcher, routeHandler);
      try {
        const action = fault === "download-service-unavailable"
          ? `Download ${format === "json" ? "JSON" : "Markdown"}`
          : "Preview report bytes";
        const observed = await captureResponse(
          page,
          (response) => {
            const url = new URL(response.url());
            return response.request().method() === "GET" && url.pathname === path && url.searchParams.get("format") === format;
          },
          () => page.getByRole("button", { name: action, exact: true }).click(),
        );
        expect(observed.response.status()).toBe(
          fault.includes("service-unavailable") ? 503 : fault === "redirect" ? 302 : 200,
        );
        await expect(page.getByRole("alert")).toBeVisible();
        await expect(page.getByRole("heading", { name: "Inert text preview", exact: true })).toHaveCount(0);
        await expect(page.getByRole("button", { name: action, exact: true })).toBeEnabled();
      } finally {
        await page.unroute(matcher, routeHandler);
      }
      const recovered = await captureOperation(
        page,
        "downloadReport",
        { registration_id: registrationId, report_id: reportId },
        () => page.getByRole("button", { name: "Preview report bytes", exact: true }).click(),
        (query) => query.get("format") === format,
      );
      await assertReportDownload(recovered.response, format);
      const bytes = await recovered.response.body();
      expect(await assertExactArtifactBytes(bytes, expectedArtifacts[format].path, expectedArtifacts[format].hash)).toBe(true);
      expect(new URL(recovered.response.url()).pathname).toBe(path);
    }
    expect(reportPosts).toBe(0);
    const retained = await captureOperation(
      page,
      "readReport",
      { registration_id: registrationId, report_id: reportId },
      async () => {
        await page.getByRole("button", { name: "Reports", exact: true }).click();
        await expect(page.getByRole("heading", { name: "Saved reports", exact: true })).toBeVisible();
        await page.getByRole("button", { name: new RegExp(`^run: ${reportId}`) }).click();
        await expect(page.getByRole("heading", { name: "Saved report", exact: true })).toBeVisible();
      },
    );
    const report = decodeSuccessEnvelope<ApiOperationData<"readReport">>(retained.body, 200, retained.response.status());
    expect(report.report_id).toBe(reportId);
    expect(report.target_kind).toBe("run");
    expect(report.raw).toEqual({ inputs: true, requests: false, responses: false });
    expect(reportPosts).toBe(0);
  } finally {
    page.off("request", countReportPost);
  }
}

async function assertReportDownload(response: Response, format: "json" | "markdown"): Promise<void> {
  expect(response.status()).toBe(200);
  const headers = await response.allHeaders();
  expect(headers["content-type"]).toBe(format === "json" ? "application/octet-stream" : "text/plain; charset=utf-8");
  expect(headers["cache-control"]).toContain("no-store");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(Number(response.headers()["content-length"] ?? "0")).toBeLessThanOrEqual(8 * 1024 * 1024);
}

async function importReportWitness(qualification: Awaited<ReturnType<typeof startDebuggingQualification>>["qualification"], projectPath: string, reportId: string, outputPath: string): Promise<void> {
  await import("./installed-debugging-support").then(({ invokeReportWitness }) => invokeReportWitness(qualification, projectPath, reportId, outputPath));
}
