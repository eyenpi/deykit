import { expect, type Page, type TestInfo } from "@playwright/test";
import type { ApiOperationData } from "../src/api/client";
import {
  captureResponse,
  captureOperation,
  decodeSuccessEnvelope,
  finishDebuggingQualification,
  installLostAcknowledgement,
  startDebuggingQualification,
  waitForCountFile,
} from "./installed-debugging-support";

function assertBaselineResultPage(
  page: ApiOperationData<"listResults">,
  resultSnapshotId: string,
  labelSnapshotId: string,
): void {
  expect(page.result_snapshot_id).toBe(resultSnapshotId);
  expect(page.label_snapshot_id).toBe(labelSnapshotId);
  expect(page.selected_count).toBe("12");
  expect(page.assessment_counts).toEqual({
    all: "12",
    inspect: "4",
    incorrect: "2",
    unlabelled: "2",
  });
  expect(page.status_counts).toEqual({
    pending: "0",
    valid: "10",
    input_invalid: "1",
    response_error: "1",
    unknown: "0",
  });
}

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function sourceCaseIds(page: ApiOperationData<"listResults">): string[] {
  const ids = page.items.map((item) => item.source.case_id);
  expect(ids.every((id) => typeof id === "string")).toBe(true);
  return ids as string[];
}

