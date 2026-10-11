import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLayoutEffect } from "react";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";
import type {
  ApiOperationBody,
  ApiOperationData,
  ApiResult,
} from "../../api/client";
import { disconnectedWorkspace } from "../../workspace/gateway";
import { WorkspaceNavigation } from "../../workspace/navigation";
import { ReportPage, ReportSheet } from "./ReportPages";

vi.mock("../../components/Modal", () => ({
  Modal: ({ children, title }: { children: ReactNode; title: string }) => (
    <div role="dialog" aria-label={title}>
      {children}
    </div>
  ),
}));

function result<T>(data: T) {
  return Promise.resolve({ data, warnings: [] });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => {
    resolve = accept;
  });
  return { promise, resolve };
}

function reportIdentity(reportId: string) {
  return (_content: string, element: Element | null) =>
    element?.tagName === "P" &&
    element.textContent?.includes(`Report ${reportId};`) === true;
}

function ReportLayoutProbe({ observe }: { observe: () => void }) {
  useLayoutEffect(() => observe(), [observe]);
  return null;
}

function stubObjectUrls() {
  const created: Blob[] = [];
  const revoked: string[] = [];
  const createDescriptor = Object.getOwnPropertyDescriptor(
    URL,
    "createObjectURL",
  );
  const revokeDescriptor = Object.getOwnPropertyDescriptor(
    URL,
    "revokeObjectURL",
  );
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    writable: true,
    value: (blob: Blob) => {
      created.push(blob);
      return `blob:report-${created.length}`;
    },
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    writable: true,
    value: (url: string) => revoked.push(url),
  });
  return {
    created,
    revoked,
    restore() {
      if (createDescriptor)
        Object.defineProperty(URL, "createObjectURL", createDescriptor);
      else Reflect.deleteProperty(URL, "createObjectURL");
      if (revokeDescriptor)
        Object.defineProperty(URL, "revokeObjectURL", revokeDescriptor);
      else Reflect.deleteProperty(URL, "revokeObjectURL");
    },
  };
}

const report: ApiOperationData<"readReport"> = {
  schema_version: 1,
  report_id: "report-1",
  target_kind: "evaluation",
  target_id: "evaluation-1",
  evaluation_ids: ["evaluation-1"],
  result_snapshot_ids: ["result-1"],
  label_snapshot_ids: ["labels-1"],
  diagnostic_snapshot_id: null,
  check_snapshot_id: null,
  comparison_id: null,
  evidence_modes: ["authored_fixture"],
  legacy: false,
  nonexportable_reason: null,
  raw: { inputs: false, requests: false, responses: false },
  created_at: "2026-10-11T00:00:00Z",
  content_hash: "a".repeat(64),
};

function runRecord(
  latestResultSnapshotId: string | null,
): ApiOperationData<"readRun"> {
  return {
    schema_version: 1,
    run_id: "run-A",
    attempt_limit: "12",
    attempts: [],
    attempts_remaining: "12",
    attempts_used: "0",
    cases: [],
    dataset_id: "dataset-A",
    decision_id: "decision-A",
    execution_active: false,
    execution_group_id: null,
    group_attempts_remaining: null,
    latest_result_snapshot_id: latestResultSnapshotId,
    mode: "fixture",
    reason: null,
    replayed: false,
    requested_model: "fixture-model",
    result_snapshot_ids: latestResultSnapshotId ? [latestResultSnapshotId] : [],
    segment_ids: [],
    segments: [],
    settings: {
      concurrency: "1",
      deadline_seconds: "120",
      max_attempts: "12",
      max_retries_per_case: "0",
      timeout_seconds: "30",
    },
    sources: {
      dataset_snapshot_id: "dataset-snapshot-A",
      decision_revision_id: "revision-A",
      development_dataset_snapshot_id: "dataset-snapshot-A",
      development_label_snapshot_id: "labels-A",
      fixture_set_id: null,
      label_snapshot_id: "labels-A",
      option_order: null,
      provider_profile_id: "fixture-provider",
      evidence_mode: "authored_fixture",
    },
    state: "complete",
  };
}

