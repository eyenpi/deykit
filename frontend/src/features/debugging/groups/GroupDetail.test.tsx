import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { ApiOperationData } from "../../../api/client";
import { disconnectedWorkspace } from "../../../workspace/gateway";
import type {
  ProjectOverview,
  WorkspaceGateway,
} from "../../../workspace/gateway";
import { WorkspaceNavigation } from "../../../workspace/navigation";
import { GroupDetail } from "./GroupDetail";
import { presentDiagnosticSummary } from "./summary";

function response<T>(data: T) {
  return Promise.resolve({ data, warnings: [] });
}

const project: ProjectOverview = {
  id: "registration-1",
  name: "Fixture project",
  path: "/tmp/fixture-project",
  decisions: [],
  datasets: [],
  warnings: [],
};

const progress = {
  schema_version: 1,
  group_id: "group-1",
  kind: "choice_order",
  seed: "9007199254740993",
  algorithm: "seeded-v1",
  independent_case_count: "1",
  initial_requests: "2",
  attempt_limit: "4",
  attempts_used: "1",
  attempts_remaining: "3",
  replayed: false,
  snapshot_id: "snapshot-2",
  members: [
    {
      schema_version: 1,
      run_id: "run-1",
      state: "running",
      attempts_used: "1",
      attempt_limit: "4",
      attempts_remaining: "3",
      cases: [],
      attempts: [],
      dataset_id: "dataset-1",
      decision_id: "decision-1",
      execution_active: true,
      execution_group_id: "group-1",
      group_attempts_remaining: "3",
      latest_result_snapshot_id: "result-1",
      mode: "fixture",
      reason: null,
      replayed: false,
      requested_model: "fixture-model",
      result_snapshot_ids: ["result-1"],
      segment_ids: ["segment-1"],
      segments: [],
      settings: {},
      sources: {},
    },
  ],
} as unknown as ApiOperationData<"readChoiceOrder">["group"];

const member = {
  run_id: "run-1",
  result_snapshot_id: "result-1",
  dataset_id: "dataset-1",
  dataset_snapshot_id: "dataset-snapshot-1",
  dataset_content_hash: "a".repeat(64),
  decision_id: "decision-1",
  decision_revision_id: "revision-1",
  decision_definition_hash: "b".repeat(64),
  label_snapshot_id: "label-snapshot-1",
  label_content_hash: "c".repeat(64),
  result_content_hash: "d".repeat(64),
  through_event_sequence: "17",
};

function snapshot(
  id: string,
  sequence: string,
): ApiOperationData<"listChoiceOrderSnapshots">[number] {
  return {
    id,
    sequence,
    group_id: "group-1",
    segment_id: `segment-${sequence}`,
    content_hash: sequence === "1" ? "e".repeat(64) : "f".repeat(64),
    created_at: `2026-10-11T00:00:0${sequence}Z`,
    results: [{ run_id: "run-1", result_snapshot_id: `result-${sequence}` }],
  };
}

function diagnosticSnapshot(
  id: string,
  sequence: string,
): ApiOperationData<"readChoiceOrderSnapshot"> {
  return {
    snapshot: snapshot(id, sequence),
    members: [member],
    summary: {
      independent_case_count: "1",
      order_count: "2",
      expanded_result_count: "2",
      fully_observed_case_count: "1",
      disagreement: {
        numerator: "0",
        denominator: "1",
        value: "0.000000",
        reason: null,
      },
      cases: [
        {
          case_id: "case-1",
          option_ids: ["option-a", "option-b"],
          statuses: ["valid", "valid"],
          observed_disagreement: false,
          fully_observed: true,
        },
      ],
      interpretation: "observed_request_order_sensitivity",
    },
  };
}

it("rejects malformed diagnostic disagreement ratios above one", () => {
  const summary = {
    independent_case_count: "1",
    order_count: "2",
    expanded_result_count: "2",
    fully_observed_case_count: "1",
    disagreement: {
      numerator: "2",
      denominator: "1",
      value: "1.000001",
      reason: null,
    },
    cases: [],
    interpretation: "observed_request_order_sensitivity",
  };
  expect(presentDiagnosticSummary(summary)).toBeUndefined();
  expect(
    presentDiagnosticSummary({
      ...summary,
      disagreement: { ...summary.disagreement, value: "1.000000" },
    })?.disagreement.value,
  ).toBe("1.000000");
});

