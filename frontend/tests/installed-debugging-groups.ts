import { expect, type Page, type TestInfo } from "@playwright/test";
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { writeFile } from "node:fs/promises";
import type { ApiOperationData } from "../src/api/client";
import {
  captureOperation,
  assertCreateReportRequestBody,
  bodySha256,
  assertExactArtifactBytes,
  decodeSuccessEnvelope,
  finishDebuggingQualification,
  installLostAcknowledgement,
  readFixtureCountsNow,
  saveServerResumeTrace,
  startDebuggingQualification,
  waitForAnyBarrierEntry,
  waitForCountFile,
  createFixtureHold,
  invokeReportWitness,
  readReportWitness,
  settleOnSandbox,
} from "./installed-debugging-support";

const RE_ADDED_CASE_SOURCE = '"A deliberately different newly re-added input."';

async function readdSameCaseWithInstalledCli(
  qualification: Awaited<
    ReturnType<typeof startDebuggingQualification>
  >["qualification"],
): Promise<{ contentHash: string }> {
  const binary = join(dirname(qualification.installedPython), "deykit");
  const args = [
    "--project",
    qualification.projectPath,
    "--json",
    "case",
    "add",
    "--dataset",
    qualification.seedMetadata.dataset_id,
    "--id",
    "ex-003",
    "--stdin",
    "--operation-id",
    "m12_same_id_readd",
  ];
  const env = Object.fromEntries(
    Object.entries(process.env).filter(
      ([key]) => key !== "PYTHONPATH" && !key.startsWith("JEV_"),
    ),
  );
  const child = spawn(binary, args, {
    cwd: qualification.projectPath,
    env,
    stdio: ["pipe", "pipe", "pipe"],
  });
  const stdout: Buffer[] = [];
  let outputSize = 0;
  let timedOut = false;
  let oversized = false;
  let forceKillTimer: ReturnType<typeof setTimeout> | undefined;
  const terminate = () => {
    child.kill("SIGTERM");
    forceKillTimer ??= setTimeout(() => child.kill("SIGKILL"), 1_000);
  };
  const timer = setTimeout(() => {
    timedOut = true;
    terminate();
  }, 30_000);
  child.stdout.on("data", (chunk: Buffer) => {
    outputSize += chunk.byteLength;
    if (outputSize > 256 * 1024) {
      oversized = true;
      terminate();
      return;
    }
    stdout.push(Buffer.from(chunk));
  });
  child.stderr.resume();
  child.stdin.end(
    JSON.stringify({
      input_kind: "text",
      input_source: RE_ADDED_CASE_SOURCE,
      tags: [],
      split: "development",
    }),
  );
  const exit = await new Promise<{
    code: number | null;
    signal: NodeJS.Signals | null;
  }>((resolve, reject) => {
    child.once("error", () =>
      reject(new Error("The installed case re-add command could not start.")),
    );
    child.once("close", (code, signal) => resolve({ code, signal }));
  }).finally(() => {
    clearTimeout(timer);
    if (forceKillTimer !== undefined) clearTimeout(forceKillTimer);
  });
  if (timedOut || oversized || exit.code !== 0 || exit.signal !== null)
    throw new Error(
      "The bounded installed case re-add command did not complete successfully.",
    );
  let parsed: unknown;
  try {
    parsed = JSON.parse(Buffer.concat(stdout).toString("utf8"));
  } catch {
    throw new Error("The installed case re-add receipt was not valid JSON.");
  }
  const envelope = object(parsed);
  const data = object(envelope.data);
  const result = object(data.result);
  const record = object(result.record);
  const etag = result.etag;
  if (
    envelope.schema_version !== 1 ||
    record.id !== "ex-003" ||
    typeof etag !== "string" ||
    !/^[a-f0-9]{64}$/.test(etag)
  )
    throw new Error(
      "The installed case re-add receipt did not match the requested case.",
    );
  return { contentHash: etag };
}

async function downloadReportBytes(
  page: Page,
  registrationId: string,
  reportId: string,
  format: "json" | "markdown",
): Promise<Buffer> {
  await page
    .getByRole("combobox", { name: "Download format", exact: true })
    .selectOption(format);
  const response = await captureOperation(
    page,
    "downloadReport",
    { registration_id: registrationId, report_id: reportId },
    () =>
      page
        .getByRole("button", { name: "Preview report bytes", exact: true })
        .click(),
    (query) => query.get("format") === format,
  );
  expect(response.response.status()).toBe(200);
  const headers = await response.response.allHeaders();
  expect(headers["content-type"]).toBe(
    format === "json"
      ? "application/octet-stream"
      : "text/plain; charset=utf-8",
  );
  expect(headers["cache-control"]).toContain("no-store");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(response.body.byteLength).toBeLessThanOrEqual(8 * 1024 * 1024);
  return response.body;
}