function evaluationRecord(
  evaluationId: string,
  runId: string,
  resultSnapshotId: string,
): ApiOperationData<"readEvaluation"> {
  return {
    schema_version: 1,
    evaluation_id: evaluationId,
    run_id: runId,
    result_snapshot_id: resultSnapshotId,
    label_snapshot_id: "labels-A",
    mode: "original",
    replayed: false,
    created_at: "2026-10-11T00:00:00Z",
    execution_operation_id: null,
    content_hash: "b".repeat(64),
    metrics: {},
    metrics_source: "fixture",
  };
}

function reportReceipt(
  targetKind: "run" | "evaluation",
  targetId: string,
  evaluationIds: readonly string[],
  resultSnapshotIds: readonly string[],
): ApiOperationData<"createReport"> {
  return {
    schema_version: 1,
    report_id: "report-created",
    content_hash: "c".repeat(64),
    created_at: "2026-10-11T00:00:00Z",
    target_id: targetId,
    target_kind: targetKind,
    evaluation_ids: evaluationIds,
    result_snapshot_ids: resultSnapshotIds,
    label_snapshot_ids: ["labels-A"],
    comparison_id: null,
    diagnostic_snapshot_id: null,
    check_snapshot_id: null,
    evidence_modes: ["authored_fixture"],
    legacy: false,
    nonexportable_reason: null,
    raw: { inputs: false, requests: false, responses: false },
  };
}

it("clears bytes and preview when changing the requested report format", async () => {
  const requests: Parameters<
    typeof disconnectedWorkspace.debugging.reports.download
  >[0][] = [];
  const operations = {
    ...disconnectedWorkspace.debugging.reports,
    read: async () => result(report),
    download: async (request: (typeof requests)[number]) => {
      requests.push(request);
      return {
        blob: new Blob([
          request.query.format === "json" ? '{"report":1}' : "# Report\n",
        ]),
        filename: request.query.format === "json" ? "report.json" : "report.md",
      };
    },
  };
  render(
    <ReportPage
      registrationId="registration-1"
      reportId="report-1"
      operations={operations}
    />,
  );
  const user = userEvent.setup();
  await screen.findByText(reportIdentity("report-1"));
  await user.click(
    screen.getByRole("button", { name: "Preview report bytes" }),
  );
  expect(await screen.findByText('{"report":1}')).toBeTruthy();
  expect(screen.getByRole("status").textContent).toContain("as json");

  await user.selectOptions(
    screen.getByLabelText("Download format"),
    "markdown",
  );
  expect(screen.queryByText('{"report":1}')).toBeNull();
  expect(screen.queryByRole("status")).toBeNull();
  await user.click(
    screen.getByRole("button", { name: "Preview report bytes" }),
  );
  expect(await screen.findByText("# Report")).toBeTruthy();
  await waitFor(() => expect(requests).toHaveLength(2));
  expect(requests[0]?.query.format).toBe("json");
  expect(requests[1]?.query.format).toBe("markdown");
  expect(screen.getByRole("status").textContent).toContain("as markdown");
});