it("keeps a selected historical snapshot pinned while progress and the latest list advance", async () => {
  const firstList = [snapshot("snapshot-1", "1"), snapshot("snapshot-2", "2")];
  const nextList = [
    ...firstList,
    {
      ...snapshot("snapshot-3", "3"),
      results: [{ run_id: "run-1", result_snapshot_id: "result-3" }],
    },
  ];
  const listSnapshots = vi
    .fn()
    .mockResolvedValueOnce({ data: firstList, warnings: [] })
    .mockResolvedValue({ data: nextList, warnings: [] });
  const readSnapshot = vi.fn(async ({ snapshotId }: { snapshotId: string }) =>
    response(
      diagnosticSnapshot(
        snapshotId,
        snapshotId === "snapshot-1"
          ? "1"
          : snapshotId === "snapshot-2"
            ? "2"
            : "3",
      ),
    ),
  );
  const read = vi.fn(async () =>
    response({
      group: progress,
      exit_code: 0,
      summary: null,
    } as ApiOperationData<"readChoiceOrder">),
  );
  const cancel = vi.fn();
  const gateway = {
    ...disconnectedWorkspace,
    debugging: {
      ...disconnectedWorkspace.debugging,
      diagnostics: {
        ...disconnectedWorkspace.debugging.diagnostics,
        read,
        listSnapshots,
        readSnapshot,
        cancel,
      },
    },
  } as unknown as WorkspaceGateway;
  const navigation = new WorkspaceNavigation(window);
  const navigate = vi.spyOn(navigation, "navigate").mockResolvedValue(true);
  const pollingCallbacks: Array<() => void> = [];
  const pollingDelays: number[] = [];
  const nativeSetInterval = window.setInterval;
  const intervalSpy = vi.spyOn(window, "setInterval").mockImplementation(((
    handler: TimerHandler,
    delay?: number,
  ) => {
    if (delay === 2500) {
      pollingDelays.push(delay);
      if (typeof handler === "function")
        pollingCallbacks.push(handler as () => void);
      return -1;
    }
    return nativeSetInterval.call(window, handler, delay);
  }) as typeof window.setInterval);
  const view = render(
    <GroupDetail
      project={project}
      gateway={gateway}
      navigation={navigation}
      kind="diagnostic"
      groupId="group-1"
    />,
  );

  await screen.findByText("Observed request-order sensitivity");
  expect(screen.getByText("9007199254740993")).toBeTruthy();
  expect(screen.getByText("17")).toBeTruthy();
  expect(read).toHaveBeenCalledTimes(1);
  expect(cancel).not.toHaveBeenCalled();

  fireEvent.change(screen.getByLabelText("Selected snapshot"), {
    target: { value: "snapshot-1" },
  });
  await screen.findByText("Selected immutable snapshot");
  expect(screen.getByLabelText("Selected snapshot")).toHaveProperty(
    "value",
    "snapshot-1",
  );
  expect(screen.getAllByText("result-1").length).toBeGreaterThan(1);

  expect(pollingDelays).toContain(2500);
  expect(pollingCallbacks).toHaveLength(1);
  await act(async () => {
    pollingCallbacks[0]?.();
    await Promise.resolve();
  });
  expect(listSnapshots).toHaveBeenCalledTimes(2);
  expect(screen.getByLabelText("Selected snapshot")).toHaveProperty(
    "value",
    "snapshot-1",
  );
  expect(screen.getAllByText("result-1").length).toBeGreaterThan(1);
  expect(screen.queryByText("result-3")).toBeNull();

  fireEvent.click(screen.getAllByRole("button", { name: "run-1" })[0]);
  await waitFor(() =>
    expect(navigate).toHaveBeenCalledWith({
      kind: "run",
      registrationId: "registration-1",
      runId: "run-1",
      returnGroup: { kind: "diagnostic", groupId: "group-1" },
    }),
  );

  view.unmount();
  intervalSpy.mockRestore();
  navigation.dispose();
});

