import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  await screen.findByText(/Report report-1/);
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