async function editDeleteAndReaddCaseThroughPublicInterfaces(
  page: Page,
  qualification: Awaited<
    ReturnType<typeof startDebuggingQualification>
  >["qualification"],
  registrationId: string,
  waitForIdle: () => Promise<void>,
): Promise<{
  originalRecordHash: string;
  editedRecordHash: string;
  readdedRecordHash: string;
}> {
  const datasetId = qualification.seedMetadata.dataset_id;
  await page
    .getByRole("button", { name: "Project examples", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Examples", exact: true }),
  ).toBeVisible();
  const dataset = page.getByRole("combobox", {
    name: "Dataset",
    exact: true,
  });
  if ((await dataset.inputValue()) !== datasetId) {
    if (await dataset.inputValue()) await dataset.selectOption("");
    const caseList = await captureOperation(
      page,
      "list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get",
      { registration_id: registrationId, dataset_id: datasetId },
      async () => {
        await dataset.selectOption(datasetId);
      },
    );
    const listed = decodeSuccessEnvelope<
      ApiOperationData<"list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get">
    >(caseList.body, 200, caseList.response.status());
    expect(listed.items.some((item) => item.record.id === "ex-003")).toBe(true);
  }
  const casesTable = page.getByRole("table", { name: /^Cases in / });
  await expect(
    casesTable.getByRole("button", { name: "ex-003", exact: true }),
  ).toBeVisible();
  const selected = await captureOperation(
    page,
    "read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get",
    {
      registration_id: registrationId,
      dataset_id: datasetId,
      case_id: "ex-003",
    },
    () =>
      casesTable.getByRole("button", { name: "ex-003", exact: true }).click(),
  );
  const original = decodeSuccessEnvelope<
    ApiOperationData<"read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get">
  >(selected.body, 200, selected.response.status());
  const originalRecordHash = original.case.etag;
  expect(original.case.record.id).toBe("ex-003");

  await page.getByRole("button", { name: "Edit input", exact: true }).click();
  const editDialog = page.getByRole("dialog", {
    name: "Edit ex-003",
    exact: true,
  });
  await expect(editDialog).toBeVisible();
  await editDialog
    .getByLabel("Input source", { exact: true })
    .fill('"A deliberately edited intermediate input."');
  const editResponse = await captureOperation(
    page,
    "edit_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__put",
    {
      registration_id: registrationId,
      dataset_id: datasetId,
      case_id: "ex-003",
    },
    () =>
      editDialog
        .getByRole("button", { name: "Save input", exact: true })
        .click(),
  );
  const editReceipt = decodeSuccessEnvelope<
    ApiOperationData<"edit_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__put">
  >(editResponse.body, 200, editResponse.response.status());
  const editedCase = editReceipt.case;
  if (!editedCase)
    throw new Error("The installed case edit receipt omitted its case.");
  expect(editedCase.record.id).toBe("ex-003");
  const editedRecordHash = editedCase.etag;
  expect(editedRecordHash).not.toBe(originalRecordHash);
  await expect(editDialog).toBeHidden();
  await expect(
    casesTable.getByRole("button", { name: "ex-003", exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Remove case", exact: true }).click();
  const removeDialog = page.getByRole("dialog", {
    name: "Remove ex-003?",
    exact: true,
  });
  const removal = await captureOperation(
    page,
    "delete_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__delete",
    {
      registration_id: registrationId,
      dataset_id: datasetId,
      case_id: "ex-003",
    },
    () =>
      removeDialog
        .getByRole("button", { name: "Remove case", exact: true })
        .click(),
  );
  const removed = decodeSuccessEnvelope<
    ApiOperationData<"delete_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__delete">
  >(removal.body, 200, removal.response.status());
  expect(removed.case).toBeNull();
  await expect(
    casesTable.getByRole("button", { name: "ex-003", exact: true }),
  ).toHaveCount(0);

  // Avoid holding the group detail's periodic source reads while the explicit
  // installed CLI mutation reuses the deleted ID.
  await page.getByRole("button", { name: "Sandbox", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sandbox", exact: true }),
  ).toBeVisible();
  await qualification.setWitness(
    "same_id_readd_original_hash",
    originalRecordHash,
  );
  await qualification.setWitness("same_id_readd_edited_hash", editedRecordHash);
  await waitForIdle();
  const added = await readdSameCaseWithInstalledCli(qualification);
  expect(added.contentHash).not.toBe(originalRecordHash);
  expect(added.contentHash).not.toBe(editedRecordHash);
  const addedEquality =
    added.contentHash !== originalRecordHash &&
    added.contentHash !== editedRecordHash;
  qualification.setEquality("same_id_readd_hash_changed", addedEquality);
  await qualification.setWitness("same_id_readd_hash", added.contentHash);

  await page
    .getByRole("button", { name: "Project examples", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Examples", exact: true }),
  ).toBeVisible();
  const reloadedDataset = page.getByRole("combobox", {
    name: "Dataset",
    exact: true,
  });
  if ((await reloadedDataset.inputValue()) !== datasetId) {
    if (await reloadedDataset.inputValue())
      await reloadedDataset.selectOption("");
    const caseList = await captureOperation(
      page,
      "list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get",
      { registration_id: registrationId, dataset_id: datasetId },
      async () => {
        await reloadedDataset.selectOption(datasetId);
      },
    );
    decodeSuccessEnvelope<
      ApiOperationData<"list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get">
    >(caseList.body, 200, caseList.response.status());
  } else {
    const reload = page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        new URL(response.url()).pathname ===
          `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases`,
      { timeout: 12_000 },
    );
    void reload.catch(() => undefined);
    await page.reload();
    const caseList = await reload;
    decodeSuccessEnvelope<
      ApiOperationData<"list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get">
    >(await caseList.body(), 200, caseList.status());
  }
  const refreshedTable = page.getByRole("table", { name: /^Cases in / });
  const casePath = `/api/v1/projects/${registrationId}/datasets/${datasetId}/cases/ex-003`;
  const labelPath = `/api/v1/projects/${registrationId}/decisions/${qualification.seedMetadata.decision_id}/datasets/${datasetId}/labels/ex-003`;
  const caseReadPromise = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      new URL(response.url()).pathname === casePath,
    { timeout: 12_000 },
  );
  const labelReadPromise = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      new URL(response.url()).pathname === labelPath,
    { timeout: 12_000 },
  );
  void caseReadPromise.catch(() => undefined);
  void labelReadPromise.catch(() => undefined);
  await refreshedTable
    .getByRole("button", { name: "ex-003", exact: true })
    .click();
  const [caseResponse, labelResponse] = await Promise.all([
    caseReadPromise,
    labelReadPromise,
  ]);
  const [caseBody, labelBody] = await Promise.all([
    caseResponse.body(),
    labelResponse.body(),
  ]);
  const current = decodeSuccessEnvelope<
    ApiOperationData<"read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get">
  >(caseBody, 200, caseResponse.status());
  expect(current.case.record.id).toBe("ex-003");
  expect(current.case.etag).toBe(added.contentHash);
  expect(current.case.record.input_source).toBe(RE_ADDED_CASE_SOURCE);
  expect(current.case.etag).not.toBe(originalRecordHash);
  const currentLabel = decodeSuccessEnvelope<
    ApiOperationData<"read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get">
  >(labelBody, 200, labelResponse.status());
  expect(currentLabel.label).toBeNull();
  return {
    originalRecordHash,
    editedRecordHash,
    readdedRecordHash: added.contentHash,
  };
}

async function setReaddedCaseCurrentLabel(
  page: Page,
  qualification: Awaited<
    ReturnType<typeof startDebuggingQualification>
  >["qualification"],
  registrationId: string,
  waitForIdle: () => Promise<void>,
): Promise<void> {
  const datasetId = qualification.seedMetadata.dataset_id;
  await page
    .getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: "Content category", exact: true })
    .click();
  await expect(page.getByLabel("Decision name", { exact: true })).toHaveValue(
    "Content category",
  );
  await page
    .getByRole("navigation", { name: "Workspace" })
    .getByRole("button", { name: "Examples", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Examples", exact: true }),
  ).toBeVisible();
  const dataset = page.getByRole("combobox", {
    name: "Dataset",
    exact: true,
  });
  if ((await dataset.inputValue()) !== datasetId)
    await dataset.selectOption(datasetId);
  const casesTable = page.getByRole("table", { name: /^Cases in / });
  const currentLabelRead = await captureOperation(
    page,
    "read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get",
    {
      registration_id: registrationId,
      decision_id: qualification.seedMetadata.decision_id,
      dataset_id: datasetId,
      case_id: "ex-003",
    },
    () =>
      casesTable.getByRole("button", { name: "ex-003", exact: true }).click(),
  );
  const currentLabel = decodeSuccessEnvelope<
    ApiOperationData<"read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get">
  >(currentLabelRead.body, 200, currentLabelRead.response.status());
  await waitForIdle();
  const previousAnswers = currentLabel.label?.acceptable_option_ids ?? [];
  const nextAnswers =
    previousAnswers.length === 1 && previousAnswers[0] === "question"
      ? ["report"]
      : ["question"];
  const answers = page.getByRole("group", {
    name: "Expected answers",
    exact: true,
  });
  const question = answers.getByLabel("Question", { exact: true });
  const report = answers.getByLabel("Report", { exact: true });
  await expect(question).toBeVisible();
  if (nextAnswers.includes("question")) {
    if (await report.isChecked()) await report.uncheck();
    if (!(await question.isChecked())) await question.check();
  } else {
    if (await question.isChecked()) await question.uncheck();
    if (!(await report.isChecked())) await report.check();
  }
  const save = answers.getByRole("button", {
    name: "Save expected answer",
    exact: true,
  });
  const saved = await captureOperation(
    page,
    "batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post",
    {
      registration_id: registrationId,
      decision_id: qualification.seedMetadata.decision_id,
      dataset_id: datasetId,
    },
    () => save.click(),
  );
  const receipt = decodeSuccessEnvelope<
    ApiOperationData<"batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post">
  >(saved.body, 200, saved.response.status());
  expect(receipt.changes).toHaveLength(1);
  expect(receipt.changes[0]?.case_id).toBe("ex-003");
  expect(receipt.changes[0]?.label?.acceptable_option_ids).toEqual(nextAnswers);
  expect(receipt.changes[0]?.label?.acceptable_option_ids).not.toEqual(
    previousAnswers,
  );
  await expect(
    page.getByRole("status").filter({ hasText: "Applicable" }),
  ).toBeVisible();
}

async function openSavedReport(
  page: Page,
  registrationId: string,
  kind: "diagnostic" | "check",
  targetId: string,
  reportId: string,
): Promise<void> {
  const listRead = await captureOperation(
    page,
    "listReports",
    { registration_id: registrationId },
    async () => {
      if (
        await page
          .getByRole("heading", { name: "Saved reports", exact: true })
          .isVisible()
          .catch(() => false)
      )
        await page.reload();
      else
        await page
          .getByRole("navigation", { name: "Utilities" })
          .getByRole("button", { name: "Reports", exact: true })
          .click();
      await expect(
        page.getByRole("heading", { name: "Saved reports", exact: true }),
      ).toBeVisible();
    },
  );
  const savedPage = decodeSuccessEnvelope<ApiOperationData<"listReports">>(
    listRead.body,
    200,
    listRead.response.status(),
  );
  expect(savedPage.total).toBe(String(savedPage.items.length));
  expect(
    savedPage.items.filter((item) => item.report_id === reportId),
  ).toHaveLength(1);
  const reportList = page.getByRole("list", { name: "Saved reports" });
  const reportRow = reportList
    .getByRole("listitem")
    .filter({ has: page.getByText(reportId, { exact: true }) });
  await expect(reportRow).toHaveCount(1);
  const reportButton = reportRow.getByRole("button", {
    name: `${kind}: ${targetId}`,
    exact: true,
  });
  await expect(reportButton).toHaveCount(1);
  await captureOperation(
    page,
    "readReport",
    { registration_id: registrationId, report_id: reportId },
    async () => {
      await reportButton.click();
      await expect(
        page.getByRole("heading", { name: "Saved report", exact: true }),
      ).toBeVisible();
    },
  ).then(async ({ response, body }) => {
    const saved = decodeSuccessEnvelope<ApiOperationData<"readReport">>(
      body,
      200,
      response.status(),
    );
    expect(saved.report_id).toBe(reportId);
    expect(saved.target_kind).toBe(kind);
    expect(saved.target_id).toBe(targetId);
    expect(saved.raw).toEqual({
      inputs: false,
      requests: false,
      responses: false,
    });
  });
}

function object(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    throw new Error("The installed API returned an unexpected object.");
  return value as Record<string, unknown>;
}

function countText(value: unknown): string {
  if (typeof value !== "string" || !/^(?:0|[1-9][0-9]*)$/.test(value))
    throw new Error("The installed API returned an invalid count.");
  return value;
}

async function addIndependentRegression(
  page: Page,
  registrationId: string,
  decisionId: string,
  runId: string,
  resultSnapshotId: string,
): Promise<string> {
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
    await runs.response.body(),
    200,
    runs.response.status(),
  );
  expect(runPage.items.some((item) => item.run_id === runId)).toBe(true);
  const runButton = page.getByRole("button", { name: runId, exact: true });
  await runButton.click();
  const row = page
    .getByRole("table", { name: "Frozen result rows" })
    .getByRole("row")
    .filter({ hasText: "ex-003" });
  await row.getByRole("button", { name: "ex-003", exact: true }).click();
  const inspector = page.getByRole("region", {
    name: "Case ex-003 inspection",
  });
  const dialogPromise = page.getByRole("dialog", {
    name: `Add regression example for ${decisionId}`,
    exact: true,
  });
  await inspector
    .getByRole("button", { name: "Add regression example", exact: true })
    .click();
  const dialog = dialogPromise;
  await expect(dialog).toBeVisible();
  const question = dialog.getByLabel("Question · question", { exact: true });
  const report = dialog.getByLabel("Report · report", { exact: true });
  const acceptableOptions = dialog
    .getByRole("group", { name: "Human-reviewed acceptable options" })
    .getByRole("checkbox");
  expect(
    await acceptableOptions.evaluateAll(
      (inputs) =>
        inputs.filter((input) => (input as HTMLInputElement).checked).length,
    ),
  ).toBe(0);
  await expect(question).not.toBeChecked();
  await expect(report).not.toBeChecked();
  await question.check();
  await dialog
    .getByLabel("Reason", { exact: true })
    .fill(
      "Independent expectation recorded after reviewing the frozen result.",
    );
  const response = await captureOperation(
    page,
    "addRegression",
    { registration_id: registrationId, decision_id: decisionId },
    () =>
      dialog
        .getByRole("button", { name: "Save regression example", exact: true })
        .click(),
  );
  const receipt = decodeSuccessEnvelope<ApiOperationData<"addRegression">>(
    await response.response.body(),
    200,
    response.response.status(),
  );
  expect(receipt.source_run_id).toBe(runId);
  expect(receipt.source_result_snapshot_id).toBe(resultSnapshotId);
  expect(receipt.case_id).toBe("ex-003");
  expect(receipt.provenance).toBe("human");
  expect(receipt.acceptable_option_ids).toEqual(["question"]);
  await dialog.getByRole("button", { name: "Close", exact: true }).click();
  await expect(dialog).toBeHidden();
  return receipt.regression_id;
}

async function openDiagnosticReview(
  page: Page,
  registrationId: string,
  fixtureSetId: string,
  datasetId: string,
  caseIds: readonly string[],
  seed: string,
) {
  await page
    .getByRole("button", {
      name: "Preview choice-order diagnostic",
      exact: true,
    })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Review choice order",
    exact: true,
  });
  await expect(dialog).toBeVisible();
  await dialog
    .getByRole("combobox", { name: "Dataset", exact: true })
    .selectOption(datasetId);
  await dialog
    .getByRole("combobox", { name: "Case scope", exact: true })
    .selectOption("all");
  for (const caseId of caseIds)
    await dialog.getByLabel(new RegExp(`^${caseId}\\b`)).check();
  await dialog.getByLabel("Orders (1–4)", { exact: true }).fill("2");
  await dialog
    .getByLabel("Seed (signed 64-bit integer text)", { exact: true })
    .fill(seed);
  await dialog.getByLabel("Authored fixture", { exact: true }).check();
  await dialog
    .getByRole("combobox", { name: "Fixture set", exact: true })
    .selectOption(fixtureSetId);
  await dialog
    .getByLabel("Lifetime group request cap (1–9007199254740991)", {
      exact: true,
    })
    .fill("4");
  await dialog.getByLabel("Concurrency (1–64)", { exact: true }).fill("1");
  await dialog
    .getByLabel("Timeout seconds (1–600)", { exact: true })
    .fill("30");
  await dialog
    .getByLabel("Deadline seconds (1–86400)", { exact: true })
    .fill("120");
  await dialog
    .getByLabel("Rate/overload retries per case (0–1)", { exact: true })
    .fill("0");
  const previewResponse = await captureOperation(
    page,
    "previewChoiceOrder",
    { registration_id: registrationId },
    () =>
      dialog
        .getByRole("button", { name: "Review choice order", exact: true })
        .click(),
  );
  return { dialog, previewResponse };
}