it("retries an unknown cancellation with its original operation id", async () => {
  const read = vi.fn(async () =>
    response({
      group: progress,
      exit_code: 0,
      summary: null,
    } as ApiOperationData<"readChoiceOrder">),
  );
  const listSnapshots = vi.fn(async () =>
    response([snapshot("snapshot-1", "1")]),
  );
  const calls: unknown[] = [];
  let attempt = 0;
  const cancel = vi.fn(async (request: unknown) => {
    calls.push(request);
    attempt += 1;
    if (attempt === 1) throw new Error("connection closed after dispatch");
    return response(progress);
  });
  const gateway = {
    ...disconnectedWorkspace,
    debugging: {
      ...disconnectedWorkspace.debugging,
      diagnostics: {
        ...disconnectedWorkspace.debugging.diagnostics,
        read,
        listSnapshots,
        cancel,
      },
    },
  } as unknown as WorkspaceGateway;
  const navigation = new WorkspaceNavigation(window);
  render(
    <GroupDetail
      project={project}
      gateway={gateway}
      navigation={navigation}
      kind="diagnostic"
      groupId="group-1"
    />,
  );

  await screen.findByText("Current progress");
  const cancelButton = screen.getByRole("button", { name: "Cancel group" });
  fireEvent.click(cancelButton);
  fireEvent.click(cancelButton);
  await screen.findByText(/connection closed after dispatch/);
  fireEvent.click(
    screen.getByRole("button", { name: "Retry original cancellation" }),
  );
  await screen.findByText("Cancellation receipt received.");
  expect(cancel).toHaveBeenCalledTimes(2);
  expect(calls[0]).toEqual(calls[1]);
  navigation.dispose();
});

it("replays an unknown diagnostic cancellation through its original port after a check-scope change", async () => {
  const diagnosticCalls: unknown[] = [];
  let attempts = 0;
  const diagnosticCancel = vi.fn(async (request: unknown) => {
    diagnosticCalls.push(request);
    attempts += 1;
    if (attempts === 1) throw new Error("connection closed after dispatch");
    return response(progress);
  });
  const checkCancel = vi.fn(async () =>
    response({
      schema_version: 1,
      kind: "regression_check",
      group_id: "group-2",
      operation_id: "unexpected",
      member_run_ids: [],
      mode: "fixture",
      replayed: true,
    } as ApiOperationData<"cancelCheck">),
  );
  const readDiagnostic = vi.fn(async ({ groupId }: { groupId: string }) =>
    response({
      group: { ...progress, group_id: groupId },
      exit_code: 0,
      summary: null,
    } as ApiOperationData<"readChoiceOrder">),
  );
  const readDiagnosticSnapshot = vi.fn(
    async ({ snapshotId }: { snapshotId: string }) =>
      response(diagnosticSnapshot(snapshotId, "1")),
  );
  const readCheck = vi.fn(async () =>
    response({
      group: { ...progress, group_id: "group-2", kind: "regression_check" },
      exit_code: 0,
      summary: null,
    } as unknown as ApiOperationData<"readCheck">),
  );
  const listDiagnosticSnapshots = vi.fn(async () =>
    response([snapshot("snapshot-1", "1")]),
  );
  const listCheckSnapshots = vi.fn(async () =>
    response([] as ApiOperationData<"listCheckSnapshots">),
  );
  const diagnosticGateway = {
    ...disconnectedWorkspace,
    debugging: {
      ...disconnectedWorkspace.debugging,
      diagnostics: {
        ...disconnectedWorkspace.debugging.diagnostics,
        read: readDiagnostic,
        listSnapshots: listDiagnosticSnapshots,
        readSnapshot: readDiagnosticSnapshot,
        cancel: diagnosticCancel,
      },
    },
  } as unknown as WorkspaceGateway;
  const checkGateway = {
    ...disconnectedWorkspace,
    debugging: {
      ...disconnectedWorkspace.debugging,
      checks: {
        ...disconnectedWorkspace.debugging.checks,
        read: readCheck,
        listSnapshots: listCheckSnapshots,
        cancel: checkCancel,
      },
    },
  } as unknown as WorkspaceGateway;
  const navigation = new WorkspaceNavigation(window);
  const onReport = vi.fn();
  const view = render(
    <GroupDetail
      project={project}
      gateway={diagnosticGateway}
      navigation={navigation}
      kind="diagnostic"
      groupId="group-1"
      onReport={onReport}
    />,
  );

  await screen.findByText("Current progress");
  await screen.findByRole("button", {
    name: "Create report from this snapshot",
  });
  fireEvent.click(screen.getByRole("button", { name: "Cancel group" }));
  await screen.findByText(/connection closed after dispatch/);
  expect(diagnosticCancel).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "run-1" })).toHaveProperty(
    "disabled",
    true,
  );
  expect(
    screen.getByRole("button", { name: "Create report from this snapshot" }),
  ).toHaveProperty("disabled", true);
  fireEvent.click(
    screen.getByRole("button", { name: "Create report from this snapshot" }),
  );
  expect(onReport).not.toHaveBeenCalled();
  const blockedNavigation = navigation.navigate({
    kind: "run",
    registrationId: "registration-1",
    runId: "guard-unknown",
  });
  await screen.findByText(
    "A group request is still settling. Retry its original request before leaving.",
  );
  expect(screen.getByRole("button", { name: "Save and leave" })).toHaveProperty(
    "disabled",
    true,
  );
  expect(
    screen.getByRole("button", { name: "Discard changes" }),
  ).toHaveProperty("disabled", true);
  const unload = new Event("beforeunload", {
    cancelable: true,
  }) as BeforeUnloadEvent;
  window.dispatchEvent(unload);
  expect(unload.defaultPrevented).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Keep editing" }));
  await expect(blockedNavigation).resolves.toBe(false);

  view.rerender(
    <GroupDetail
      project={project}
      gateway={checkGateway}
      navigation={navigation}
      kind="check"
      groupId="group-2"
    />,
  );
  await screen.findByText("Check progress");
  fireEvent.click(
    screen.getByRole("button", { name: "Retry original cancellation" }),
  );
  await waitFor(() => expect(diagnosticCancel).toHaveBeenCalledTimes(2));
  expect(checkCancel).not.toHaveBeenCalled();
  expect(diagnosticCalls[1]).toEqual(diagnosticCalls[0]);
  expect(screen.queryByText("Cancellation receipt received.")).toBeNull();
  await expect(
    navigation.navigate({
      kind: "run",
      registrationId: "registration-1",
      runId: "guard-after-receipt",
    }),
  ).resolves.toBe(true);

  view.rerender(
    <GroupDetail
      project={project}
      gateway={diagnosticGateway}
      navigation={navigation}
      kind="diagnostic"
      groupId="group-1"
    />,
  );
  await waitFor(() => expect(listDiagnosticSnapshots).toHaveBeenCalledTimes(2));
  expect(screen.queryByText("Cancellation receipt received.")).toBeNull();
  navigation.dispose();
});