export async function runSavedAnswersWorkflow(
  page: Page,
  testInfo: TestInfo,
): Promise<void> {
  const context = await startDebuggingQualification(page, testInfo, "S");
  const { qualification, registrationId, reads } = context;
  let succeeded = false;
  try {
    await qualification.enterPhase("original-run-and-evaluation");
    const runsCapture = await captureOperation(
      page,
      "listRuns",
      { registration_id: registrationId },
      () => page.getByRole("button", { name: "Runs", exact: true }).click(),
    );
    const runPage = decodeSuccessEnvelope<ApiOperationData<"listRuns">>(
      await runsCapture.response.body(),
      200,
      runsCapture.response.status(),
    );
    const seededRuns = runPage.items.filter(
      (item) => item.run_id === qualification.seedMetadata.run_id,
    );
    expect(seededRuns).toHaveLength(1);
    const runButton = page.getByRole("button", {
      name: qualification.seedMetadata.run_id,
      exact: true,
    });
    await expect(runButton).toBeVisible();
    const firstResults = await captureOperation(
      page,
      "listResults",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
      },
      () => runButton.click(),
      (query) => !query.has("evaluation_id"),
    );
    const originalPage = decodeSuccessEnvelope<ApiOperationData<"listResults">>(
      await firstResults.response.body(),
      200,
      firstResults.response.status(),
    );
    assertBaselineResultPage(
      originalPage,
      qualification.seedMetadata.result_snapshot_id,
      qualification.seedMetadata.label_snapshot_id,
    );
    await expect(
      page.getByRole("heading", {
        name: `Run ${qualification.seedMetadata.run_id}`,
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("table", { name: "Frozen result rows" }),
    ).toBeVisible();

    const evaluationSelection = page.getByRole("combobox", {
      name: "Evaluation snapshot",
      exact: true,
    });
    await expect(evaluationSelection).toBeVisible();
    const evaluationResults = await captureOperation(
      page,
      "listResults",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
      },
      async () => {
        await evaluationSelection.selectOption(
          qualification.seedMetadata.evaluation_id,
        );
      },
      (query) =>
        query.get("evaluation_id") === qualification.seedMetadata.evaluation_id,
    );
    const pinnedFirstPage = decodeSuccessEnvelope<
      ApiOperationData<"listResults">
    >(
      await evaluationResults.response.body(),
      200,
      evaluationResults.response.status(),
    );
    assertBaselineResultPage(
      pinnedFirstPage,
      qualification.seedMetadata.result_snapshot_id,
      qualification.seedMetadata.label_snapshot_id,
    );
    await expect(
      page.getByText(
        `Pinned evaluation ${qualification.seedMetadata.evaluation_id}; result snapshot ${qualification.seedMetadata.result_snapshot_id}, label snapshot ${qualification.seedMetadata.label_snapshot_id}.`,
        { exact: true },
      ),
    ).toBeVisible();

    await qualification.enterPhase("frozen-pagination-and-assessment");
    const firstPaged = await captureOperation(
      page,
      "listResults",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
      },
      async () => {
        await page
          .getByRole("combobox", { name: "Results per page", exact: true })
          .selectOption("5");
      },
      (query) =>
        query.get("limit") === "5" &&
        query.get("evaluation_id") === qualification.seedMetadata.evaluation_id,
    );
    let currentPage = decodeSuccessEnvelope<ApiOperationData<"listResults">>(
      await firstPaged.response.body(),
      200,
      firstPaged.response.status(),
    );
    assertBaselineResultPage(
      currentPage,
      qualification.seedMetadata.result_snapshot_id,
      qualification.seedMetadata.label_snapshot_id,
    );
    const pagedIds = sourceCaseIds(currentPage);
    expect(pagedIds).toHaveLength(5);
    expect(currentPage.next_cursor).not.toBeNull();
    await expect(
      page.getByRole("table", { name: "Frozen result rows" }),
    ).toBeVisible();
    await expect(
      page.getByRole("table", { name: "Frozen result rows" }).getByRole("row"),
    ).toHaveCount(6);

    for (const expectedSize of [5, 2]) {
      const next = await captureOperation(
        page,
        "listResults",
        {
          registration_id: registrationId,
          run_id: qualification.seedMetadata.run_id,
        },
        () =>
          page
            .getByRole("button", { name: "Load more results", exact: true })
            .click(),
        (query) =>
          query.get("limit") === "5" &&
          query.get("evaluation_id") ===
            qualification.seedMetadata.evaluation_id &&
          query.has("cursor"),
      );
      currentPage = decodeSuccessEnvelope<ApiOperationData<"listResults">>(
        await next.response.body(),
        200,
        next.response.status(),
      );
      assertBaselineResultPage(
        currentPage,
        qualification.seedMetadata.result_snapshot_id,
        qualification.seedMetadata.label_snapshot_id,
      );
      const nextIds = sourceCaseIds(currentPage);
      expect(nextIds).toHaveLength(expectedSize);
      expect(nextIds.some((id) => pagedIds.includes(id))).toBe(false);
      pagedIds.push(...nextIds);
      const rows = page
        .getByRole("table", { name: "Frozen result rows" })
        .getByRole("row");
      await expect(rows).toHaveCount(pagedIds.length + 1);
    }
    expect(pagedIds).toHaveLength(12);
    expect(new Set(pagedIds).size).toBe(12);
    expect(pagedIds).toContain("ex-003");
    await reads.waitForIdle();

    const statusFilterRead = await captureOperation(
      page,
      "listResults",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
      },
      async () => {
        await page
          .getByRole("combobox", { name: "Status", exact: true })
          .selectOption("valid");
      },
      (query) =>
        query.get("status") === "valid" &&
        query.get("evaluation_id") === qualification.seedMetadata.evaluation_id,
    );
    const validStatusPage = decodeSuccessEnvelope<
      ApiOperationData<"listResults">
    >(statusFilterRead.body, 200, statusFilterRead.response.status());
    assertBaselineResultPage(
      validStatusPage,
      qualification.seedMetadata.result_snapshot_id,
      qualification.seedMetadata.label_snapshot_id,
    );
    expect(validStatusPage.filtered_count).toBe("10");
    const incorrectFilterRead = await captureOperation(
      page,
      "listResults",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
      },
      async () => {
        await page
          .getByRole("combobox", { name: "Assessment", exact: true })
          .selectOption("incorrect");
      },
      (query) =>
        query.get("status") === "valid" &&
        query.get("assessment_filter") === "incorrect" &&
        query.get("evaluation_id") === qualification.seedMetadata.evaluation_id,
    );
    const validIncorrectPage = decodeSuccessEnvelope<
      ApiOperationData<"listResults">
    >(incorrectFilterRead.body, 200, incorrectFilterRead.response.status());
    assertBaselineResultPage(
      validIncorrectPage,
      qualification.seedMetadata.result_snapshot_id,
      qualification.seedMetadata.label_snapshot_id,
    );
    expect(validIncorrectPage.filtered_count).toBe("2");
    expect(
      validIncorrectPage.items.every((item) => {
        const source = record(item.source);
        return source?.status === "valid" && source.set_correct === false;
      }),
    ).toBe(true);
    const taggedSource = originalPage.items
      .map((item) => record(item.source))
      .find(
        (source) =>
          typeof source?.split === "string" &&
          Array.isArray(source.tags) &&
          source.tags.length > 0 &&
          source.tags.every((tag) => typeof tag === "string"),
      );
    if (!taggedSource || typeof taggedSource.split !== "string")
      throw new Error("The seeded result rows had no authored split/tag pair.");
    const selectedSplit = taggedSource.split;
    const firstTag = Array.isArray(taggedSource.tags)
      ? taggedSource.tags.find((tag): tag is string => typeof tag === "string")
      : undefined;
    if (typeof firstTag !== "string")
      throw new Error("The seeded result rows had no authored tag value.");
    await page
      .getByRole("combobox", { name: "Assessment", exact: true })
      .selectOption("all");
    const splitRead = await captureOperation(
      page,
      "listResults",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
      },
      async () => {
        await page
          .getByRole("combobox", { name: "Split", exact: true })
          .selectOption(selectedSplit);
      },
      (query) =>
        query.get("split") === selectedSplit &&
        query.get("status") === "valid" &&
        query.get("evaluation_id") === qualification.seedMetadata.evaluation_id,
    );
    const splitPage = decodeSuccessEnvelope<ApiOperationData<"listResults">>(
      splitRead.body,
      200,
      splitRead.response.status(),
    );
    assertBaselineResultPage(
      splitPage,
      qualification.seedMetadata.result_snapshot_id,
      qualification.seedMetadata.label_snapshot_id,
    );
    const splitTagRead = await captureOperation(
      page,
      "listResults",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
      },
      async () => {
        await page.getByLabel("Tag", { exact: true }).fill(firstTag);
      },
      (query) =>
        query.get("split") === selectedSplit &&
        query.get("tag") === firstTag &&
        query.get("status") === "valid" &&
        query.get("evaluation_id") === qualification.seedMetadata.evaluation_id,
    );
    const splitTagPage = decodeSuccessEnvelope<ApiOperationData<"listResults">>(
      splitTagRead.body,
      200,
      splitTagRead.response.status(),
    );
    assertBaselineResultPage(
      splitTagPage,
      qualification.seedMetadata.result_snapshot_id,
      qualification.seedMetadata.label_snapshot_id,
    );
    expect(splitTagPage.filtered_count).not.toBe("0");
    expect(
      splitTagPage.items.every((item) => {
        const source = record(item.source);
        return (
          source?.split === selectedSplit &&
          Array.isArray(source.tags) &&
          source.tags.includes(firstTag)
        );
      }),
    ).toBe(true);
    const allStatusRead = await captureOperation(
      page,
      "listResults",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
      },
      async () => {
        await page
          .getByRole("combobox", { name: "Status", exact: true })
          .selectOption("");
      },
      (query) =>
        !query.has("status") &&
        query.get("split") === taggedSource.split &&
        query.get("tag") === firstTag &&
        query.get("evaluation_id") === qualification.seedMetadata.evaluation_id,
    );
    const allStatusPage = decodeSuccessEnvelope<
      ApiOperationData<"listResults">
    >(allStatusRead.body, 200, allStatusRead.response.status());
    assertBaselineResultPage(
      allStatusPage,
      qualification.seedMetadata.result_snapshot_id,
      qualification.seedMetadata.label_snapshot_id,
    );
    const allSplitRead = await captureOperation(
      page,
      "listResults",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
      },
      async () => {
        await page
          .getByRole("combobox", { name: "Split", exact: true })
          .selectOption("");
      },
      (query) =>
        !query.has("split") &&
        query.get("tag") === firstTag &&
        query.get("evaluation_id") === qualification.seedMetadata.evaluation_id,
    );
    const allSplitPage = decodeSuccessEnvelope<ApiOperationData<"listResults">>(
      await allSplitRead.response.body(),
      200,
      allSplitRead.response.status(),
    );
    assertBaselineResultPage(
      allSplitPage,
      qualification.seedMetadata.result_snapshot_id,
      qualification.seedMetadata.label_snapshot_id,
    );
    const allTagRead = await captureOperation(
      page,
      "listResults",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
      },
      async () => {
        await page.getByLabel("Tag", { exact: true }).fill("");
      },
      (query) =>
        !query.has("tag") &&
        query.get("evaluation_id") === qualification.seedMetadata.evaluation_id,
    );
    const allTagPage = decodeSuccessEnvelope<ApiOperationData<"listResults">>(
      await allTagRead.response.body(),
      200,
      allTagRead.response.status(),
    );
    assertBaselineResultPage(
      allTagPage,
      qualification.seedMetadata.result_snapshot_id,
      qualification.seedMetadata.label_snapshot_id,
    );
    const pageSizeReset = await captureOperation(
      page,
      "listResults",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
      },
      async () => {
        await page
          .getByRole("combobox", { name: "Results per page", exact: true })
          .selectOption("50");
      },
      (query) =>
        query.get("limit") === "50" &&
        query.get("evaluation_id") === qualification.seedMetadata.evaluation_id,
    );
    const resetPage = decodeSuccessEnvelope<ApiOperationData<"listResults">>(
      await pageSizeReset.response.body(),
      200,
      pageSizeReset.response.status(),
    );
    assertBaselineResultPage(
      resetPage,
      qualification.seedMetadata.result_snapshot_id,
      qualification.seedMetadata.label_snapshot_id,
    );
    await reads.waitForIdle();

    await page
      .getByRole("button", { name: "Content category", exact: true })
      .click();
    await page.getByRole("button", { name: "Examples", exact: true }).click();
    const exampleDataset = page.getByRole("combobox", {
      name: "Dataset",
      exact: true,
    });
    if (
      (await exampleDataset.inputValue()) !==
      qualification.seedMetadata.dataset_id
    ) {
      const listedCases = await captureOperation(
        page,
        "list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get",
        {
          registration_id: registrationId,
          dataset_id: qualification.seedMetadata.dataset_id,
        },
        async () => {
          const selected = await exampleDataset.inputValue();
          if (selected) await exampleDataset.selectOption("");
          await exampleDataset.selectOption(
            qualification.seedMetadata.dataset_id,
          );
        },
      );
      decodeSuccessEnvelope<
        ApiOperationData<"list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get">
      >(listedCases.body, 200, listedCases.response.status());
    } else {
      await exampleDataset.selectOption("");
      const listedCases = await captureOperation(
        page,
        "list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get",
        {
          registration_id: registrationId,
          dataset_id: qualification.seedMetadata.dataset_id,
        },
        async () => {
          await exampleDataset.selectOption(
            qualification.seedMetadata.dataset_id,
          );
        },
      );
      decodeSuccessEnvelope<
        ApiOperationData<"list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get">
      >(listedCases.body, 200, listedCases.response.status());
    }
    const backingCaseRead = await captureOperation(
      page,
      "read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get",
      {
        registration_id: registrationId,
        dataset_id: qualification.seedMetadata.dataset_id,
        case_id: "ex-003",
      },
      () =>
        page
          .getByRole("table", { name: /^Cases in / })
          .getByRole("button", { name: "ex-003", exact: true })
          .click(),
    );
    const backingCase = decodeSuccessEnvelope<
      ApiOperationData<"read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get">
    >(backingCaseRead.body, 200, backingCaseRead.response.status());
    const backingInputSource = backingCase.case.record.input_source;
    if (typeof backingInputSource !== "string")
      throw new Error("The authored case input source was not a string.");
    const returnedRuns = await captureOperation(
      page,
      "listRuns",
      { registration_id: registrationId },
      async () => {
        await page.getByRole("button", { name: "Runs", exact: true }).click();
        await expect(
          page.getByRole("heading", { name: "Runs", exact: true }),
        ).toBeVisible();
      },
    );
    const returnedRunPage = decodeSuccessEnvelope<ApiOperationData<"listRuns">>(
      returnedRuns.body,
      200,
      returnedRuns.response.status(),
    );
    expect(
      returnedRunPage.items.some(
        (item) => item.run_id === qualification.seedMetadata.run_id,
      ),
    ).toBe(true);
    const returnedResults = await captureOperation(
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
    const returnedResultPage = decodeSuccessEnvelope<
      ApiOperationData<"listResults">
    >(
      await returnedResults.response.body(),
      200,
      returnedResults.response.status(),
    );
    expect(returnedResultPage.result_snapshot_id).toBe(
      qualification.seedMetadata.result_snapshot_id,
    );
    const returnedPinnedResults = await captureOperation(
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
    const returnedPinnedPage = decodeSuccessEnvelope<
      ApiOperationData<"listResults">
    >(
      await returnedPinnedResults.response.body(),
      200,
      returnedPinnedResults.response.status(),
    );
    assertBaselineResultPage(
      returnedPinnedPage,
      qualification.seedMetadata.result_snapshot_id,
      qualification.seedMetadata.label_snapshot_id,
    );
    await reads.waitForIdle();

    await qualification.enterPhase("probability-and-label-review");
    const caseRow = page
      .getByRole("table", { name: "Frozen result rows" })
      .getByRole("row")
      .filter({ hasText: "ex-003" });
    const caseDetail = await captureOperation(
      page,
      "readResult",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
        case_id: "ex-003",
      },
      () =>
        caseRow.getByRole("button", { name: "ex-003", exact: true }).click(),
      (query) =>
        query.get("expected_result_snapshot_id") ===
          qualification.seedMetadata.result_snapshot_id &&
        query.get("expected_label_snapshot_id") ===
          qualification.seedMetadata.label_snapshot_id &&
        query.get("include_input") === "false" &&
        query.get("include_request") === "false" &&
        query.get("include_response") === "false" &&
        query.get("include_attempts") === "false",
    );
    const detail = decodeSuccessEnvelope<ApiOperationData<"readResult">>(
      await caseDetail.response.body(),
      200,
      caseDetail.response.status(),
    );
    expect(detail.context.result_snapshot_id).toBe(
      qualification.seedMetadata.result_snapshot_id,
    );
    expect(detail.context.label_snapshot_id).toBe(
      qualification.seedMetadata.label_snapshot_id,
    );
    expect(
      detail.probabilities.map((item) => [item.option_id, item.probability]),
    ).toEqual([
      ["report", "0.62"],
      ["question", "0.2"],
      ["request", "0.14"],
      ["other", "0.04"],
    ]);
    const caseInspector = page.getByRole("region", {
      name: "Case ex-003 inspection",
    });
    const inputToggle = caseInspector.getByLabel("Include input", {
      exact: true,
    });
    const revealedInput = await captureOperation(
      page,
      "readResult",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
        case_id: "ex-003",
      },
      async () => {
        await inputToggle.check();
      },
      (query) =>
        query.get("evaluation_id") ===
          qualification.seedMetadata.evaluation_id &&
        query.get("expected_result_snapshot_id") ===
          qualification.seedMetadata.result_snapshot_id &&
        query.get("expected_label_snapshot_id") ===
          qualification.seedMetadata.label_snapshot_id &&
        query.get("include_input") === "true" &&
        query.get("include_request") === "false" &&
        query.get("include_response") === "false" &&
        query.get("include_attempts") === "false",
    );
    const revealedDetail = decodeSuccessEnvelope<
      ApiOperationData<"readResult">
    >(
      await revealedInput.response.body(),
      200,
      revealedInput.response.status(),
    );
    const revealedSource = record(revealedDetail.source)?.input_source;
    expect(revealedSource === backingInputSource).toBe(true);
    const displayedSource = await caseInspector
      .locator("pre.source-editor")
      .textContent();
    expect(displayedSource === backingInputSource).toBe(true);
    const hiddenAgain = await captureOperation(
      page,
      "readResult",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
        case_id: "ex-003",
      },
      async () => {
        await inputToggle.uncheck();
      },
      (query) =>
        query.get("evaluation_id") ===
          qualification.seedMetadata.evaluation_id &&
        query.get("expected_result_snapshot_id") ===
          qualification.seedMetadata.result_snapshot_id &&
        query.get("expected_label_snapshot_id") ===
          qualification.seedMetadata.label_snapshot_id &&
        query.get("include_input") === "false" &&
        query.get("include_request") === "false" &&
        query.get("include_response") === "false" &&
        query.get("include_attempts") === "false",
    );
    const hiddenAgainDetail = decodeSuccessEnvelope<
      ApiOperationData<"readResult">
    >(await hiddenAgain.response.body(), 200, hiddenAgain.response.status());
    expect(record(hiddenAgainDetail.source)?.input_source).toBeNull();
    await expect(caseInspector.locator("pre.source-editor")).toHaveCount(0);
    const otherCaseRow = page
      .getByRole("table", { name: "Frozen result rows" })
      .getByRole("row")
      .filter({ hasText: "ex-004" });
    const changedCase = await captureOperation(
      page,
      "readResult",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
        case_id: "ex-004",
      },
      async () => {
        await otherCaseRow
          .getByRole("button", { name: "ex-004", exact: true })
          .click();
      },
      (query) =>
        query.get("evaluation_id") ===
          qualification.seedMetadata.evaluation_id &&
        query.get("expected_result_snapshot_id") ===
          qualification.seedMetadata.result_snapshot_id &&
        query.get("expected_label_snapshot_id") ===
          qualification.seedMetadata.label_snapshot_id &&
        query.get("include_input") === "false",
    );
    const changedCaseDetail = decodeSuccessEnvelope<
      ApiOperationData<"readResult">
    >(await changedCase.response.body(), 200, changedCase.response.status());
    expect(changedCaseDetail.context.result_snapshot_id).toBe(
      qualification.seedMetadata.result_snapshot_id,
    );
    const changedCaseInspector = page.getByRole("region", {
      name: "Case ex-004 inspection",
    });
    await expect(changedCaseInspector.locator("pre.source-editor")).toHaveCount(
      0,
    );
    await reads.waitForIdle();
    await page
      .getByRole("table", { name: "Frozen result rows" })
      .getByRole("button", { name: "ex-003", exact: true })
      .click();
    await expect(caseInspector).toContainText("Case ex-003");
    await reads.waitForIdle();
    await expect(
      caseInspector.getByRole("heading", { name: "Reported probabilities" }),
    ).toBeVisible();
    for (const exactProbability of [
      "Report · report: 0.62",
      "Question · question: 0.2",
      "Request · request: 0.14",
      "Other · other: 0.04",
    ])
      await expect(
        caseInspector.getByText(exactProbability, { exact: true }),
      ).toBeVisible();
    await caseInspector
      .getByRole("button", { name: "Review current label", exact: true })
      .click();
    const labelDialog = page.getByRole("dialog", {
      name: "Review current label",
      exact: true,
    });
    await expect(
      labelDialog.getByRole("region", { name: "Frozen label expectation" }),
    ).toContainText("question");
    const questionOption = labelDialog.getByLabel("Question · question", {
      exact: true,
    });
    const reportOption = labelDialog.getByLabel("Report · report", {
      exact: true,
    });
    await expect(questionOption).toBeChecked();
    await expect(reportOption).not.toBeChecked();
    await questionOption.uncheck();
    await reportOption.check();
    let labelWriteCount = 0;
    const countLabelWrite = (request: import("@playwright/test").Request) => {
      if (
        request.method() === "POST" &&
        new URL(request.url()).pathname ===
          `/api/v1/projects/${registrationId}/decisions/${qualification.seedMetadata.decision_id}/datasets/${qualification.seedMetadata.dataset_id}/labels/batch`
      )
        labelWriteCount += 1;
    };
    page.on("request", countLabelWrite);
    const labelSave = await captureOperation(
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
    >(await labelSave.response.body(), 200, labelSave.response.status());
    expect(labelReceipt.changes).toHaveLength(1);
    expect(labelReceipt.changes[0]?.case_id).toBe("ex-003");
    expect(labelReceipt.changes[0]?.label?.acceptable_option_ids).toEqual([
      "report",
    ]);
    await reads.waitForIdle();
    await expect(
      labelDialog.getByRole("region", { name: "Current mutable label" }),
    ).toContainText("report");
    await page.keyboard.press("Escape");
    await expect(labelDialog).toBeHidden();
    await expect(caseRow).toContainText("question");
    expect(labelWriteCount).toBe(1);
    const resultsPath = `/api/v1/projects/${registrationId}/runs/${qualification.seedMetadata.run_id}/results`;
    let failedRead = false;
    const failFirstResultsRead = async (
      route: import("@playwright/test").Route,
    ) => {
      if (!failedRead && route.request().method() === "GET") {
        failedRead = true;
        const body = JSON.stringify({
          schema_version: 1,
          error: {
            code: "internal_error",
            message: "Request failed.",
            reason: "storage_io",
          },
        });
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body,
        });
      } else {
        await route.continue();
      }
    };
    const resultsMatcher = (url: URL) => url.pathname === resultsPath;
    try {
      await page.route(resultsMatcher, failFirstResultsRead);
      const failedRefresh = await captureResponse(
        page,
        (response) =>
          response.request().method() === "GET" &&
          new URL(response.url()).pathname === resultsPath,
        () =>
          page
            .getByRole("button", {
              name: "Refresh frozen results",
              exact: true,
            })
            .click(),
      );
      expect(failedRead).toBe(true);
      expect(failedRefresh.response.status()).toBe(503);
      const failureBody: unknown = JSON.parse(
        failedRefresh.body.toString("utf8"),
      );
      const failureEnvelope = record(failureBody);
      const failure = record(failureEnvelope?.error);
      expect(failure?.code).toBe("internal_error");
      expect(failure?.reason).toBe("storage_io");
      await expect(page.getByRole("alert")).toBeVisible();
    } finally {
      await page.unroute(resultsMatcher, failFirstResultsRead);
    }
    const refreshedResults = await captureOperation(
      page,
      "listResults",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
      },
      () =>
        page
          .getByRole("button", {
            name: "Refresh frozen results",
            exact: true,
          })
          .click(),
      (query) =>
        query.get("evaluation_id") ===
          qualification.seedMetadata.evaluation_id &&
        query.get("expected_result_snapshot_id") ===
          qualification.seedMetadata.result_snapshot_id &&
        query.get("expected_label_snapshot_id") ===
          qualification.seedMetadata.label_snapshot_id,
    );
    const refreshedResultPage = decodeSuccessEnvelope<
      ApiOperationData<"listResults">
    >(
      await refreshedResults.response.body(),
      200,
      refreshedResults.response.status(),
    );
    assertBaselineResultPage(
      refreshedResultPage,
      qualification.seedMetadata.result_snapshot_id,
      qualification.seedMetadata.label_snapshot_id,
    );
    expect(labelWriteCount).toBe(1);
    page.off("request", countLabelWrite);
    await reads.waitForIdle();

    const evaluationControls = page.getByRole("region", {
      name: "Saved result evaluation",
    });
    const reevaluation = await captureOperation(
      page,
      "reevaluateRun",
      {
        registration_id: registrationId,
        run_id: qualification.seedMetadata.run_id,
      },
      () =>
        evaluationControls
          .getByRole("button", {
            name: "Re-evaluate saved answers",
            exact: true,
          })
          .click(),
    );
    const reevaluated = decodeSuccessEnvelope<
      ApiOperationData<"reevaluateRun">
    >(await reevaluation.response.body(), 200, reevaluation.response.status());
    expect(reevaluated.run_id).toBe(qualification.seedMetadata.run_id);
    expect(reevaluated.result_snapshot_id).toBe(
      qualification.seedMetadata.result_snapshot_id,
    );
    expect(reevaluated.label_snapshot_id).not.toBe(
      qualification.seedMetadata.label_snapshot_id,
    );
    expect(reevaluated.mode).toBe("saved_answer_reevaluation");
    expect(reevaluated.evaluation_id).not.toBe(
      qualification.seedMetadata.evaluation_id,
    );
    expect(reevaluated.replayed).toBe(false);
    const reevaluationSummary = record(reevaluated.metrics.summary);
    const reevaluationQuality = record(reevaluationSummary?.quality);
    const reevaluationCoverage = record(reevaluationSummary?.coverage);
    expect(reevaluationQuality?.numerator).toBe(7);
    expect(reevaluationQuality?.denominator).toBe(8);
    expect(reevaluationCoverage?.numerator).toBe(10);
    expect(reevaluationCoverage?.denominator).toBe(12);
    qualification.setWitness(
      "reevaluation_content_hash",
      reevaluated.content_hash,
    );
    qualification.setWitness("reevaluation_id", reevaluated.evaluation_id);
    await reads.waitForIdle();

    await qualification.enterPhase("evaluation-switch-clears-raw-source");
    const runList = await captureOperation(
      page,
      "listRuns",
      { registration_id: registrationId },
      () => page.getByRole("button", { name: "Runs", exact: true }).click(),
    );
    const listedRuns = decodeSuccessEnvelope<ApiOperationData<"listRuns">>(
      runList.body,
      200,
      runList.response.status(),
    );
    expect(
      listedRuns.items.some(
        (item) => item.run_id === qualification.seedMetadata.run_id,
      ),
    ).toBe(true);
    const reopenedRun = await captureOperation(
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
    const reopenedPage = decodeSuccessEnvelope<ApiOperationData<"listResults">>(
      await reopenedRun.response.body(),
      200,
      reopenedRun.response.status(),
    );
    expect(reopenedPage.result_snapshot_id).toBe(
      qualification.seedMetadata.result_snapshot_id,
    );
    const switchedEvaluation = await captureOperation(
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
          .selectOption(reevaluated.evaluation_id);
      },
      (query) =>
        query.get("evaluation_id") === reevaluated.evaluation_id &&
        query.get("expected_result_snapshot_id") ===
          qualification.seedMetadata.result_snapshot_id,
    );
    const switchedPage = decodeSuccessEnvelope<ApiOperationData<"listResults">>(
      await switchedEvaluation.response.body(),
      200,
      switchedEvaluation.response.status(),
    );
    expect(switchedPage.evaluation_id).toBe(reevaluated.evaluation_id);
    expect(switchedPage.result_snapshot_id).toBe(
      qualification.seedMetadata.result_snapshot_id,
    );
    expect(switchedPage.label_snapshot_id).toBe(reevaluated.label_snapshot_id);
    await expect(page.locator("pre.source-editor")).toHaveCount(0);
    await reads.waitForIdle();

    await qualification.enterPhase("annotation-lost-ack-and-replay");
    const note = "M12 authored note for ex-003";
    const annotationPath = `/api/v1/projects/${registrationId}/runs/${qualification.seedMetadata.run_id}/annotations`;
    const annotationLoss = await installLostAcknowledgement(
      page,
      annotationPath,
      200,
    );
    try {
      await caseInspector
        .getByRole("button", { name: "Add annotation", exact: true })
        .click();
      const annotationDialog = page.getByRole("dialog", {
        name: "Case annotations",
        exact: true,
      });
      await annotationDialog.getByLabel("Note", { exact: true }).fill(note);
      await annotationDialog
        .getByRole("button", { name: "Save annotation", exact: true })
        .click();
      await expect(
        annotationDialog.getByRole("button", {
          name: "Retry original unchanged annotation",
          exact: true,
        }),
      ).toBeVisible();
      const first = annotationLoss.firstObservation();
      expect(first?.firstStatus).toBe(200);
      await annotationDialog
        .getByRole("button", {
          name: "Retry original unchanged annotation",
          exact: true,
        })
        .click();
      await expect(annotationDialog.getByRole("status")).toContainText(
        "Annotation",
      );
      const replay = annotationLoss.observation();
      expect(replay).toBeDefined();
      expect(replay?.replayStatus).toBe(200);
      expect(replay?.sameRequestBytes).toBe(true);
      expect(replay?.firstRequestHash).toBe(replay?.replayRequestHash);
      const firstReceipt = decodeSuccessEnvelope<
        ApiOperationData<"addAnnotation">
      >(
        replay?.firstResponseBody ?? Buffer.alloc(0),
        200,
        replay?.firstStatus ?? 0,
      );
      const replayReceipt = decodeSuccessEnvelope<
        ApiOperationData<"addAnnotation">
      >(
        replay?.replayResponseBody ?? Buffer.alloc(0),
        200,
        replay?.replayStatus ?? 0,
      );
      expect(replayReceipt.annotation_id).toBe(firstReceipt.annotation_id);
      expect(firstReceipt.replayed).toBe(false);
      expect(replayReceipt.replayed).toBe(true);
      expect(replayReceipt.note).toBe(note);
      qualification.setWitness(
        "annotation_request_sha256",
        replay?.firstRequestHash ?? "",
      );
      qualification.setWitness("annotation_id", replayReceipt.annotation_id);
      await expect(
        annotationDialog
          .getByRole("list", { name: "Saved annotations" })
          .getByText(note, { exact: true }),
      ).toBeVisible();
      await reads.waitForIdle();
      await page.keyboard.press("Escape");
      await expect(annotationDialog).toBeHidden();
    } finally {
      await annotationLoss.dispose();
    }

    await qualification.enterPhase("explicit-regression-oracle");
    await caseInspector
      .getByRole("button", { name: "Add regression example", exact: true })
      .click();
    const regressionDialog = page.getByRole("dialog", {
      name: "Add regression example for Content category",
      exact: true,
    });
    const expectedQuestion = regressionDialog.getByLabel(
      "Question · question",
      { exact: true },
    );
    await expect(expectedQuestion).not.toBeChecked();
    await expectedQuestion.check();
    await regressionDialog
      .getByLabel("Reason", { exact: true })
      .fill("Independent authored expectation after manual review.");
    const regressionSave = await captureOperation(
      page,
      "addRegression",
      {
        registration_id: registrationId,
        decision_id: qualification.seedMetadata.decision_id,
      },
      () =>
        regressionDialog
          .getByRole("button", { name: "Save regression example", exact: true })
          .click(),
    );
    const regression = decodeSuccessEnvelope<ApiOperationData<"addRegression">>(
      await regressionSave.response.body(),
      200,
      regressionSave.response.status(),
    );
    expect(regression.case_id).toBe("ex-003");
    expect(regression.source_run_id).toBe(qualification.seedMetadata.run_id);
    expect(regression.source_result_snapshot_id).toBe(
      qualification.seedMetadata.result_snapshot_id,
    );
    expect(regression.acceptable_option_ids).toEqual(["question"]);
    expect(regression.provenance).toBe("human");
    expect(regression.reason).toBe(
      "Independent authored expectation after manual review.",
    );
    qualification.setWitness("regression_id", regression.regression_id);
    await reads.waitForIdle();
    await page
      .getByRole("button", { name: "Regression examples", exact: true })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Regression examples for Content category",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("table", { name: "Service-reported regression records" }),
    ).toContainText(regression.regression_id);
    await expect(
      page.getByRole("table", { name: "Service-reported regression records" }),
    ).toContainText("question");

    const finalCounts = await waitForCountFile(
      qualification.controlDirectory,
      (counts) =>
        counts.fixture_dispatch_calls === 0 &&
        counts.for_case_calls === 0 &&
        counts.live_dispatch_calls === 0,
    );
    expect(finalCounts.fixture_dispatch_calls).toBe(0);
    expect(finalCounts.for_case_calls).toBe(0);
    expect(finalCounts.live_dispatch_calls).toBe(0);
    qualification.setCounts(finalCounts);
    await qualification.captureScreenshot(page, "m12-saved-answers.png");
    succeeded = true;
  } finally {
    await finishDebuggingQualification(qualification, reads, succeeded);
  }
}