it("keeps deferred report bytes inside their A-to-B-to-A rendered scope", async () => {
  type Download = Awaited<
    ReturnType<typeof disconnectedWorkspace.debugging.reports.download>
  >;
  const pending: Array<{
    reportId: string;
    request: Parameters<
      typeof disconnectedWorkspace.debugging.reports.download
    >[0];
    response: ReturnType<typeof deferred<Download>>;
  }> = [];
  const operations = {
    ...disconnectedWorkspace.debugging.reports,
    read: async (request: { reportId: string }) =>
      result({ ...report, report_id: request.reportId }),
    download: (request: (typeof pending)[number]["request"]) => {
      const response = deferred<Download>();
      pending.push({ reportId: request.reportId, request, response });
      return response.promise;
    },
  };
  const tree = render(
    <ReportPage
      registrationId="registration-1"
      reportId="report-A"
      operations={operations}
    />,
  );
  const user = userEvent.setup();
  try {
    await screen.findByText(reportIdentity("report-A"));
    await user.click(
      screen.getByRole("button", { name: "Preview report bytes" }),
    );
    await waitFor(() => expect(pending).toHaveLength(1));

    tree.rerender(
      <ReportPage
        registrationId="registration-1"
        reportId="report-B"
        operations={operations}
      />,
    );
    await screen.findByText(reportIdentity("report-B"));
    expect(
      (
        screen.getByRole("button", {
          name: "Preview report bytes",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false);
    await user.click(
      screen.getByRole("button", { name: "Preview report bytes" }),
    );
    await waitFor(() => expect(pending).toHaveLength(2));
    pending[1]?.response.resolve({
      blob: new Blob(["bytes from B"]),
      filename: "b.json",
    });
    expect(await screen.findByText("bytes from B")).toBeTruthy();

    tree.rerender(
      <ReportPage
        registrationId="registration-1"
        reportId="report-A"
        operations={operations}
      />,
    );
    await screen.findByText(reportIdentity("report-A"));
    await user.click(
      screen.getByRole("button", { name: "Preview report bytes" }),
    );
    await waitFor(() => expect(pending).toHaveLength(3));
    expect(
      screen.getByRole("button", { name: "Reading report bytes…" }),
    ).toBeTruthy();

    await act(async () => {
      pending[0]?.response.resolve({
        blob: new Blob(["stale bytes from A1"]),
        filename: "stale-a.json",
      });
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.queryByText("stale bytes from A1")).toBeNull();
    expect(
      screen.getByRole("button", { name: "Reading report bytes…" }),
    ).toBeTruthy();

    pending[2]?.response.resolve({
      blob: new Blob(["current bytes from A2"]),
      filename: "current-a.json",
    });
    expect(await screen.findByText("current bytes from A2")).toBeTruthy();
  } finally {
    tree.unmount();
  }
});

it("hides the previous report synchronously while replacement metadata is pending", async () => {
  type Read = ApiOperationData<"readReport">;
  const pendingRead = deferred<ApiResult<Read>>();
  let replacementReads = 0;
  let downloadCalls = 0;
  const operations = {
    ...disconnectedWorkspace.debugging.reports,
    read: (request: { reportId: string }) => {
      if (request.reportId === "report-A")
        return result({ ...report, report_id: "report-A" });
      replacementReads += 1;
      return pendingRead.promise;
    },
    download: async () => {
      downloadCalls += 1;
      return {
        blob: new Blob(["replacement bytes"]),
        filename: "replacement.json",
      };
    },
  };
  let layoutSnapshot:
    | {
        oldMetadataVisible: boolean;
        downloadControls: number;
        loading: boolean;
      }
    | undefined;
  const observe = () => {
    const page = document.querySelector("article.document");
    const buttons = [...(page?.querySelectorAll("button") ?? [])];
    layoutSnapshot = {
      oldMetadataVisible:
        page?.textContent?.includes("Report report-A;") ?? false,
      downloadControls: buttons.filter((button) =>
        /report bytes|^Download /.test(button.textContent?.trim() ?? ""),
      ).length,
      loading: page?.textContent?.includes("Loading report metadata…") ?? false,
    };
  };
  const tree = render(
    <>
      <ReportPage
        registrationId="registration-1"
        reportId="report-A"
        operations={operations}
      />
      <ReportLayoutProbe observe={observe} />
    </>,
  );
  try {
    await screen.findByText(reportIdentity("report-A"));
    tree.rerender(
      <>
        <ReportPage
          registrationId="registration-1"
          reportId="report-B"
          operations={operations}
        />
        <ReportLayoutProbe observe={observe} />
      </>,
    );
    expect(layoutSnapshot).toEqual({
      oldMetadataVisible: false,
      downloadControls: 0,
      loading: true,
    });
    await waitFor(() => expect(replacementReads).toBe(1));
    expect(downloadCalls).toBe(0);

    pendingRead.resolve({
      data: { ...report, report_id: "report-B" },
      warnings: [],
    });
    await screen.findByText(reportIdentity("report-B"));
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Preview report bytes" }));
    expect(downloadCalls).toBe(1);
  } finally {
    tree.unmount();
  }
});

it("rejects a same-key replacement port response admitted before passive effects", async () => {
  type Download = Awaited<
    ReturnType<typeof disconnectedWorkspace.debugging.reports.download>
  >;
  type Read = ApiOperationData<"readReport">;
  const staleDownload = deferred<Download>();
  const replacementRead = deferred<ApiResult<Read>>();
  let replacementReads = 0;
  const originalOperations = {
    ...disconnectedWorkspace.debugging.reports,
    read: async () => result(report),
    download: () => staleDownload.promise,
  };
  let replacementDownloads = 0;
  const replacementOperations = {
    ...disconnectedWorkspace.debugging.reports,
    read: () => {
      replacementReads += 1;
      return replacementRead.promise;
    },
    download: async () => {
      replacementDownloads += 1;
      return { blob: new Blob(["new port bytes"]), filename: "new-port.json" };
    },
  };
  const urls = stubObjectUrls();
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => undefined);
  let layoutSnapshot:
    | {
        oldMetadataVisible: boolean;
        downloadControls: number;
        loading: boolean;
      }
    | undefined;
  const observe = () => {
    const page = document.querySelector("article.document");
    const buttons = [...(page?.querySelectorAll("button") ?? [])];
    layoutSnapshot = {
      oldMetadataVisible:
        page?.textContent?.includes("Report report-1;") ?? false,
      downloadControls: buttons.filter((button) =>
        /report bytes|^Download /.test(button.textContent?.trim() ?? ""),
      ).length,
      loading: page?.textContent?.includes("Loading report metadata…") ?? false,
    };
    staleDownload.resolve({
      blob: new Blob(["stale same-key bytes"]),
      filename: "stale.json",
    });
  };
  const tree = render(
    <>
      <ReportPage
        registrationId="registration-1"
        reportId="report-1"
        operations={originalOperations}
      />
      <ReportLayoutProbe observe={() => undefined} />
    </>,
  );
  const user = userEvent.setup();
  try {
    await screen.findByText(reportIdentity("report-1"));
    await user.click(screen.getByRole("button", { name: "Download JSON" }));
    tree.rerender(
      <>
        <ReportPage
          registrationId="registration-1"
          reportId="report-1"
          operations={replacementOperations}
        />
        <ReportLayoutProbe observe={observe} />
      </>,
    );
    expect(layoutSnapshot).toEqual({
      oldMetadataVisible: false,
      downloadControls: 0,
      loading: true,
    });
    await waitFor(() => expect(replacementReads).toBe(1));
    expect(replacementDownloads).toBe(0);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(urls.created).toEqual([]);
    expect(click).not.toHaveBeenCalled();

    replacementRead.resolve({ data: report, warnings: [] });
    await screen.findByText(reportIdentity("report-1"));
    await user.click(
      screen.getByRole("button", { name: "Preview report bytes" }),
    );
    await screen.findByText("new port bytes");
    expect(replacementDownloads).toBe(1);
    expect(urls.created).toEqual([]);
    expect(click).not.toHaveBeenCalled();
  } finally {
    tree.unmount();
    click.mockRestore();
    urls.restore();
  }
});

it("ignores a pending saved download after unmount without creating a URL or clicking", async () => {
  type Download = Awaited<
    ReturnType<typeof disconnectedWorkspace.debugging.reports.download>
  >;
  const response = deferred<Download>();
  const operations = {
    ...disconnectedWorkspace.debugging.reports,
    read: async () => result(report),
    download: () => response.promise,
  };
  const urls = stubObjectUrls();
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => undefined);
  const tree = render(
    <ReportPage
      registrationId="registration-1"
      reportId="report-1"
      operations={operations}
    />,
  );
  const user = userEvent.setup();
  try {
    await screen.findByText(reportIdentity("report-1"));
    await user.click(screen.getByRole("button", { name: "Download JSON" }));
    tree.unmount();
    await act(async () => {
      response.resolve({
        blob: new Blob(["late saved bytes"]),
        filename: "late.json",
      });
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(urls.created).toEqual([]);
    expect(click).not.toHaveBeenCalled();
  } finally {
    tree.unmount();
    click.mockRestore();
    urls.restore();
  }
});

it("binds saved report URLs to their exact bytes and revokes them on format, scope, timer, and unmount", async () => {
  type Download = Awaited<
    ReturnType<typeof disconnectedWorkspace.debugging.reports.download>
  >;
  const pending: Array<ReturnType<typeof deferred<Download>>> = [];
  const operations = {
    ...disconnectedWorkspace.debugging.reports,
    read: async (request: { reportId: string }) =>
      result({ ...report, report_id: request.reportId }),
    download: () => {
      const response = deferred<Download>();
      pending.push(response);
      return response.promise;
    },
  };
  const urls = stubObjectUrls();
  let clickedAnchor: HTMLAnchorElement | undefined;
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(function (this: HTMLAnchorElement) {
      clickedAnchor = this;
    });
  const tree = render(
    <ReportPage
      registrationId="registration-1"
      reportId="report-1"
      operations={operations}
    />,
  );
  try {
    await screen.findByText(reportIdentity("report-1"));
    vi.useFakeTimers();

    fireEvent.click(screen.getByRole("button", { name: "Download JSON" }));
    expect(pending).toHaveLength(1);
    const firstBlob = new Blob(["first report bytes"]);
    await act(async () => {
      pending[0]?.resolve({ blob: firstBlob, filename: "safe-report.json" });
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByText("Download started: safe-report.json")).toBeTruthy();
    expect(urls.created).toEqual([firstBlob]);
    expect(clickedAnchor?.href).toBe("blob:report-1");
    expect(clickedAnchor?.download).toBe("safe-report.json");
    expect(click).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByLabelText("Download format"), {
      target: { value: "markdown" },
    });
    expect(urls.revoked).toEqual(["blob:report-1"]);
    await vi.runOnlyPendingTimersAsync();
    expect(urls.revoked).toEqual(["blob:report-1"]);

    fireEvent.click(screen.getByRole("button", { name: "Download Markdown" }));
    expect(pending).toHaveLength(2);
    const secondBlob = new Blob(["second report bytes"]);
    await act(async () => {
      pending[1]?.resolve({ blob: secondBlob, filename: "second.md" });
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(urls.created).toEqual([firstBlob, secondBlob]);
    expect(clickedAnchor?.download).toBe("second.md");
    tree.rerender(
      <ReportPage
        registrationId="registration-1"
        reportId="report-2"
        operations={operations}
      />,
    );
    expect(urls.revoked).toEqual(["blob:report-1", "blob:report-2"]);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByText(reportIdentity("report-2"))).toBeTruthy();
    await vi.runOnlyPendingTimersAsync();
    expect(urls.revoked).toEqual(["blob:report-1", "blob:report-2"]);

    fireEvent.click(screen.getByRole("button", { name: "Download Markdown" }));
    expect(pending).toHaveLength(3);
    const thirdBlob = new Blob(["third report bytes"]);
    await act(async () => {
      pending[2]?.resolve({ blob: thirdBlob, filename: "third.md" });
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(urls.created).toEqual([firstBlob, secondBlob, thirdBlob]);
    expect(clickedAnchor?.download).toBe("third.md");
    tree.unmount();
    expect(urls.revoked).toEqual([
      "blob:report-1",
      "blob:report-2",
      "blob:report-3",
    ]);
  } finally {
    tree.unmount();
    vi.useRealTimers();
    click.mockRestore();
    urls.restore();
  }
});

it("keeps a new report-target verification active when an older target read settles", async () => {
  window.history.replaceState(null, "", "#/p/registration-1/reports");
  const navigation = new WorkspaceNavigation(window);
  type Evaluation = ApiOperationData<"readEvaluation">;
  type Comparison = ApiOperationData<"readComparison">;
  const evaluationRead = deferred<ApiResult<Evaluation>>();
  const comparisonRead = deferred<ApiResult<Comparison>>();
  const execution = {
    ...disconnectedWorkspace.execution,
    inspection: {
      ...disconnectedWorkspace.execution.inspection,
      readEvaluation: () => evaluationRead.promise,
    },
  };
  const debugging = {
    ...disconnectedWorkspace.debugging,
    comparisons: {
      ...disconnectedWorkspace.debugging.comparisons,
      read: () => comparisonRead.promise,
    },
  };
  const tree = render(
    <ReportSheet
      registrationId="registration-1"
      debugging={debugging}
      execution={execution}
      navigation={navigation}
      onClose={() => undefined}
      onCreated={() => undefined}
    />,
  );
  const user = userEvent.setup();
  try {
    await user.selectOptions(
      screen.getByLabelText("Target kind"),
      "evaluation",
    );
    await user.type(screen.getByLabelText("Target ID"), "evaluation-A");
    await user.click(
      screen.getByRole("button", { name: "Verify saved target" }),
    );
    expect(
      screen.getByRole("button", { name: "Verifying target…" }),
    ).toBeTruthy();

    await user.selectOptions(
      screen.getByLabelText("Target kind"),
      "comparison",
    );
    await user.clear(screen.getByLabelText("Target ID"));
    await user.type(screen.getByLabelText("Target ID"), "comparison-B");
    const verify = screen.getByRole("button", { name: "Verify saved target" });
    expect((verify as HTMLButtonElement).disabled).toBe(false);
    await user.click(verify);
    expect(
      screen.getByRole("button", { name: "Verifying target…" }),
    ).toBeTruthy();

    evaluationRead.resolve({
      data: {
        schema_version: 1,
        evaluation_id: "evaluation-A",
        run_id: "run-A",
        result_snapshot_id: "result-A",
        label_snapshot_id: "labels-A",
        mode: "original",
        replayed: false,
        created_at: "2026-10-11T00:00:00Z",
        execution_operation_id: null,
        content_hash: "evaluation-hash",
        metrics: {},
        metrics_source: "fixture",
      },
      warnings: [],
    });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Verifying target…" }),
      ).toBeTruthy(),
    );
    expect(
      (
        screen.getByRole("button", {
          name: "Verifying target…",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(screen.queryByLabelText("Verified report target")).toBeNull();

    comparisonRead.resolve({
      data: {
        schema_version: 1,
        comparison_id: "comparison-B",
        content_hash: "comparison-hash",
        created_at: "2026-10-11T00:00:00Z",
        left_evaluation_id: "left-eval",
        left_result_snapshot_id: "left-result",
        outcomes: {},
        replayed: false,
        right_evaluation_id: "right-eval",
        right_result_snapshot_id: "right-result",
      },
      warnings: [],
    });
    expect(await screen.findByLabelText("Verified report target")).toBeTruthy();
    expect(
      screen.getByLabelText("Verified report target").textContent,
    ).toContain("Comparison comparison-B");
    expect(
      screen.getByRole("button", { name: "Verify saved target" }),
    ).toBeTruthy();
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});

it("pins an explicit historical run evaluation and its result in the report body", async () => {
  const navigation = new WorkspaceNavigation(window);
  const submitted: ApiOperationBody<"createReport">[] = [];
  const execution = {
    ...disconnectedWorkspace.execution,
    runs: {
      ...disconnectedWorkspace.execution.runs,
      read: async () => result(runRecord(null)),
    },
    inspection: {
      ...disconnectedWorkspace.execution.inspection,
      readEvaluation: async ({ evaluationId }: { evaluationId: string }) =>
        result(evaluationRecord(evaluationId, "run-A", "historical-result")),
    },
  };
  const debugging = {
    ...disconnectedWorkspace.debugging,
    reports: {
      ...disconnectedWorkspace.debugging.reports,
      create: async ({ body }: { body: ApiOperationBody<"createReport"> }) => {
        submitted.push(body);
        return result(
          reportReceipt(
            "run",
            "run-A",
            ["evaluation-A"],
            ["historical-result"],
          ),
        );
      },
    },
  };
  const tree = render(
    <ReportSheet
      registrationId="registration-1"
      debugging={debugging}
      execution={execution}
      navigation={navigation}
      onClose={() => undefined}
      onCreated={() => undefined}
    />,
  );
  const user = userEvent.setup();
  try {
    await user.type(screen.getByLabelText("Target ID"), "run-A");
    await user.type(
      screen.getByLabelText("Saved evaluation ID (optional)"),
      "evaluation-A",
    );
    await user.click(
      screen.getByRole("button", { name: "Verify saved target" }),
    );
    const verified = await screen.findByLabelText("Verified report target");
    expect(verified.textContent).toContain("Evaluation evaluation-A");
    expect(verified.textContent).toContain("Labels labels-A");
    expect(verified.textContent).toContain("Result historical-result");

    await user.click(screen.getByRole("button", { name: "Create report" }));
    const receiptStatus = await screen.findByRole("status");
    expect(receiptStatus.textContent).toContain(
      "Report report-created is saved.",
    );
    expect(submitted).toHaveLength(1);
    const body = submitted[0];
    expect(body).toBeDefined();
    expect(Object.keys(body ?? {}).sort()).toEqual(
      [
        "evaluation_id",
        "operation_id",
        "raw",
        "result_snapshot_id",
        "schema_version",
        "target_id",
        "target_kind",
      ].sort(),
    );
    expect(body?.evaluation_id).toBe("evaluation-A");
    expect(body?.result_snapshot_id).toBe("historical-result");
    expect(body?.target_kind).toBe("run");
    expect(body?.target_id).toBe("run-A");
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});

it("rejects a saved evaluation from another run before creating a report", async () => {
  const navigation = new WorkspaceNavigation(window);
  let createCalls = 0;
  const execution = {
    ...disconnectedWorkspace.execution,
    runs: {
      ...disconnectedWorkspace.execution.runs,
      read: async () => result(runRecord("latest-result")),
    },
    inspection: {
      ...disconnectedWorkspace.execution.inspection,
      readEvaluation: async ({ evaluationId }: { evaluationId: string }) =>
        result(evaluationRecord(evaluationId, "different-run", "other-result")),
    },
  };
  const debugging = {
    ...disconnectedWorkspace.debugging,
    reports: {
      ...disconnectedWorkspace.debugging.reports,
      create: async () => {
        createCalls += 1;
        return result(
          reportReceipt("run", "run-A", ["evaluation-A"], ["other-result"]),
        );
      },
    },
  };
  const tree = render(
    <ReportSheet
      registrationId="registration-1"
      debugging={debugging}
      execution={execution}
      navigation={navigation}
      onClose={() => undefined}
      onCreated={() => undefined}
    />,
  );
  const user = userEvent.setup();
  try {
    await user.type(screen.getByLabelText("Target ID"), "run-A");
    await user.type(
      screen.getByLabelText("Saved evaluation ID (optional)"),
      "evaluation-A",
    );
    await user.click(
      screen.getByRole("button", { name: "Verify saved target" }),
    );
    expect(
      await screen.findByText(
        "The saved evaluation does not belong to this run.",
      ),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Verified report target")).toBeNull();
    expect(
      (
        screen.getByRole("button", {
          name: "Create report",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(createCalls).toBe(0);
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});

it("does not republish run verification after its evaluation selector changes A-to-B-to-A", async () => {
  const navigation = new WorkspaceNavigation(window);
  const evaluationRead =
    deferred<ApiResult<ApiOperationData<"readEvaluation">>>();
  const execution = {
    ...disconnectedWorkspace.execution,
    runs: {
      ...disconnectedWorkspace.execution.runs,
      read: async () => result(runRecord("latest-result")),
    },
    inspection: {
      ...disconnectedWorkspace.execution.inspection,
      readEvaluation: () => evaluationRead.promise,
    },
  };
  const tree = render(
    <ReportSheet
      registrationId="registration-1"
      debugging={disconnectedWorkspace.debugging}
      execution={execution}
      navigation={navigation}
      onClose={() => undefined}
      onCreated={() => undefined}
    />,
  );
  const user = userEvent.setup();
  try {
    await user.type(screen.getByLabelText("Target ID"), "run-A");
    const evaluationInput = screen.getByLabelText(
      "Saved evaluation ID (optional)",
    );
    await user.type(evaluationInput, "evaluation-A");
    await user.click(
      screen.getByRole("button", { name: "Verify saved target" }),
    );
    expect(
      screen.getByRole("button", { name: "Verifying target…" }),
    ).toBeTruthy();
    await user.clear(evaluationInput);
    await user.type(evaluationInput, "evaluation-B");
    await user.clear(evaluationInput);
    await user.type(evaluationInput, "evaluation-A");

    await act(async () => {
      evaluationRead.resolve({
        data: evaluationRecord("evaluation-A", "run-A", "historical-result"),
        warnings: [],
      });
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.queryByLabelText("Verified report target")).toBeNull();
    expect(
      (
        screen.getByRole("button", {
          name: "Verify saved target",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false);
    expect(
      (
        screen.getByRole("button", {
          name: "Create report",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});

it("omits evaluation selectors for saved-evaluation reports but checks their receipt context", async () => {
  const navigation = new WorkspaceNavigation(window);
  const submitted: ApiOperationBody<"createReport">[] = [];
  const execution = {
    ...disconnectedWorkspace.execution,
    inspection: {
      ...disconnectedWorkspace.execution.inspection,
      readEvaluation: async ({ evaluationId }: { evaluationId: string }) =>
        result(evaluationRecord(evaluationId, "run-A", "historical-result")),
    },
  };
  const debugging = {
    ...disconnectedWorkspace.debugging,
    reports: {
      ...disconnectedWorkspace.debugging.reports,
      create: async ({ body }: { body: ApiOperationBody<"createReport"> }) => {
        submitted.push(body);
        return result(
          reportReceipt(
            "evaluation",
            "evaluation-A",
            ["evaluation-A"],
            ["historical-result"],
          ),
        );
      },
    },
  };
  const tree = render(
    <ReportSheet
      registrationId="registration-1"
      debugging={debugging}
      execution={execution}
      navigation={navigation}
      onClose={() => undefined}
      onCreated={() => undefined}
    />,
  );
  const user = userEvent.setup();
  try {
    await user.selectOptions(
      screen.getByLabelText("Target kind"),
      "evaluation",
    );
    await user.type(screen.getByLabelText("Target ID"), "evaluation-A");
    await user.click(
      screen.getByRole("button", { name: "Verify saved target" }),
    );
    expect(await screen.findByLabelText("Verified report target")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Create report" }));
    const receiptStatus = await screen.findByRole("status");
    expect(receiptStatus.textContent).toContain(
      "Report report-created is saved.",
    );
    expect(submitted).toHaveLength(1);
    const body = submitted[0];
    expect(body).toBeDefined();
    expect(Object.keys(body ?? {}).sort()).toEqual(
      [
        "operation_id",
        "raw",
        "schema_version",
        "target_id",
        "target_kind",
      ].sort(),
    );
    expect(body?.target_kind).toBe("evaluation");
    expect(body?.evaluation_id).toBeUndefined();
    expect(body?.result_snapshot_id).toBeUndefined();
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});