it("previews resume without dispatch, then retries an unknown resume with the same body", async () => {
  let readAttempt = 0;
  const read = vi.fn(async () => {
    readAttempt += 1;
    if (readAttempt > 1)
      throw new Error("progress read unavailable after receipt");
    return response({
      group: progress,
      exit_code: 0,
      summary: null,
    } as ApiOperationData<"readChoiceOrder">);
  });
  const listSnapshots = vi.fn(async () =>
    response([snapshot("snapshot-1", "1")]),
  );
  const previewResume = vi.fn(async () =>
    response({
      schema_version: 1,
      dry_run: true,
      group: progress,
      proposed_attempt_limit: "8",
      retry_unknown: false,
      segment_ids: ["segment-2"],
      members: [{ run_id: "run-1", planned_case_ids: ["case-1"] }],
    } as ApiOperationData<"previewChoiceOrderResume">),
  );
  const resumeCalls: unknown[] = [];
  let attempt = 0;
  const resume = vi.fn(async (request: unknown) => {
    resumeCalls.push(request);
    attempt += 1;
    if (attempt === 1) throw new Error("connection closed after dispatch");
    return response({
      schema_version: 1,
      kind: "choice_order",
      group_id: "group-1",
      operation_id: "operation-1",
      member_run_ids: ["run-1"],
      mode: "fixture",
      replayed: true,
    } as ApiOperationData<"resumeChoiceOrder">);
  });
  const gateway = {
    ...disconnectedWorkspace,
    debugging: {
      ...disconnectedWorkspace.debugging,
      diagnostics: {
        ...disconnectedWorkspace.debugging.diagnostics,
        read,
        listSnapshots,
        previewResume,
        resume,
      },
    },
  } as unknown as WorkspaceGateway;
  const navigation = new WorkspaceNavigation(window);
  render(
    <GroupDetail
      project={project}
      gateway={gateway}
      navigation={navigation}
      kind="diagnostic"
      groupId="group-1"
    />,
  );

  await screen.findByText("Current progress");
  fireEvent.click(screen.getByRole("button", { name: "Review resume" }));
  await screen.findByText(/Reviewed resume for 1 members/);
  expect(screen.getByLabelText("Selected snapshot")).toHaveProperty(
    "disabled",
    true,
  );
  expect(
    screen.getByRole("checkbox", {
      name: "Retry members with unknown outcomes",
    }),
  ).toHaveProperty("disabled", true);
  const stagedNavigation = navigation.navigate({
    kind: "run",
    registrationId: "registration-1",
    runId: "staged-outside",
  });
  await screen.findByText(
    "A reviewed resume is staged. Discard it or keep editing before leaving.",
  );
  expect(
    screen.getByRole("button", { name: "Discard changes" }),
  ).toHaveProperty("disabled", false);
  fireEvent.click(screen.getByRole("button", { name: "Keep editing" }));
  await expect(stagedNavigation).resolves.toBe(false);
  expect(previewResume).toHaveBeenCalledTimes(1);
  expect(resume).not.toHaveBeenCalled();

  const resumeButton = screen.getByRole("button", {
    name: "Resume reviewed group",
  });
  fireEvent.click(resumeButton);
  fireEvent.click(resumeButton);
  await screen.findByText(/connection closed after dispatch/);
  expect(resume).toHaveBeenCalledTimes(1);
  fireEvent.click(
    screen.getByRole("button", { name: "Retry original resume request" }),
  );
  await screen.findByText(/Resume accepted:/);
  await screen.findByText(/progress read unavailable after receipt/);
  expect(resume).toHaveBeenCalledTimes(2);
  expect(resumeCalls[1]).toEqual(resumeCalls[0]);
  navigation.dispose();
});