export async function runGroupsWorkflow(
  page: Page,
  testInfo: TestInfo,
): Promise<void> {
  const context = await startDebuggingQualification(page, testInfo, "G");
  const { qualification, registrationId, reads } = context;
  let succeeded = false;
  const holds: Array<{ release: () => Promise<void> }> = [];
  try {
    await qualification.enterPhase("author-independent-regression");
    const regressionId = await addIndependentRegression(
      page,
      registrationId,
      qualification.seedMetadata.decision_id,
      qualification.seedMetadata.run_id,
      qualification.seedMetadata.result_snapshot_id,
    );
    qualification.setWitness("regression_id", regressionId);
    await reads.waitForIdle();

    await qualification.enterPhase("diagnostic-preview-and-cancel-replay");
    const caseIds = ["ex-001", "ex-003"] as const;
    for (const caseId of caseIds)
      holds.push(
        await createFixtureHold(qualification.controlDirectory, caseId),
      );
    await page
      .getByRole("navigation", { name: "Workspace" })
      .getByRole("button", { name: "Content category", exact: true })
      .click();
    const review = await openDiagnosticReview(
      page,
      registrationId,
      qualification.seedMetadata.fixture_set_id,
      qualification.seedMetadata.dataset_id,
      caseIds,
      "-9223372036854775808",
    );
    const preview = decodeSuccessEnvelope<
      ApiOperationData<"previewChoiceOrder">
    >(
      await review.previewResponse.response.body(),
      200,
      review.previewResponse.response.status(),
    );
    expect(preview.kind).toBe("choice_order");
    expect(preview.dry_run).toBe(true);
    expect(preview.independent_case_count).toBe("2");
    expect(preview.initial_requests).toBe("4");
    expect(preview.attempt_limit).toBe("4");
    expect(preview.seed).toBe("-9223372036854775808");
    const previewOrders = preview.members.map(
      (member) => member.identity.option_order,
    );
    expect(previewOrders).toHaveLength(2);
    expect(
      new Set(previewOrders.map((order) => JSON.stringify(order))).size,
    ).toBe(2);
    const previewObservationPairs = preview.members.flatMap((member) =>
      member.identity.requests.map(
        (request) =>
          `${JSON.stringify(member.identity.option_order)}:${request.case_id}`,
      ),
    );
    expect(previewObservationPairs).toHaveLength(4);
    expect(new Set(previewObservationPairs).size).toBe(4);
    for (const member of preview.members)
      expect(
        member.identity.requests.map((request) => request.case_id).sort(),
      ).toEqual([...caseIds].sort());
    expect(previewOrders[0]).toEqual(qualification.seedMetadata.original_order);
    expect(previewOrders[1]).toEqual(
      qualification.seedMetadata.min_seed_alternate,
    );
    expect(
      preview.members.every((member) => member.identity.requests.length === 2),
    ).toBe(true);
    const originalEx003Request = preview.members[0]?.identity.requests.find(
      (request) => request.case_id === "ex-003",
    );
    expect(originalEx003Request?.input_hash).toMatch(/^[a-f0-9]{64}$/);
    const originalEx003InputHash = originalEx003Request?.input_hash;
    if (!originalEx003InputHash)
      throw new Error("The original case input hash was unavailable.");
    qualification.setWitness(
      "diagnostic_original_ex003_input_hash",
      originalEx003InputHash,
    );
    const seedInput = review.dialog.getByLabel(
      "Seed (signed 64-bit integer text)",
      { exact: true },
    );
    await seedInput.fill("9223372036854775807");
    const maxSeedPreviewResponse = await captureOperation(
      page,
      "previewChoiceOrder",
      { registration_id: registrationId },
      () =>
        review.dialog
          .getByRole("button", { name: "Review choice order", exact: true })
          .click(),
    );
    const maxSeedPreview = decodeSuccessEnvelope<
      ApiOperationData<"previewChoiceOrder">
    >(
      maxSeedPreviewResponse.body,
      200,
      maxSeedPreviewResponse.response.status(),
    );
    expect(maxSeedPreview.seed).toBe("9223372036854775807");
    expect(maxSeedPreview.members[0]?.identity.option_order).toEqual(
      qualification.seedMetadata.original_order,
    );
    expect(maxSeedPreview.members[1]?.identity.option_order).toEqual(
      qualification.seedMetadata.max_seed_alternate,
    );
    expect(maxSeedPreview.dry_run).toBe(true);
    await seedInput.fill("-9223372036854775808");
    const restoredMinPreviewResponse = await captureOperation(
      page,
      "previewChoiceOrder",
      { registration_id: registrationId },
      () =>
        review.dialog
          .getByRole("button", { name: "Review choice order", exact: true })
          .click(),
    );
    const restoredMinPreview = decodeSuccessEnvelope<
      ApiOperationData<"previewChoiceOrder">
    >(
      restoredMinPreviewResponse.body,
      200,
      restoredMinPreviewResponse.response.status(),
    );
    expect(restoredMinPreview.seed).toBe("-9223372036854775808");
    expect(restoredMinPreview.members[1]?.identity.option_order).toEqual(
      qualification.seedMetadata.min_seed_alternate,
    );
    const noCalls = await waitForCountFile(
      qualification.controlDirectory,
      (counts) =>
        counts.fixture_dispatch_calls === 0 &&
        counts.for_case_calls === 0 &&
        counts.live_dispatch_calls === 0,
    );
    expect(noCalls.fixture_dispatch_calls).toBe(0);
    expect(noCalls.for_case_calls).toBe(0);
    expect(noCalls.live_dispatch_calls).toBe(0);
    await reads.waitForIdle();

    const startPath = `/api/v1/projects/${registrationId}/diagnostics/choice-order`;
    const startLoss = await installLostAcknowledgement(page, startPath, 202);
    let startReceipt: ApiOperationData<"startChoiceOrder"> | undefined;
    try {
      await review.dialog
        .getByRole("button", { name: "Start reviewed group", exact: true })
        .click();
      await expect(
        review.dialog.getByRole("button", {
          name: "Retry original start request",
          exact: true,
        }),
      ).toBeVisible();
      const firstAck = startLoss.firstObservation();
      expect(firstAck?.firstStatus).toBe(202);
      if (!firstAck)
        throw new Error("The original group acceptance body was unavailable.");
      const firstReceipt = decodeSuccessEnvelope<
        ApiOperationData<"startChoiceOrder">
      >(firstAck.firstResponseBody, 202, firstAck.firstStatus);
      expect(firstReceipt.replayed).toBe(false);
      expect(firstReceipt.operation_id).toMatch(/^[A-Za-z0-9_-]{1,128}$/);
      const firstReceiptPath = testInfo.outputPath(
        "diagnostic-start-first-receipt.json",
      );
      await writeFile(firstReceiptPath, firstAck.firstResponseBody, {
        flag: "wx",
        mode: 0o600,
      });
      qualification.setWitness(
        "diagnostic_start_first_receipt_sha256",
        bodySha256(firstAck.firstResponseBody),
      );
      const actualEnteredCase = await waitForAnyBarrierEntry(
        qualification.controlDirectory,
        caseIds,
        20_000,
      );
      const heldCounts = await waitForCountFile(
        qualification.controlDirectory,
        (counts) =>
          counts.fixture_dispatch_calls >= 1 && counts.for_case_calls >= 1,
      );
      expect(heldCounts.fixture_dispatch_calls).toBe(heldCounts.for_case_calls);
      expect(heldCounts.fixture_dispatch_calls).toBeLessThanOrEqual(2);
      qualification.setCounts({
        fixture_dispatch_calls: heldCounts.fixture_dispatch_calls,
        for_case_calls: heldCounts.for_case_calls,
        live_dispatch_calls: heldCounts.live_dispatch_calls,
      });
      qualification.setWitness("diagnostic_barrier_case_id", actualEnteredCase);

      const replayResponse = await captureOperation(
        page,
        "startChoiceOrder",
        { registration_id: registrationId },
        () =>
          review.dialog
            .getByRole("button", {
              name: "Retry original start request",
              exact: true,
            })
            .click(),
      );
      expect(replayResponse.response.status()).toBe(202);
      const replay = startLoss.observation();
      expect(replay?.replayStatus).toBe(202);
      expect(replay?.sameRequestBytes).toBe(true);
      expect(replay?.firstRequestHash).toBe(replay?.replayRequestHash);
      const firstEnvelope = object(
        JSON.parse(replay?.firstResponseBody.toString("utf8") ?? "{}"),
      );
      const again = object(
        JSON.parse(replay?.replayResponseBody.toString("utf8") ?? "{}"),
      );
      const firstData = object(firstEnvelope.data);
      const replayData = object(again.data);
      expect(firstData.operation_id).toBe(replayData.operation_id);
      expect(firstData.group_id).toBe(replayData.group_id);
      expect(firstData.segment_id).toBe(replayData.segment_id);
      expect(firstData.member_run_ids).toEqual(replayData.member_run_ids);
      startReceipt = decodeSuccessEnvelope<
        ApiOperationData<"startChoiceOrder">
      >(
        replay?.replayResponseBody ?? Buffer.alloc(0),
        202,
        replay?.replayStatus ?? 0,
      );
      expect(startReceipt.group_id).toBe(firstReceipt.group_id);
      expect(startReceipt.operation_id).toBe(firstReceipt.operation_id);
      expect(startReceipt.segment_id).toBe(firstReceipt.segment_id);
      expect(startReceipt.member_run_ids).toEqual(firstReceipt.member_run_ids);
      expect(startReceipt.replayed).toBe(true);
      qualification.setWitness("diagnostic_group_id", startReceipt.group_id);
      qualification.setWitness(
        "diagnostic_start_segment_id",
        startReceipt.segment_id,
      );
      qualification.setWitness(
        "diagnostic_start_request_sha256",
        replay?.firstRequestHash ?? "",
      );
    } finally {
      await startLoss.dispose();
    }

    if (!startReceipt)
      throw new Error("The diagnostic start receipt was unavailable.");
    const childRunId = startReceipt.member_run_ids[0];
    if (!childRunId)
      throw new Error("The accepted group omitted its child run identity.");
    await qualification.enterPhase("diagnostic-child-inspection");
    const childRunRead = await captureOperation(
      page,
      "readRun",
      { registration_id: registrationId, run_id: childRunId },
      () => page.getByRole("button", { name: childRunId, exact: true }).click(),
    );
    const childRun = decodeSuccessEnvelope<ApiOperationData<"readRun">>(
      childRunRead.body,
      200,
      childRunRead.response.status(),
    );
    expect(childRun.run_id).toBe(childRunId);
    expect(childRun.execution_group_id).toBe(startReceipt.group_id);
    expect(childRun.execution_active).toBe(true);
    await expect(
      page.getByRole("heading", { name: `Run ${childRunId}`, exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Cancel run", exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Resume run", exact: true }),
    ).toHaveCount(0);
    await page
      .getByRole("button", {
        name: "Back to choice-order diagnostic",
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("heading", { name: "Group progress", exact: true }),
    ).toBeVisible();
    await qualification.enterPhase("diagnostic-cancel-replay");
    const cancelPath = `/api/v1/projects/${registrationId}/diagnostics/${startReceipt.group_id}/cancel`;
    const cancelLoss = await installLostAcknowledgement(page, cancelPath, 200);
    try {
      await page
        .getByRole("button", { name: "Cancel group", exact: true })
        .click();
      await expect(
        page.getByRole("button", {
          name: "Retry original cancellation",
          exact: true,
        }),
      ).toBeVisible();
      const firstCancel = cancelLoss.firstObservation();
      expect(firstCancel?.firstStatus).toBe(200);
      if (!firstCancel)
        throw new Error(
          "The original group cancellation body was unavailable.",
        );
      const firstCancelReceipt = decodeSuccessEnvelope<
        ApiOperationData<"cancelChoiceOrder">
      >(firstCancel.firstResponseBody, 200, firstCancel.firstStatus);
      expect(firstCancelReceipt.group_id).toBe(startReceipt.group_id);
      expect(firstCancelReceipt.kind).toBe("choice_order");
      expect(firstCancelReceipt.replayed).toBe(false);
      const replayResponse = await captureOperation(
        page,
        "cancelChoiceOrder",
        { registration_id: registrationId, group_id: startReceipt.group_id },
        () =>
          page
            .getByRole("button", {
              name: "Retry original cancellation",
              exact: true,
            })
            .click(),
      );
      expect(replayResponse.response.status()).toBe(200);
      const replay = cancelLoss.observation();
      expect(replay?.replayStatus).toBe(200);
      expect(replay?.sameRequestBytes).toBe(true);
      expect(replay?.firstRequestHash).toBe(replay?.replayRequestHash);
      const replayedCancelReceipt = decodeSuccessEnvelope<
        ApiOperationData<"cancelChoiceOrder">
      >(
        replay?.replayResponseBody ?? Buffer.alloc(0),
        200,
        replay?.replayStatus ?? 0,
      );
      expect(replayedCancelReceipt.group_id).toBe(firstCancelReceipt.group_id);
      expect(replayedCancelReceipt.kind).toBe(firstCancelReceipt.kind);
      expect(
        replayedCancelReceipt.members.map((member) => member.run_id),
      ).toEqual(firstCancelReceipt.members.map((member) => member.run_id));
      expect(replayedCancelReceipt.replayed).toBe(firstCancelReceipt.replayed);
      qualification.setWitness(
        "diagnostic_cancel_request_sha256",
        replay?.firstRequestHash ?? "",
      );
    } finally {
      await cancelLoss.dispose();
      for (const hold of holds.splice(0)) await hold.release();
    }
    await expect(
      page.getByRole("region", { name: "Current progress" }),
    ).toContainText("Settled", { timeout: 20_000 });
    await reads.waitForIdle();
    const cancelledCounts = await waitForCountFile(
      qualification.controlDirectory,
      (counts) =>
        counts.fixture_dispatch_calls === counts.for_case_calls &&
        counts.fixture_dispatch_calls >= 1,
      20_000,
    );
    expect(cancelledCounts.fixture_dispatch_calls).toBeLessThanOrEqual(2);
    expect(cancelledCounts.live_dispatch_calls).toBe(0);
    qualification.setCounts({
      fixture_dispatch_calls: cancelledCounts.fixture_dispatch_calls,
      for_case_calls: cancelledCounts.for_case_calls,
      live_dispatch_calls: cancelledCounts.live_dispatch_calls,
    });

    await qualification.enterPhase("pin-partial-diagnostic-snapshot");
    const snapshotSelect = page.getByRole("combobox", {
      name: "Selected snapshot",
      exact: true,
    });
    const snapshotValues = await snapshotSelect
      .locator("option")
      .evaluateAll((items) =>
        items.map((item) => (item as HTMLOptionElement).value).filter(Boolean),
      );
    expect(snapshotValues.length).toBeGreaterThan(0);
    const diagnosticSnapshotId = snapshotValues[snapshotValues.length - 1];
    if (!diagnosticSnapshotId)
      throw new Error("The diagnostic snapshot identity was unavailable.");
    const selectedValue = await snapshotSelect.inputValue();
    let reloadGroupForSnapshotRead = false;
    if (selectedValue !== diagnosticSnapshotId) {
      const firstOther = snapshotValues.find(
        (value) => value !== selectedValue,
      );
      if (firstOther) await snapshotSelect.selectOption(firstOther);
    } else if (!snapshotValues.some((value) => value !== diagnosticSnapshotId))
      reloadGroupForSnapshotRead = true;
    const readSnapshot = await captureOperation(
      page,
      "readChoiceOrderSnapshot",
      {
        registration_id: registrationId,
        group_id: startReceipt?.group_id ?? "",
        snapshot_id: diagnosticSnapshotId,
      },
      async () => {
        if (reloadGroupForSnapshotRead) await page.reload();
        else await snapshotSelect.selectOption(diagnosticSnapshotId);
      },
    );
    const diagnosticDetail = decodeSuccessEnvelope<
      ApiOperationData<"readChoiceOrderSnapshot">
    >(await readSnapshot.response.body(), 200, readSnapshot.response.status());
    expect(diagnosticDetail.snapshot.id).toBe(diagnosticSnapshotId);
    expect(diagnosticDetail.snapshot.group_id).toBe(startReceipt?.group_id);
    expect(diagnosticDetail.members).toHaveLength(2);
    expect(diagnosticDetail.snapshot.id).toBe(
      await snapshotSelect.inputValue(),
    );
    const diagnosticSnapshotRoute = page.url();
    qualification.setWitness(
      "diagnostic_snapshot_content_hash",
      diagnosticDetail.snapshot.content_hash,
    );
    qualification.setWitness("diagnostic_snapshot_id", diagnosticSnapshotId);
    await expect(
      page.getByRole("heading", {
        name: "Selected immutable snapshot",
        exact: true,
      }),
    ).toBeVisible();
    const diagnosticSummary = object(diagnosticDetail.summary);
    const summaryCases = diagnosticSummary.cases;
    expect(Array.isArray(summaryCases)).toBe(true);
    const summaryCaseIds = (summaryCases as unknown[]).map((item) => {
      const caseId = object(item).case_id;
      if (typeof caseId !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(caseId))
        throw new Error("The diagnostic summary case identity was invalid.");
      return caseId;
    });
    expect([...summaryCaseIds].sort()).toEqual([...caseIds].sort());
    const summaryRegion = page.getByRole("region", {
      name: "Selected immutable snapshot",
    });
    await expect(summaryRegion).toContainText(
      `${countText(diagnosticSummary.independent_case_count)} cases · ${countText(diagnosticSummary.order_count)} orders · ${countText(diagnosticSummary.expanded_result_count)} expanded results · ${countText(diagnosticSummary.fully_observed_case_count)} fully observed`,
    );
    const summaryHeading = summaryRegion.getByRole("heading", {
      name: "Observed request-order sensitivity",
      exact: true,
    });
    await expect(summaryHeading).toBeVisible();
    const summaryList = summaryHeading.locator(
      "xpath=following-sibling::ol[1]",
    );
    await expect(summaryList.getByRole("listitem")).toHaveCount(
      summaryCaseIds.length,
    );
    for (const caseId of summaryCaseIds)
      await expect(
        summaryList.getByText(caseId, { exact: true }),
      ).toBeVisible();
    await page
      .getByRole("button", {
        name: "Create report from this snapshot",
        exact: true,
      })
      .click();
    const reportDialog = page.getByRole("dialog", {
      name: "Create a pinned report",
      exact: true,
    });
    await expect(
      reportDialog.getByRole("button", {
        name: "Verify saved target",
        exact: true,
      }),
    ).toBeEnabled();
    await reportDialog
      .getByRole("button", { name: "Verify saved target", exact: true })
      .click();
    await expect(
      reportDialog.getByRole("button", { name: "Create report", exact: true }),
    ).toBeEnabled();
    for (const rawName of [
      "Include raw inputs",
      "Include raw requests",
      "Include raw responses",
    ])
      await expect(
        reportDialog.getByLabel(rawName, { exact: true }),
      ).not.toBeChecked();
    const diagnosticReportPath = `/api/v1/projects/${registrationId}/reports`;
    const reportLoss = await installLostAcknowledgement(
      page,
      diagnosticReportPath,
      200,
    );
    let diagnosticReportId = "";
    try {
      await reportDialog
        .getByRole("button", { name: "Create report", exact: true })
        .click();
      await expect(
        reportDialog.getByRole("button", {
          name: "Retry original unchanged report",
          exact: true,
        }),
      ).toBeVisible();
      expect(reportLoss.firstObservation()?.firstStatus).toBe(200);
      const replayResponse = await captureOperation(
        page,
        "createReport",
        { registration_id: registrationId },
        () =>
          reportDialog
            .getByRole("button", {
              name: "Retry original unchanged report",
              exact: true,
            })
            .click(),
      );
      expect(replayResponse.response.status()).toBe(200);
      const replay = reportLoss.observation();
      expect(replay?.replayStatus).toBe(200);
      expect(replay?.sameRequestBytes).toBe(true);
      if (!replay)
        throw new Error(
          "The original diagnostic report request was unavailable.",
        );
      expect(bodySha256(replay.firstRequestBody)).toBe(replay.firstRequestHash);
      assertCreateReportRequestBody(replay.firstRequestBody, {
        targetKind: "diagnostic",
        targetId: startReceipt.group_id,
        raw: { inputs: false, requests: false, responses: false },
        groupSnapshotId: diagnosticSnapshotId,
      });
      const receipt = decodeSuccessEnvelope<ApiOperationData<"createReport">>(
        replay?.replayResponseBody ?? Buffer.alloc(0),
        200,
        replay?.replayStatus ?? 0,
      );
      expect(receipt.target_kind).toBe("diagnostic");
      expect(receipt.target_id).toBe(startReceipt?.group_id);
      expect(receipt.diagnostic_snapshot_id).toBe(diagnosticSnapshotId);
      expect(receipt.raw).toEqual({
        inputs: false,
        requests: false,
        responses: false,
      });
      diagnosticReportId = receipt.report_id;
      qualification.setWitness("diagnostic_report_id", diagnosticReportId);
      qualification.setWitness(
        "diagnostic_report_content_hash",
        receipt.content_hash,
      );
    } finally {
      await reportLoss.dispose();
    }
    if (!diagnosticReportId)
      throw new Error("The diagnostic report receipt was unavailable.");
    await openSavedReport(
      page,
      registrationId,
      "diagnostic",
      startReceipt.group_id,
      diagnosticReportId,
    );
    await reads.waitForIdle();
    const immutableWitness = testInfo.outputPath(
      "diagnostic-report-witness.json",
    );
    await settleOnSandbox(page, reads);
    await invokeReportWitness(
      qualification,
      qualification.projectPath,
      diagnosticReportId,
      immutableWitness,
    );
    const artifacts = await import("./installed-debugging-support").then(
      ({ readReportWitness }) =>
        readReportWitness(immutableWitness, diagnosticReportId),
    );
    await openSavedReport(
      page,
      registrationId,
      "diagnostic",
      startReceipt.group_id,
      diagnosticReportId,
    );
    qualification.setWitness(
      "diagnostic_report_json_sha256",
      artifacts.json.bytes_hash,
    );
    qualification.setWitness(
      "diagnostic_report_markdown_sha256",
      artifacts.markdown.bytes_hash,
    );
    qualification.setWitness(
      "diagnostic_report_witness_file",
      "diagnostic-report-witness.json",
    );
    const diagnosticBytes = {} as Record<"json" | "markdown", Buffer>;
    for (const format of ["json", "markdown"] as const) {
      const bytes = await downloadReportBytes(
        page,
        registrationId,
        diagnosticReportId,
        format,
      );
      expect(
        await assertExactArtifactBytes(
          bytes,
          join(testInfo.outputDir, artifacts[format].file),
          artifacts[format].bytes_hash,
        ),
      ).toBe(true);
      diagnosticBytes[format] = bytes;
      const filename = `diagnostic-browser-${format}.bin`;
      await writeFile(testInfo.outputPath(filename), bytes, {
        flag: "wx",
        mode: 0o600,
      });
      qualification.setWitness(
        `diagnostic_browser_${format}_sha256`,
        bodySha256(bytes),
      );
      qualification.setWitness(`diagnostic_browser_${format}_file`, filename);
      qualification.setEquality(
        `diagnostic_browser_${format}_equals_saved`,
        bodySha256(bytes) === artifacts[format].bytes_hash,
      );
    }
    await reads.waitForIdle();
    await page.goto(diagnosticSnapshotRoute);
    await expect(
      page.getByRole("heading", { name: "Group progress", exact: true }),
    ).toBeVisible();
    expect(await snapshotSelect.inputValue()).toBe(diagnosticSnapshotId);
    await qualification.enterPhase("resume-diagnostic-group");
    const retryUnknown = page.getByLabel(
      "Retry members with unknown outcomes",
      { exact: true },
    );
    await expect(retryUnknown).not.toBeChecked();
    await page
      .getByRole("button", { name: "Review resume", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Resume reviewed group", exact: true }),
    ).toBeVisible();
    const secondHolds = [
      await createFixtureHold(qualification.controlDirectory, "ex-001"),
      await createFixtureHold(qualification.controlDirectory, "ex-003"),
    ];
    const resumePath = `/api/v1/projects/${registrationId}/diagnostics/${startReceipt.group_id}/resume`;
    const resumeLoss = await installLostAcknowledgement(page, resumePath, 202);
    resumeLoss.mark("observer_armed");
    try {
      resumeLoss.mark("resume_click_begin");
      await page
        .getByRole("button", { name: "Resume reviewed group", exact: true })
        .click();
      resumeLoss.mark("resume_click_complete");
      await expect(
        page.getByRole("button", {
          name: "Retry original resume request",
          exact: true,
        }),
      ).toBeVisible();
      const firstResume = resumeLoss.firstObservation();
      expect(firstResume?.firstStatus).toBe(202);
      if (!firstResume)
        throw new Error("The original group resume body was unavailable.");
      const firstResumeReceipt = decodeSuccessEnvelope<
        ApiOperationData<"resumeChoiceOrder">
      >(firstResume.firstResponseBody, 202, firstResume.firstStatus);
      resumeLoss.mark("first_receipt_decoded");
      expect(firstResumeReceipt.group_id).toBe(startReceipt.group_id);
      expect(firstResumeReceipt.operation_id).not.toBe(
        startReceipt.operation_id,
      );
      expect(firstResumeReceipt.segment_id).not.toBe(startReceipt.segment_id);
      expect(firstResumeReceipt.member_run_ids).toEqual(
        startReceipt.member_run_ids,
      );
      expect(firstResumeReceipt.replayed).toBe(false);
      const replayResponse = await captureOperation(
        page,
        "resumeChoiceOrder",
        { registration_id: registrationId, group_id: startReceipt.group_id },
        () =>
          page
            .getByRole("button", {
              name: "Retry original resume request",
              exact: true,
            })
            .click(),
      );
      resumeLoss.mark("replay_capture_complete");
      expect(replayResponse.response.status()).toBe(202);
      const replay = resumeLoss.observation();
      expect(replay?.replayStatus).toBe(202);
      expect(replay?.sameRequestBytes).toBe(true);
      const accepted = decodeSuccessEnvelope<
        ApiOperationData<"resumeChoiceOrder">
      >(
        replay?.replayResponseBody ?? Buffer.alloc(0),
        202,
        replay?.replayStatus ?? 0,
      );
      expect(accepted.group_id).toBe(startReceipt.group_id);
      expect(accepted.operation_id).toBe(firstResumeReceipt.operation_id);
      expect(accepted.segment_id).toBe(firstResumeReceipt.segment_id);
      expect(accepted.member_run_ids).toEqual(
        firstResumeReceipt.member_run_ids,
      );
      expect(accepted.replayed).toBe(true);
    } finally {
      try {
        try {
          const traceName = "diagnostic-resume-browser-trace.json";
          await writeFile(
            testInfo.outputPath(traceName),
            `${JSON.stringify(resumeLoss.trace(), null, 2)}\n`,
            { flag: "wx", mode: 0o600 },
          );
          qualification.setWitness(
            "diagnostic_resume_browser_trace_file",
            traceName,
          );

          const serverTraceName = "diagnostic-resume-server-trace.json";
          const serverTraceState = await saveServerResumeTrace(
            qualification.controlDirectory,
            testInfo.outputPath(serverTraceName),
          );
          qualification.setWitness(
            "diagnostic_resume_server_trace_state",
            serverTraceState,
          );
          if (serverTraceState === "present")
            qualification.setWitness(
              "diagnostic_resume_server_trace_file",
              serverTraceName,
            );

          const counts = await readFixtureCountsNow(
            qualification.controlDirectory,
          );
          qualification.setWitness(
            "diagnostic_resume_pre_cleanup_counts_state",
            counts ? "present" : "absent",
          );
          if (counts) {
            const countsName = "diagnostic-resume-pre-cleanup-counts.json";
            await writeFile(
              testInfo.outputPath(countsName),
              `${JSON.stringify(
                {
                  fixture_dispatch_calls: counts.fixture_dispatch_calls,
                  for_case_calls: counts.for_case_calls,
                  live_dispatch_calls: counts.live_dispatch_calls,
                },
                null,
                2,
              )}\n`,
              { flag: "wx", mode: 0o600 },
            );
            qualification.setWitness(
              "diagnostic_resume_pre_cleanup_counts_file",
              countsName,
            );
          }
          qualification.setWitness(
            "diagnostic_resume_observation_capture_state",
            "complete",
          );
          await qualification.save();
        } catch {
          qualification.setWitness(
            "diagnostic_resume_observation_capture_state",
            "failed",
          );
          await qualification.save().catch(() => undefined);
        }
      } finally {
        try {
          await resumeLoss.dispose();
        } finally {
          await Promise.all(secondHolds.map((hold) => hold.release()));
        }
      }
    }
    await expect(
      page.getByRole("region", { name: "Current progress" }),
    ).toContainText("Settled", { timeout: 20_000 });
    const resumedCounts = await waitForCountFile(
      qualification.controlDirectory,
      (counts) =>
        counts.fixture_dispatch_calls === 4 &&
        counts.for_case_calls === 4 &&
        counts.live_dispatch_calls === 0,
      30_000,
    );
    expect(resumedCounts.fixture_dispatch_calls).toBe(4);
    expect(resumedCounts.for_case_calls).toBe(4);
    qualification.setCounts({
      fixture_dispatch_calls: 4,
      for_case_calls: 4,
      live_dispatch_calls: 0,
    });
    const finalProgressRead = await captureOperation(
      page,
      "readChoiceOrder",
      { registration_id: registrationId, group_id: startReceipt.group_id },
      async () => {
        await page.reload();
      },
    );
    const finalProgress = decodeSuccessEnvelope<
      ApiOperationData<"readChoiceOrder">
    >(finalProgressRead.body, 200, finalProgressRead.response.status());
    expect(finalProgress.group.group_id).toBe(startReceipt.group_id);
    expect(finalProgress.group.kind).toBe("choice_order");
    expect(finalProgress.group.attempt_limit).toBe("4");
    expect(finalProgress.group.attempts_used).toBe("4");
    expect(finalProgress.group.attempts_remaining).toBe("0");
    expect(finalProgress.group.independent_case_count).toBe("2");
    expect(finalProgress.group.initial_requests).toBe("4");
    expect(finalProgress.group.members).toHaveLength(2);
    expect(
      finalProgress.group.members.every(
        (member) =>
          member.attempts_used === "2" && member.attempts_remaining === "0",
      ),
    ).toBe(true);
    const progressRegion = page.getByRole("region", {
      name: "Current progress",
    });
    for (const [label, value] of [
      ["Independent cases", finalProgress.group.independent_case_count],
      ["Initial requests", finalProgress.group.initial_requests],
      ["Lifetime attempt limit", finalProgress.group.attempt_limit],
      ["Attempts used", finalProgress.group.attempts_used],
      ["Attempts remaining", finalProgress.group.attempts_remaining],
    ]) {
      const valueCell = progressRegion
        .locator("dt")
        .filter({ hasText: new RegExp(`^${label}$`) })
        .locator("xpath=following-sibling::dd[1]");
      await expect(valueCell).toHaveText(value);
    }
    for (const member of finalProgress.group.members) {
      const memberRow = progressRegion
        .getByRole("listitem")
        .filter({ hasText: member.run_id });
      await expect(memberRow).toHaveCount(1);
      await expect(
        memberRow.getByRole("button", { name: member.run_id, exact: true }),
      ).toBeVisible();
      await expect(memberRow).toContainText(
        `${member.state} · ${member.attempts_used} attempts · ${member.attempts_remaining} remaining`,
      );
    }
    expect(await snapshotSelect.inputValue()).toBe(diagnosticSnapshotId);
    const resumedOptions = snapshotSelect.locator("option");
    await expect
      .poll(() => resumedOptions.last().getAttribute("value"))
      .not.toBe(diagnosticSnapshotId);
    const resumedSnapshotValues = await snapshotSelect
      .locator("option")
      .evaluateAll((items) =>
        items.map((item) => (item as HTMLOptionElement).value).filter(Boolean),
      );
    const latestResumedSnapshot = resumedSnapshotValues.at(-1);
    if (!latestResumedSnapshot)
      throw new Error("The resumed diagnostic snapshot was unavailable.");
    expect(latestResumedSnapshot).not.toBe(diagnosticSnapshotId);
    const finalDiagnosticRead = await captureOperation(
      page,
      "readChoiceOrderSnapshot",
      {
        registration_id: registrationId,
        group_id: startReceipt.group_id,
        snapshot_id: latestResumedSnapshot,
      },
      () =>
        page
          .getByRole("button", {
            name: "Select latest snapshot",
            exact: true,
          })
          .click(),
    );
    const finalDiagnosticDetail = decodeSuccessEnvelope<
      ApiOperationData<"readChoiceOrderSnapshot">
    >(finalDiagnosticRead.body, 200, finalDiagnosticRead.response.status());
    expect(finalDiagnosticDetail.snapshot.id).toBe(latestResumedSnapshot);
    expect(finalDiagnosticDetail.snapshot.group_id).toBe(startReceipt.group_id);
    expect(finalDiagnosticDetail.members).toHaveLength(2);
    const finalDiagnosticSummary = object(finalDiagnosticDetail.summary);
    const finalSummaryCases = finalDiagnosticSummary.cases;
    expect(Array.isArray(finalSummaryCases)).toBe(true);
    const finalSummaryCaseIds = (finalSummaryCases as unknown[]).map((item) => {
      const caseId = object(item).case_id;
      if (typeof caseId !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(caseId))
        throw new Error("The final diagnostic case identity was invalid.");
      return caseId;
    });
    expect([...finalSummaryCaseIds].sort()).toEqual([...caseIds].sort());
    expect(finalDiagnosticSummary.independent_case_count).toBe("2");
    expect(finalDiagnosticSummary.order_count).toBe("2");
    expect(finalDiagnosticSummary.expanded_result_count).toBe("4");
    expect(finalDiagnosticSummary.fully_observed_case_count).toBe("2");
    const finalSummaryRegion = page.getByRole("region", {
      name: "Selected immutable snapshot",
    });
    await expect(finalSummaryRegion).toContainText(
      "2 cases · 2 orders · 4 expanded results · 2 fully observed",
    );
    await expect(
      finalSummaryRegion.getByText("Disagreement: 1/2", { exact: false }),
    ).toBeVisible();
    const finalSummaryHeading = finalSummaryRegion.getByRole("heading", {
      name: "Observed request-order sensitivity",
      exact: true,
    });
    await expect(finalSummaryHeading).toBeVisible();
    const finalSummaryList = finalSummaryHeading.locator(
      "xpath=following-sibling::ol[1]",
    );
    await expect(finalSummaryList.getByRole("listitem")).toHaveCount(2);
    for (const caseId of finalSummaryCaseIds)
      await expect(
        finalSummaryList.getByText(caseId, { exact: true }),
      ).toBeVisible();

    const resumedSelection = await snapshotSelect.inputValue();
    const otherResumedSnapshot = resumedSnapshotValues.find(
      (value) => value !== diagnosticSnapshotId,
    );
    let reloadForPinnedRead = false;
    if (resumedSelection === diagnosticSnapshotId && otherResumedSnapshot)
      await snapshotSelect.selectOption(otherResumedSnapshot);
    else if (resumedSelection === diagnosticSnapshotId)
      reloadForPinnedRead = true;
    const pinnedRead = await captureOperation(
      page,
      "readChoiceOrderSnapshot",
      {
        registration_id: registrationId,
        group_id: startReceipt.group_id,
        snapshot_id: diagnosticSnapshotId,
      },
      async () => {
        if (reloadForPinnedRead) await page.reload();
        else await snapshotSelect.selectOption(diagnosticSnapshotId);
      },
    );
    const pinnedDetail = decodeSuccessEnvelope<
      ApiOperationData<"readChoiceOrderSnapshot">
    >(pinnedRead.body, 200, pinnedRead.response.status());
    expect(pinnedDetail.snapshot.id).toBe(diagnosticSnapshotId);
    expect(pinnedDetail.snapshot.content_hash).toBe(
      diagnosticDetail.snapshot.content_hash,
    );
    expect(pinnedDetail.members).toEqual(diagnosticDetail.members);
    await expect(snapshotSelect).toHaveValue(diagnosticSnapshotId);
    await expect(
      page.getByRole("heading", {
        name: "Selected immutable snapshot",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByText("Disagreement: 1/2", { exact: false }),
    ).toBeVisible();
    await reads.waitForIdle();
    qualification.setEquality(
      "diagnostic_snapshot_preserved_after_resume",
      pinnedDetail.snapshot.content_hash ===
        diagnosticDetail.snapshot.content_hash &&
        JSON.stringify(pinnedDetail.members) ===
          JSON.stringify(diagnosticDetail.members),
    );
    await qualification.captureScreenshot(page, "m12-group-snapshot.png");

    await openSavedReport(
      page,
      registrationId,
      "diagnostic",
      startReceipt.group_id,
      diagnosticReportId,
    );
    await reads.waitForIdle();
    for (const format of ["json", "markdown"] as const) {
      const afterResume = await downloadReportBytes(
        page,
        registrationId,
        diagnosticReportId,
        format,
      );
      expect(Buffer.compare(afterResume, diagnosticBytes[format])).toBe(0);
      qualification.setEquality(
        `diagnostic_report_${format}_unchanged_after_resume`,
        Buffer.compare(afterResume, diagnosticBytes[format]) === 0,
      );
    }
    await page.goto(diagnosticSnapshotRoute);
    await expect(
      page.getByRole("heading", { name: "Group progress", exact: true }),
    ).toBeVisible();
    await expect(snapshotSelect).toHaveValue(diagnosticSnapshotId);
    await setReaddedCaseCurrentLabel(page, qualification, registrationId, () =>
      reads.waitForIdle(),
    );
    const diagnosticAfterLabel = await captureOperation(
      page,
      "readChoiceOrderSnapshot",
      {
        registration_id: registrationId,
        group_id: startReceipt.group_id,
        snapshot_id: diagnosticSnapshotId,
      },
      async () => {
        await page.goto(diagnosticSnapshotRoute);
      },
    );
    const diagnosticAfterLabelDetail = decodeSuccessEnvelope<
      ApiOperationData<"readChoiceOrderSnapshot">
    >(diagnosticAfterLabel.body, 200, diagnosticAfterLabel.response.status());
    expect(diagnosticAfterLabelDetail.snapshot.id).toBe(diagnosticSnapshotId);
    expect(diagnosticAfterLabelDetail.snapshot.content_hash).toBe(
      diagnosticDetail.snapshot.content_hash,
    );
    expect(diagnosticAfterLabelDetail.members).toEqual(
      diagnosticDetail.members,
    );
    await expect(snapshotSelect).toHaveValue(diagnosticSnapshotId);
    await openSavedReport(
      page,
      registrationId,
      "diagnostic",
      startReceipt.group_id,
      diagnosticReportId,
    );
    await reads.waitForIdle();
    for (const format of ["json", "markdown"] as const) {
      const afterLabelEdit = await downloadReportBytes(
        page,
        registrationId,
        diagnosticReportId,
        format,
      );
      expect(Buffer.compare(afterLabelEdit, diagnosticBytes[format])).toBe(0);
      qualification.setEquality(
        `diagnostic_report_${format}_unchanged_after_current_label_edit`,
        Buffer.compare(afterLabelEdit, diagnosticBytes[format]) === 0,
      );
    }

    await qualification.enterPhase("regression-check-frozen-input");
    const readdedCase = await editDeleteAndReaddCaseThroughPublicInterfaces(
      page,
      qualification,
      registrationId,
      () => reads.waitForIdle(),
    );
    await page
      .getByRole("navigation", { name: "Workspace" })
      .getByRole("button", { name: "Content category", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Preview regression check", exact: true })
      .click();
    const checkDialog = page.getByRole("dialog", {
      name: "Review regression check",
      exact: true,
    });
    const oracle = checkDialog.getByLabel(
      new RegExp(`ex-003 · ${regressionId}`),
    );
    await oracle.check();
    await checkDialog.getByLabel("Authored fixture", { exact: true }).check();
    await checkDialog
      .getByRole("combobox", { name: "Fixture set", exact: true })
      .selectOption(qualification.seedMetadata.fixture_set_id);
    await checkDialog
      .getByLabel("Lifetime group request cap (1–9007199254740991)", {
        exact: true,
      })
      .fill("1");
    await checkDialog
      .getByLabel("Concurrency (1–64)", { exact: true })
      .fill("1");
    await checkDialog
      .getByLabel("Timeout seconds (1–600)", { exact: true })
      .fill("30");
    await checkDialog
      .getByLabel("Deadline seconds (1–86400)", { exact: true })
      .fill("120");
    await checkDialog
      .getByLabel("Rate/overload retries per case (0–1)", { exact: true })
      .fill("0");
    const checkPreviewResponse = await captureOperation(
      page,
      "previewRegressionCheck",
      { registration_id: registrationId },
      () =>
        checkDialog
          .getByRole("button", { name: "Review regression check", exact: true })
          .click(),
    );
    const checkPreview = decodeSuccessEnvelope<
      ApiOperationData<"previewRegressionCheck">
    >(
      await checkPreviewResponse.response.body(),
      200,
      checkPreviewResponse.response.status(),
    );
    expect(checkPreview.kind).toBe("regression_check");
    expect(checkPreview.dry_run).toBe(true);
    expect(checkPreview.members).toHaveLength(1);
    expect(checkPreview.initial_requests).toBe("1");
    expect(checkPreview.members[0]?.identity.requests[0]?.input_hash).toMatch(
      /^[a-f0-9]{64}$/,
    );
    expect(checkPreview.members[0]?.identity.requests[0]?.case_id).toBe(
      "ex-003",
    );
    expect(checkPreview.members[0]?.identity.requests[0]?.input_hash).toBe(
      originalEx003InputHash,
    );
    qualification.setEquality(
      "check_preview_uses_frozen_ex003_input",
      checkPreview.members[0]?.identity.requests[0]?.input_hash ===
        originalEx003InputHash,
    );
    qualification.setWitness(
      "readded_ex003_record_hash",
      readdedCase.readdedRecordHash,
    );
    await reads.waitForIdle();
    const checkHold = await createFixtureHold(
      qualification.controlDirectory,
      "ex-003",
    );
    const checkStartPath = `/api/v1/projects/${registrationId}/checks`;
    const checkLoss = await installLostAcknowledgement(
      page,
      checkStartPath,
      202,
    );
    let checkReceipt: ApiOperationData<"startRegressionCheck"> | undefined;
    try {
      await checkDialog
        .getByRole("button", { name: "Start reviewed group", exact: true })
        .click();
      await expect(
        checkDialog.getByRole("button", {
          name: "Retry original start request",
          exact: true,
        }),
      ).toBeVisible();
      expect(checkLoss.firstObservation()?.firstStatus).toBe(202);
      const replayResponse = await captureOperation(
        page,
        "startRegressionCheck",
        { registration_id: registrationId },
        () =>
          checkDialog
            .getByRole("button", {
              name: "Retry original start request",
              exact: true,
            })
            .click(),
      );
      expect(replayResponse.response.status()).toBe(202);
      const replay = checkLoss.observation();
      expect(replay?.sameRequestBytes).toBe(true);
      checkReceipt = decodeSuccessEnvelope<
        ApiOperationData<"startRegressionCheck">
      >(
        replay?.replayResponseBody ?? Buffer.alloc(0),
        202,
        replay?.replayStatus ?? 0,
      );
      expect(checkReceipt.replayed).toBe(true);
      qualification.setWitness("check_group_id", checkReceipt.group_id);
    } finally {
      await checkLoss.dispose();
      await checkHold.release();
    }
    if (!checkReceipt)
      throw new Error("The regression check receipt was unavailable.");
    await expect(
      page.getByRole("region", { name: "Current progress" }),
    ).toContainText("Settled", { timeout: 30_000 });
    const completeCounts = await waitForCountFile(
      qualification.controlDirectory,
      (counts) =>
        counts.fixture_dispatch_calls === 5 &&
        counts.for_case_calls === 5 &&
        counts.live_dispatch_calls === 0,
      30_000,
    );
    expect(completeCounts.fixture_dispatch_calls).toBe(5);
    expect(completeCounts.for_case_calls).toBe(5);
    qualification.setCounts({
      fixture_dispatch_calls: 5,
      for_case_calls: 5,
      live_dispatch_calls: 0,
    });
    await reads.waitForIdle();
    const checkProgressRead = await captureOperation(
      page,
      "readCheck",
      { registration_id: registrationId, group_id: checkReceipt.group_id },
      async () => {
        await page.reload();
      },
    );
    const checkProgress = decodeSuccessEnvelope<ApiOperationData<"readCheck">>(
      checkProgressRead.body,
      200,
      checkProgressRead.response.status(),
    );
    expect(checkProgress.group.group_id).toBe(checkReceipt.group_id);
    expect(checkProgress.group.kind).toBe("regression_check");
    expect(checkProgress.group.attempt_limit).toBe("1");
    expect(checkProgress.group.attempts_used).toBe("1");
    expect(checkProgress.group.attempts_remaining).toBe("0");
    expect(checkProgress.group.independent_case_count).toBe("1");
    expect(checkProgress.group.initial_requests).toBe("1");
    expect(checkProgress.group.members).toHaveLength(1);
    expect(checkProgress.group.members[0]?.attempts_used).toBe("1");
    expect(checkProgress.group.members[0]?.attempts_remaining).toBe("0");

    await qualification.enterPhase("pin-check-snapshot-and-report");
    const checkSnapshotSelect = page.getByRole("combobox", {
      name: "Selected snapshot",
      exact: true,
    });
    const checkSnapshotValues = await checkSnapshotSelect
      .locator("option")
      .evaluateAll((items) =>
        items.map((item) => (item as HTMLOptionElement).value).filter(Boolean),
      );
    expect(checkSnapshotValues.length).toBeGreaterThan(0);
    const checkSnapshotId = checkSnapshotValues[checkSnapshotValues.length - 1];
    if (!checkSnapshotId)
      throw new Error("The check snapshot identity was unavailable.");
    const selectedCheckSnapshot = await checkSnapshotSelect.inputValue();
    let reloadForCheckRead = false;
    if (selectedCheckSnapshot !== checkSnapshotId) {
      const other = checkSnapshotValues.find(
        (value) => value !== selectedCheckSnapshot,
      );
      if (other) await checkSnapshotSelect.selectOption(other);
    } else if (!checkSnapshotValues.some((value) => value !== checkSnapshotId))
      reloadForCheckRead = true;
    const snapshotRead = await captureOperation(
      page,
      "readCheckSnapshot",
      {
        registration_id: registrationId,
        group_id: checkReceipt.group_id,
        snapshot_id: checkSnapshotId,
      },
      async () => {
        if (reloadForCheckRead) await page.reload();
        else await checkSnapshotSelect.selectOption(checkSnapshotId);
      },
    );
    const checkSnapshot = decodeSuccessEnvelope<
      ApiOperationData<"readCheckSnapshot">
    >(snapshotRead.body, 200, snapshotRead.response.status());
    expect(checkSnapshot.snapshot.id).toBe(checkSnapshotId);
    expect(checkSnapshot.snapshot.group_id).toBe(checkReceipt.group_id);
    expect(checkSnapshot.cases).toHaveLength(1);
    expect(checkSnapshot.expectation_failures).toBe("1");
    expect(checkSnapshot.baseline_unavailable).toBe(
      "frozen_regression_selection",
    );
    expect(checkSnapshot.cases[0]?.regression_id).toBe(regressionId);
    expect(checkSnapshot.cases[0]?.case_id).toBe("ex-003");
    expect(checkSnapshot.cases[0]?.input_hash).toBe(originalEx003InputHash);
    expect(checkPreview.members[0]?.identity.requests[0]?.input_hash).toBe(
      originalEx003InputHash,
    );
    expect(readdedCase.readdedRecordHash).not.toBe(originalEx003InputHash);
    expect(checkSnapshot.cases[0]?.expected_option_ids).toEqual(["question"]);
    expect(checkSnapshot.cases[0]?.passed).toBe(false);
    expect(checkSnapshot.cases[0]?.actual_option_id).not.toBe("question");
    expect(checkSnapshot.cases[0]?.source_run_id).toBe(
      qualification.seedMetadata.run_id,
    );
    expect(checkSnapshot.cases[0]?.source_result_snapshot_id).toBe(
      qualification.seedMetadata.result_snapshot_id,
    );
    qualification.setWitness("check_snapshot_id", checkSnapshotId);
    const checkSnapshotRoute = page.url();
    await expect(
      page.getByRole("heading", {
        name: "Selected immutable snapshot",
        exact: true,
      }),
    ).toBeVisible();
    await page
      .getByRole("button", {
        name: "Create report from this snapshot",
        exact: true,
      })
      .click();
    const checkReportDialog = page.getByRole("dialog", {
      name: "Create a pinned report",
      exact: true,
    });
    const checkVerified = await captureOperation(
      page,
      "readCheckSnapshot",
      {
        registration_id: registrationId,
        group_id: checkReceipt.group_id,
        snapshot_id: checkSnapshotId,
      },
      () =>
        checkReportDialog
          .getByRole("button", { name: "Verify saved target", exact: true })
          .click(),
    );
    const verifiedSnapshot = decodeSuccessEnvelope<
      ApiOperationData<"readCheckSnapshot">
    >(checkVerified.body, 200, checkVerified.response.status());
    expect(verifiedSnapshot.snapshot.id).toBe(checkSnapshotId);
    expect(verifiedSnapshot.cases).toEqual(checkSnapshot.cases);
    expect(verifiedSnapshot.expectation_failures).toBe("1");
    expect(verifiedSnapshot.baseline_unavailable).toBe(
      "frozen_regression_selection",
    );
    for (const rawName of [
      "Include raw inputs",
      "Include raw requests",
      "Include raw responses",
    ])
      await expect(
        checkReportDialog.getByLabel(rawName, { exact: true }),
      ).not.toBeChecked();
    const checkReportResponse = await captureOperation(
      page,
      "createReport",
      { registration_id: registrationId },
      () =>
        checkReportDialog
          .getByRole("button", { name: "Create report", exact: true })
          .click(),
    );
    const checkReportReceipt = decodeSuccessEnvelope<
      ApiOperationData<"createReport">
    >(
      await checkReportResponse.response.body(),
      200,
      checkReportResponse.response.status(),
    );
    const checkReportRequestBody = checkReportResponse.response
      .request()
      .postDataBuffer();
    if (!checkReportRequestBody)
      throw new Error("The check report request body was unavailable.");
    assertCreateReportRequestBody(checkReportRequestBody, {
      targetKind: "check",
      targetId: checkReceipt.group_id,
      raw: { inputs: false, requests: false, responses: false },
      groupSnapshotId: checkSnapshotId,
    });
    expect(checkReportReceipt.target_kind).toBe("check");
    expect(checkReportReceipt.target_id).toBe(checkReceipt.group_id);
    expect(checkReportReceipt.check_snapshot_id).toBe(checkSnapshotId);
    expect(checkReportReceipt.raw).toEqual({
      inputs: false,
      requests: false,
      responses: false,
    });
    qualification.setWitness("check_report_id", checkReportReceipt.report_id);
    await openSavedReport(
      page,
      registrationId,
      "check",
      checkReceipt.group_id,
      checkReportReceipt.report_id,
    );
    await reads.waitForIdle();
    const checkWitnessPath = testInfo.outputPath("check-report-witness.json");
    await settleOnSandbox(page, reads);
    await invokeReportWitness(
      qualification,
      qualification.projectPath,
      checkReportReceipt.report_id,
      checkWitnessPath,
    );
    const checkWitness = await readReportWitness(
      checkWitnessPath,
      checkReportReceipt.report_id,
    );
    await openSavedReport(
      page,
      registrationId,
      "check",
      checkReceipt.group_id,
      checkReportReceipt.report_id,
    );
    qualification.setWitness(
      "check_report_json_sha256",
      checkWitness.json.bytes_hash,
    );
    qualification.setWitness(
      "check_report_markdown_sha256",
      checkWitness.markdown.bytes_hash,
    );
    qualification.setWitness(
      "check_report_witness_file",
      "check-report-witness.json",
    );
    const checkBytes = {} as Record<"json" | "markdown", Buffer>;
    for (const format of ["json", "markdown"] as const) {
      const bytes = await downloadReportBytes(
        page,
        registrationId,
        checkReportReceipt.report_id,
        format,
      );
      expect(
        await assertExactArtifactBytes(
          bytes,
          join(testInfo.outputDir, checkWitness[format].file),
          checkWitness[format].bytes_hash,
        ),
      ).toBe(true);
      checkBytes[format] = bytes;
      const filename = `check-browser-${format}.bin`;
      await writeFile(testInfo.outputPath(filename), bytes, {
        flag: "wx",
        mode: 0o600,
      });
      qualification.setWitness(
        `check_browser_${format}_sha256`,
        bodySha256(bytes),
      );
      qualification.setWitness(`check_browser_${format}_file`, filename);
    }

    await qualification.enterPhase(
      "remove-current-regression-and-preserve-check",
    );
    await page
      .getByRole("button", {
        name: `Regression examples: Content category`,
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Regression examples for Content category",
        exact: true,
      }),
    ).toBeVisible();
    const regressionRow = page
      .getByRole("row")
      .filter({ hasText: regressionId });
    await expect(regressionRow).toContainText("Executable");
    const removedRegression = await captureOperation(
      page,
      "removeRegression",
      {
        registration_id: registrationId,
        decision_id: qualification.seedMetadata.decision_id,
        regression_id: regressionId,
      },
      () =>
        regressionRow
          .getByRole("button", {
            name: "Remove from future checks",
            exact: true,
          })
          .click(),
    );
    const removal = decodeSuccessEnvelope<ApiOperationData<"removeRegression">>(
      removedRegression.body,
      200,
      removedRegression.response.status(),
    );
    expect(removal.regression_id).toBe(regressionId);
    expect(removal.removed).toBe(true);
    const removedRow = page.getByRole("row").filter({ hasText: regressionId });
    await expect(removedRow).toContainText("Removed");
    await expect(
      removedRow.getByRole("button", {
        name: "Remove from future checks",
        exact: true,
      }),
    ).toHaveCount(0);
    await page
      .getByRole("navigation", { name: "Workspace" })
      .getByRole("button", { name: "Content category", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Preview regression check", exact: true })
      .click();
    const defaultCheckDialog = page.getByRole("dialog", {
      name: "Review regression check",
      exact: true,
    });
    await expect(
      defaultCheckDialog.getByText(
        "No visible regression oracles are available.",
        { exact: true },
      ),
    ).toBeVisible();
    await defaultCheckDialog
      .getByLabel("Authored fixture", { exact: true })
      .check();
    await defaultCheckDialog
      .getByRole("combobox", { name: "Fixture set", exact: true })
      .selectOption(qualification.seedMetadata.fixture_set_id);
    await defaultCheckDialog
      .getByLabel("Lifetime group request cap (1–9007199254740991)", {
        exact: true,
      })
      .fill("1");
    await defaultCheckDialog
      .getByLabel("Concurrency (1–64)", { exact: true })
      .fill("1");
    await defaultCheckDialog
      .getByLabel("Timeout seconds (1–600)", { exact: true })
      .fill("30");
    await defaultCheckDialog
      .getByLabel("Deadline seconds (1–86400)", { exact: true })
      .fill("120");
    await defaultCheckDialog
      .getByLabel("Rate/overload retries per case (0–1)", { exact: true })
      .fill("0");
    const emptyScope = await captureOperation(
      page,
      "previewRegressionCheck",
      { registration_id: registrationId },
      () =>
        defaultCheckDialog
          .getByRole("button", { name: "Review regression check", exact: true })
          .click(),
    );
    expect(emptyScope.response.status()).toBe(422);
    const emptyEnvelope = object(JSON.parse(emptyScope.body.toString("utf8")));
    const emptyError = object(emptyEnvelope.error);
    expect(emptyError.code).toBe("validation_error");
    expect(emptyError.reason).toBe("empty_regression_scope");
    await defaultCheckDialog
      .getByRole("button", { name: "Close", exact: true })
      .click();
    const checkSnapshotAfterRemoval = await captureOperation(
      page,
      "readCheckSnapshot",
      {
        registration_id: registrationId,
        group_id: checkReceipt.group_id,
        snapshot_id: checkSnapshotId,
      },
      async () => {
        await page.goto(checkSnapshotRoute);
      },
    );
    const checkSnapshotAfterRemovalDetail = decodeSuccessEnvelope<
      ApiOperationData<"readCheckSnapshot">
    >(
      checkSnapshotAfterRemoval.body,
      200,
      checkSnapshotAfterRemoval.response.status(),
    );
    expect(checkSnapshotAfterRemovalDetail.snapshot.id).toBe(checkSnapshotId);
    expect(checkSnapshotAfterRemovalDetail.cases).toEqual(checkSnapshot.cases);
    expect(checkSnapshotAfterRemovalDetail.expectation_failures).toBe("1");
    expect(checkSnapshotAfterRemovalDetail.baseline_unavailable).toBe(
      "frozen_regression_selection",
    );
    await expect(checkSnapshotSelect).toHaveValue(checkSnapshotId);
    await reads.waitForIdle();
    const removedCounts = await waitForCountFile(
      qualification.controlDirectory,
      (counts) =>
        counts.fixture_dispatch_calls === 5 &&
        counts.for_case_calls === 5 &&
        counts.live_dispatch_calls === 0,
    );
    expect(removedCounts).toMatchObject({
      fixture_dispatch_calls: 5,
      for_case_calls: 5,
      live_dispatch_calls: 0,
    });

    await openSavedReport(
      page,
      registrationId,
      "diagnostic",
      startReceipt.group_id,
      diagnosticReportId,
    );
    await reads.waitForIdle();
    for (const format of ["json", "markdown"] as const) {
      const afterRemoval = await downloadReportBytes(
        page,
        registrationId,
        diagnosticReportId,
        format,
      );
      expect(Buffer.compare(afterRemoval, diagnosticBytes[format])).toBe(0);
      expect(
        await assertExactArtifactBytes(
          afterRemoval,
          join(testInfo.outputDir, artifacts[format].file),
          artifacts[format].bytes_hash,
        ),
      ).toBe(true);
      qualification.setEquality(
        `diagnostic_report_${format}_unchanged_after_regression_removal`,
        Buffer.compare(afterRemoval, diagnosticBytes[format]) === 0,
      );
    }

    await openSavedReport(
      page,
      registrationId,
      "check",
      checkReceipt.group_id,
      checkReportReceipt.report_id,
    );
    await reads.waitForIdle();
    for (const format of ["json", "markdown"] as const) {
      const afterRemoval = await downloadReportBytes(
        page,
        registrationId,
        checkReportReceipt.report_id,
        format,
      );
      expect(Buffer.compare(afterRemoval, checkBytes[format])).toBe(0);
      expect(
        await assertExactArtifactBytes(
          afterRemoval,
          join(testInfo.outputDir, checkWitness[format].file),
          checkWitness[format].bytes_hash,
        ),
      ).toBe(true);
      qualification.setEquality(
        `check_report_${format}_unchanged_after_removal`,
        Buffer.compare(afterRemoval, checkBytes[format]) === 0,
      );
    }
    succeeded = true;
  } finally {
    for (const hold of holds.splice(0)) await hold.release();
    await finishDebuggingQualification(qualification, reads, succeeded);
  }
}
