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
import type { ApiOperationData, ApiResult } from "../../api/client";
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
    await waitFor(() => expect(pending).toHaveLength(1));
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
    await waitFor(() => expect(pending).toHaveLength(2));
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
    await screen.findByText(reportIdentity("report-2"));
    await vi.runOnlyPendingTimersAsync();
    expect(urls.revoked).toEqual(["blob:report-1", "blob:report-2"]);

    fireEvent.click(screen.getByRole("button", { name: "Download Markdown" }));
    await waitFor(() => expect(pending).toHaveLength(3));
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