it("does not publish an old cancellation receipt into a later A-to-B-to-A group scope", async () => {
  type CancelResponse = Awaited<
    ReturnType<WorkspaceGateway["debugging"]["diagnostics"]["cancel"]>
  >;
  let resolveCancel: ((value: CancelResponse) => void) | undefined;
  const cancel = vi.fn(
    () =>
      new Promise<CancelResponse>((resolve) => {
        resolveCancel = resolve;
      }),
  );
  const read = vi.fn(async ({ groupId }: { groupId: string }) =>
    response({
      group: { ...progress, group_id: groupId },
      exit_code: 0,
      summary: null,
    } as ApiOperationData<"readChoiceOrder">),
  );
  const listSnapshots = vi.fn(async () =>
    response([] as ApiOperationData<"listChoiceOrderSnapshots">),
  );
  const gateway = {
    ...disconnectedWorkspace,
    debugging: {
      ...disconnectedWorkspace.debugging,
      diagnostics: {
        ...disconnectedWorkspace.debugging.diagnostics,
        read,
        listSnapshots,
        cancel,
      },
    },
  } as unknown as WorkspaceGateway;
  const navigation = new WorkspaceNavigation(window);
  const props = { project, gateway, navigation, kind: "diagnostic" as const };
  const view = render(<GroupDetail {...props} groupId="group-1" />);
  await screen.findByText("Current progress");
  fireEvent.click(screen.getByRole("button", { name: "Cancel group" }));
  expect(cancel).toHaveBeenCalledTimes(1);

  view.rerender(<GroupDetail {...props} groupId="group-2" />);
  view.rerender(<GroupDetail {...props} groupId="group-1" />);
  await waitFor(() => expect(listSnapshots).toHaveBeenCalledTimes(3));
  await act(async () => {
    resolveCancel?.({
      data: { ...progress, group_id: "group-1" },
      warnings: [],
    } as CancelResponse);
  });
  expect(screen.queryByText("Cancellation receipt received.")).toBeNull();
  expect(listSnapshots).toHaveBeenCalledTimes(3);
  navigation.dispose();
});