export async function runComparisonWorkflow(
  page: Page,
  testInfo: TestInfo,
): Promise<void> {
  const context = await startDebuggingQualification(page, testInfo, "C");
  const { qualification, registrationId, reads } = context;
  let succeeded = false;
  try {
    await qualification.enterPhase("review-authored-revised-run");
    await page
      .getByRole("button", { name: "Content category", exact: true })
      .click();
    const runReview = page.getByRole("dialog", {
      name: "Review a run",
      exact: true,
    });
    await expect(runReview).toBeVisible();
    await runReview
      .getByRole("combobox", { name: "Dataset", exact: true })
      .selectOption(qualification.seedMetadata.dataset_id);
    await runReview
      .getByRole("combobox", { name: "Fixture set", exact: true })
      .selectOption(qualification.seedMetadata.fixture_set_id);
    await runReview
      .getByLabel("Lifetime request cap (1–9007199254740991)")
      .fill("12");
    await runReview.getByLabel("Concurrency (1–64)").fill("1");
    await runReview.getByLabel("Timeout seconds (1–600)").fill("30");
    await runReview.getByLabel("Deadline seconds (1–86400)").fill("120");
    await runReview
      .getByLabel("Rate/overload retries per case (0–1)")
      .fill("0");
    const previewCapture = await captureOperation(
      page,
      "previewRun",
      { registration_id: registrationId },
      () =>
        runReview
          .getByRole("button", { name: "Review run", exact: true })
          .click(),
    );
    const preview = decodeSuccessEnvelope<ApiOperationData<"previewRun">>(
      await previewCapture.response.body(),
      200,
      previewCapture.response.status(),
    );
    expect(preview.initial_requests).toBe("11");
    expect(preview.selected_case_ids).toHaveLength(12);
    const previewCases = new Map(
      preview.case_reviews.map((item) => [item.case_id, item]),
    );
    expect(previewCases.get("ex-003")?.request_hash).toMatch(/^[a-f0-9]{64}$/);
    expect(previewCases.get("ex-003")?.input_error).toBeNull();
    expect(previewCases.get("ex-011")?.input_error).not.toBeNull();
    await reads.waitForIdle();
    const callsBefore = await waitForCountFile(
      qualification.controlDirectory,
      (counts) =>
        counts.fixture_dispatch_calls === 0 &&
        counts.for_case_calls === 0 &&
        counts.live_dispatch_calls === 0,
    );
    expect(callsBefore).toMatchObject({
      fixture_dispatch_calls: 0,
      for_case_calls: 0,
      live_dispatch_calls: 0,
    });
    await expect(
      runReview.getByRole("button", {
        name: "Start reviewed run",
        exact: true,
      }),
    ).toBeEnabled();

    const startedCapture = await captureOperation(
      page,
      "startRun",
      { registration_id: registrationId },
      () =>
        runReview
          .getByRole("button", { name: "Start reviewed run", exact: true })
          .click(),
    );
    const started = decodeSuccessEnvelope<ApiOperationData<"startRun">>(
      await startedCapture.response.body(),
      202,
      startedCapture.response.status(),
    );
    const revisedRunId = started.run_id;
    if (revisedRunId === qualification.seedMetadata.run_id)
      throw new Error(
        "The revised fixture run reused the original run identity.",
      );
    qualification.setWitness("revised_run_id", revisedRunId);
    await expect(
      page.getByRole("heading", { name: `Run ${revisedRunId}`, exact: true }),
    ).toBeVisible();
    await expect(page.locator(".run-detail .lead")).toContainText("completed");
    const executionCounts = await waitForCountFile(
      qualification.controlDirectory,
      (counts) =>
        counts.fixture_dispatch_calls === 11 &&
        counts.for_case_calls === 11 &&
        counts.live_dispatch_calls === 0,
      30_000,
    );
    expect(executionCounts.fixture_dispatch_by_case["ex-011"] ?? 0).toBe(0);
    expect(executionCounts.for_case_by_case["ex-011"] ?? 0).toBe(0);
    expect(
      Object.values(executionCounts.for_case_by_case).filter(
        (count) => count === 1,
      ),
    ).toHaveLength(11);
    qualification.setCounts(executionCounts);
    await reads.waitForIdle();

    await qualification.enterPhase("save-revised-evaluation");
    const evaluationControls = page.getByRole("region", {
      name: "Saved result evaluation",
    });
    const saveEvaluation = await captureOperation(
      page,
      "createEvaluation",
      { registration_id: registrationId, run_id: revisedRunId },
      () =>
        evaluationControls
          .getByRole("button", { name: "Save evaluation", exact: true })
          .click(),
    );
    const revisedEvaluation = decodeSuccessEnvelope<
      ApiOperationData<"createEvaluation">
    >(
      await saveEvaluation.response.body(),
      200,
      saveEvaluation.response.status(),
    );
    expect(revisedEvaluation.run_id).toBe(revisedRunId);
    expect(revisedEvaluation.mode).toBe("original");
    expect(revisedEvaluation.label_snapshot_id).toBe(
      qualification.seedMetadata.label_snapshot_id,
    );
    expect(revisedEvaluation.evaluation_id).not.toBe(
      qualification.seedMetadata.evaluation_id,
    );
    const revisedSummary = record(revisedEvaluation.metrics.summary);
    const revisedQuality = record(revisedSummary?.quality);
    expect(revisedQuality?.numerator).toBe(7);
    expect(revisedQuality?.denominator).toBe(8);
    qualification.setWitness(
      "revised_evaluation_id",
      revisedEvaluation.evaluation_id,
    );
    qualification.setWitness(
      "revised_result_snapshot_id",
      revisedEvaluation.result_snapshot_id,
    );
    await reads.waitForIdle();

    await qualification.enterPhase("create-and-replay-comparison");
    await page
      .getByRole("button", { name: "Comparisons", exact: true })
      .click();
    const left = page.getByLabel("Left saved evaluation ID", { exact: true });
    const right = page.getByLabel("Right saved evaluation ID", { exact: true });
    await left.fill(qualification.seedMetadata.evaluation_id);
    await right.fill(revisedEvaluation.evaluation_id);
    await page
      .getByRole("button", { name: "Verify saved evaluations", exact: true })
      .click();
    await expect(
      page.getByRole("region", { name: "Verified evaluation context" }),
    ).toContainText(qualification.seedMetadata.evaluation_id);
    await expect(
      page.getByRole("region", { name: "Verified evaluation context" }),
    ).toContainText(revisedEvaluation.evaluation_id);
    const comparisonPath = `/api/v1/projects/${registrationId}/comparisons`;
    const lostComparisonAck = await installLostAcknowledgement(
      page,
      comparisonPath,
      200,
    );
    let originalComparison: ApiOperationData<"createComparison"> | undefined;
    let replayedComparison: ApiOperationData<"createComparison"> | undefined;
    try {
      await page
        .getByRole("button", { name: "Create saved comparison", exact: true })
        .click();
      await expect(
        page.getByRole("button", {
          name: "Retry original unchanged comparison",
          exact: true,
        }),
      ).toBeVisible();
      const observation = lostComparisonAck.firstObservation();
      expect(observation?.firstStatus).toBe(200);
      originalComparison = decodeSuccessEnvelope<
        ApiOperationData<"createComparison">
      >(
        observation?.firstResponseBody ?? Buffer.alloc(0),
        200,
        observation?.firstStatus ?? 0,
      );
      await page
        .getByRole("button", {
          name: "Retry original unchanged comparison",
          exact: true,
        })
        .click();
      await expect(
        page.getByRole("button", {
          name: "Open saved comparison",
          exact: true,
        }),
      ).toBeVisible();
      const replay = lostComparisonAck.observation();
      expect(replay).toBeDefined();
      expect(replay?.sameRequestBytes).toBe(true);
      expect(replay?.firstRequestHash).toBe(replay?.replayRequestHash);
      replayedComparison = decodeSuccessEnvelope<
        ApiOperationData<"createComparison">
      >(
        replay?.replayResponseBody ?? Buffer.alloc(0),
        200,
        replay?.replayStatus ?? 0,
      );
      expect(replayedComparison.comparison_id).toBe(
        originalComparison.comparison_id,
      );
      expect(originalComparison.replayed).toBe(false);
      expect(replayedComparison.replayed).toBe(true);
      expect(replayedComparison.left_evaluation_id).toBe(
        qualification.seedMetadata.evaluation_id,
      );
      expect(replayedComparison.right_evaluation_id).toBe(
        revisedEvaluation.evaluation_id,
      );
      qualification.setWitness(
        "comparison_id",
        replayedComparison.comparison_id,
      );
      qualification.setWitness(
        "comparison_request_sha256",
        replay?.firstRequestHash ?? "",
      );
    } finally {
      await lostComparisonAck.dispose();
    }
    if (!replayedComparison)
      throw new Error("The retained comparison receipt was unavailable.");
    const outcomeData = record(replayedComparison.outcomes);
    const primaryCounts = record(outcomeData?.primary_counts);
    expect(primaryCounts).toMatchObject({
      both_correct: "6",
      improved: "1",
      regressed: "0",
      both_wrong: "1",
      unlabelled_agreement: "2",
      unavailable_answer: "2",
    });
    const allBuckets = [
      "left_only",
      "right_only",
      "changed_input",
      "changed_question_options",
      "changed_expectations",
      "unavailable_answer",
      "excluded_expectation",
      "unlabelled_agreement",
      "unlabelled_disagreement",
      "both_correct",
      "improved",
      "regressed",
      "both_wrong",
    ];
    expect(Object.keys(primaryCounts ?? {}).sort()).toEqual(
      [...allBuckets].sort(),
    );
    const bucketTotal = allBuckets.reduce(
      (total, bucket) => total + BigInt(String(primaryCounts?.[bucket])),
      0n,
    );
    expect(bucketTotal).toBe(12n);
    expect(outcomeData?.quality_denominator).toBe("8");
    expect(outcomeData?.left_correct_count).toBe("6");
    expect(outcomeData?.right_correct_count).toBe("7");
    expect(outcomeData?.unlabelled_denominator).toBe("2");
    for (const bucket of allBuckets) {
      if (
        [
          "unavailable_answer",
          "both_correct",
          "improved",
          "both_wrong",
          "unlabelled_agreement",
        ].includes(bucket)
      )
        continue;
      if (bucket === "regressed") continue;
      expect(primaryCounts?.[bucket]).toBe("0");
    }
    expect(primaryCounts?.quality_denominator).toBeUndefined();
    await reads.waitForIdle();
    await qualification.captureScreenshot(page, "m12-comparison-original.png");

    await qualification.enterPhase("reverse-comparison-independent-intent");
    await page
      .getByRole("button", { name: "Comparisons", exact: true })
      .click();
    await left.fill(revisedEvaluation.evaluation_id);
    await right.fill(qualification.seedMetadata.evaluation_id);
    await page
      .getByRole("button", { name: "Verify saved evaluations", exact: true })
      .click();
    await expect(
      page.getByRole("button", {
        name: "Create saved comparison",
        exact: true,
      }),
    ).toBeEnabled();
    const reversedCapture = await captureOperation(
      page,
      "createComparison",
      { registration_id: registrationId },
      () =>
        page
          .getByRole("button", { name: "Create saved comparison", exact: true })
          .click(),
    );
    const reversed = decodeSuccessEnvelope<
      ApiOperationData<"createComparison">
    >(
      await reversedCapture.response.body(),
      200,
      reversedCapture.response.status(),
    );
    expect(reversed.comparison_id).not.toBe(replayedComparison.comparison_id);
    expect(reversed.left_evaluation_id).toBe(revisedEvaluation.evaluation_id);
    expect(reversed.right_evaluation_id).toBe(
      qualification.seedMetadata.evaluation_id,
    );
    const reversedCounts = record(record(reversed.outcomes)?.primary_counts);
    expect(reversedCounts?.improved).toBe("0");
    expect(reversedCounts?.regressed).toBe("1");
    const reversedOutcomes = record(reversed.outcomes);
    expect(reversedOutcomes?.quality_denominator).toBe("8");
    expect(reversedOutcomes?.left_correct_count).toBe("7");
    expect(reversedOutcomes?.right_correct_count).toBe("6");
    expect(reversedOutcomes?.unlabelled_denominator).toBe("2");
    for (const bucket of allBuckets) {
      if (bucket === "improved" || bucket === "regressed") continue;
      expect(reversedCounts?.[bucket]).toBe(primaryCounts?.[bucket]);
    }
    qualification.setWitness("reversed_comparison_id", reversed.comparison_id);
    await reads.waitForIdle();

    const finalCounts = await waitForCountFile(
      qualification.controlDirectory,
      (counts) =>
        counts.fixture_dispatch_calls === 11 &&
        counts.for_case_calls === 11 &&
        counts.live_dispatch_calls === 0,
    );
    expect(finalCounts.fixture_dispatch_calls).toBe(11);
    expect(finalCounts.for_case_calls).toBe(11);
    expect(finalCounts.live_dispatch_calls).toBe(0);
    qualification.setCounts(finalCounts);
    await qualification.captureScreenshot(page, "m12-comparison-reversed.png");
    succeeded = true;
  } finally {
    await finishDebuggingQualification(qualification, reads, succeeded);
  }
}
