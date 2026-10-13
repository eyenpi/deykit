import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { useLayoutEffect } from "react";
import { afterEach, expect, it, vi } from "vitest";
import type { ApiOperationData } from "../../../api/client";
import { disconnectedWorkspace } from "../../../workspace/gateway";
import type {
  ProjectOverview,
  WorkspaceGateway,
} from "../../../workspace/gateway";
import { WorkspaceNavigation } from "../../../workspace/navigation";
import { GroupDetail } from "./GroupDetail";

const project: ProjectOverview = {
  id: "registration-1",
  name: "Polling fixture",
  path: "/tmp/polling-fixture",
  decisions: [],
  datasets: [],
  warnings: [],
};

const navigations: WorkspaceNavigation[] = [];

function createNavigation(): WorkspaceNavigation {
  const navigation = new WorkspaceNavigation(window);
  navigations.push(navigation);
  return navigation;
}

function groupProgress(
  groupId: string,
  state: string,
  executionActive: boolean,
  attemptsUsed = "1",
  empty = false,
): ApiOperationData<"readChoiceOrder">["group"] {
  return {
    schema_version: 1,
    group_id: groupId,
    kind: "choice_order",
    seed: "9",
    algorithm: "seeded-v1",
    independent_case_count: "1",
    initial_requests: "1",
    attempt_limit: "4",
    attempts_used: attemptsUsed,
    attempts_remaining: "3",
    replayed: false,
    snapshot_id: null,
    members: empty
      ? []
      : [
          {
            schema_version: 1,
            run_id: `${groupId}-run`,
            state,
            attempts_used: attemptsUsed,
            attempt_limit: "4",
            attempts_remaining: "3",
            cases: [],
            attempts: [],
            dataset_id: "dataset-1",
            decision_id: "decision-1",
            execution_active: executionActive,
            execution_group_id: groupId,
            group_attempts_remaining: "3",
            latest_result_snapshot_id: null,
            mode: "fixture",
            reason: null,
            replayed: false,
            requested_model: "fixture-model",
            result_snapshot_ids: [],
            segment_ids: [],
            segments: [],
            settings: {},
            sources: {},
          },
        ],
  } as unknown as ApiOperationData<"readChoiceOrder">["group"];
}

afterEach(() => {
  cleanup();
  for (const navigation of navigations.splice(0)) navigation.dispose();
  vi.useRealTimers();
});

function readResponse(group: ApiOperationData<"readChoiceOrder">["group"]): {
  data: ApiOperationData<"readChoiceOrder">;
  warnings: string[];
} {
  return {
    data: { group, exit_code: 0, summary: null },
    warnings: [],
  };
}

function snapshotRecord(
  id: string,
  groupId: string,
): ApiOperationData<"listChoiceOrderSnapshots">[number] {
  return {
    id,
    sequence: "1",
    group_id: groupId,
    segment_id: null,
    content_hash: "a".repeat(64),
    created_at: "2026-10-11T00:00:01Z",
    results: [],
  };
}

function snapshotDetail(
  id: string,
  groupId: string,
): ApiOperationData<"readChoiceOrderSnapshot"> {
  return {
    snapshot: snapshotRecord(id, groupId),
    members: [],
    summary: {
      independent_case_count: "0",
      order_count: "0",
      expanded_result_count: "0",
      fully_observed_case_count: "0",
      disagreement: {
        numerator: "0",
        denominator: "0",
        value: null,
        reason: "no_fully_observed_cases",
      },
      cases: [],
      interpretation: "observed_request_order_sensitivity",
    },
  };
}

function gatewayFor(
  read: (...args: never[]) => Promise<unknown>,
  listSnapshots: (...args: never[]) => Promise<unknown> = async () => ({
    data: [],
    warnings: [],
  }),
  readSnapshot: (...args: never[]) => Promise<unknown> = async () => ({
    data: snapshotDetail("snapshot-default", "group-a"),
    warnings: [],
  }),
): WorkspaceGateway {
  return {
    ...disconnectedWorkspace,
    debugging: {
      ...disconnectedWorkspace.debugging,
      diagnostics: {
        ...disconnectedWorkspace.debugging.diagnostics,
        read,
        listSnapshots,
        readSnapshot,
      },
    },
  } as unknown as WorkspaceGateway;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (cause: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

it("serializes progress and snapshot reads and schedules the next pair after settlement", async () => {
  vi.useFakeTimers();
  const firstProgress = deferred<Awaited<ReturnType<typeof readResponse>>>();
  const firstSnapshots = deferred<{ data: never[]; warnings: never[] }>();
  const read = vi
    .fn()
    .mockReturnValueOnce(firstProgress.promise)
    .mockResolvedValue(readResponse(groupProgress("group-a", "running", true)));
  const listSnapshots = vi
    .fn()
    .mockReturnValueOnce(firstSnapshots.promise)
    .mockResolvedValue({ data: [], warnings: [] });
  const navigation = createNavigation();
  render(
    <GroupDetail
      project={project}
      gateway={gatewayFor(read, listSnapshots)}
      navigation={navigation}
      kind="diagnostic"
      groupId="group-a"
    />,
  );

  await act(async () => {
    await Promise.resolve();
  });
  expect(read).toHaveBeenCalledTimes(1);
  expect(listSnapshots).not.toHaveBeenCalled();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(7_500);
  });
  expect(read).toHaveBeenCalledTimes(1);
  expect(listSnapshots).not.toHaveBeenCalled();

  await act(async () => {
    firstProgress.resolve(
      readResponse(groupProgress("group-a", "running", true)),
    );
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(listSnapshots).toHaveBeenCalledTimes(1);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(7_500);
  });
  expect(read).toHaveBeenCalledTimes(1);
  expect(listSnapshots).toHaveBeenCalledTimes(1);

  await act(async () => {
    firstSnapshots.resolve({ data: [], warnings: [] });
    await Promise.resolve();
    await Promise.resolve();
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2_499);
  });
  expect(read).toHaveBeenCalledTimes(1);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1);
  });
  expect(read).toHaveBeenCalledTimes(2);
  expect(listSnapshots).toHaveBeenCalledTimes(2);
  vi.useRealTimers();
});

it("does not publish or continue an A1 poll after A to B to A2 scope changes", async () => {
  const oldProgress = deferred<Awaited<ReturnType<typeof readResponse>>>();
  const oldRead = vi.fn(() => oldProgress.promise);
  const oldList = vi.fn(async () => ({ data: [], warnings: [] }));
  const currentRead = vi.fn(async () =>
    readResponse(groupProgress("group-a", "running", true, "2")),
  );
  const currentList = vi.fn(async () => ({ data: [], warnings: [] }));
  const navigation = createNavigation();
  const view = render(
    <GroupDetail
      project={project}
      gateway={gatewayFor(oldRead, oldList)}
      navigation={navigation}
      kind="diagnostic"
      groupId="group-a"
    />,
  );
  await act(async () => {
    await Promise.resolve();
  });
  expect(oldRead).toHaveBeenCalledTimes(1);

  view.rerender(
    <GroupDetail
      project={project}
      gateway={gatewayFor(async () => ({
        data: {
          group: groupProgress("group-b", "running", true),
          exit_code: 0,
          summary: null,
        },
        warnings: [],
      }))}
      navigation={navigation}
      kind="diagnostic"
      groupId="group-b"
    />,
  );
  view.rerender(
    <GroupDetail
      project={project}
      gateway={gatewayFor(currentRead, currentList)}
      navigation={navigation}
      kind="diagnostic"
      groupId="group-a"
    />,
  );
  await screen.findAllByText("2");
  expect(currentRead).toHaveBeenCalledTimes(1);
  await waitFor(() => expect(currentList).toHaveBeenCalledTimes(1));

  await act(async () => {
    oldProgress.resolve(
      readResponse(groupProgress("group-a", "completed", false, "99")),
    );
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(oldList).not.toHaveBeenCalled();
  expect(currentList).toHaveBeenCalledTimes(1);
  expect(screen.queryByText("99")).toBeNull();
});

it("aborts its captured read on unmount and does not admit a late result", async () => {
  const heldProgress = deferred<Awaited<ReturnType<typeof readResponse>>>();
  let signal: AbortSignal | undefined;
  const read = vi.fn(
    (
      { signal: requestSignal }: { signal: AbortSignal } = {
        signal: new AbortController().signal,
      },
    ) => {
      signal = requestSignal;
      return heldProgress.promise;
    },
  );
  const listSnapshots = vi.fn(async () => ({ data: [], warnings: [] }));
  const navigation = createNavigation();
  const view = render(
    <GroupDetail
      project={project}
      gateway={gatewayFor(read, listSnapshots)}
      navigation={navigation}
      kind="diagnostic"
      groupId="group-a"
    />,
  );
  await act(async () => {
    await Promise.resolve();
  });
  expect(signal?.aborted).toBe(false);
  view.unmount();
  expect(signal?.aborted).toBe(true);
  await act(async () => {
    heldProgress.reject(new Error("stale read failure"));
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(listSnapshots).not.toHaveBeenCalled();
});

it.each(["success", "error"])(
  "fences a historical snapshot %s during render before passive cleanup",
  async (outcome) => {
    const oldDetail = deferred<{
      data: ApiOperationData<"readChoiceOrderSnapshot">;
      warnings: string[];
    }>();
    let oldSignal: AbortSignal | undefined;
    const readSnapshot = vi.fn((request?: { signal: AbortSignal }) => {
      oldSignal = request?.signal;
      return oldDetail.promise;
    });
    const makeScopeGateway = (groupId: string, detailGateway = false) =>
      gatewayFor(
        async () => readResponse(groupProgress(groupId, "running", true)),
        async () => ({
          data:
            groupId === "group-a"
              ? [snapshotRecord("snapshot-a", groupId)]
              : [],
          warnings: [],
        }),
        detailGateway
          ? readSnapshot
          : async (
              { snapshotId }: { snapshotId: string } = {
                snapshotId: "snapshot-default",
              },
            ) => ({
              data: snapshotDetail(snapshotId, groupId),
              warnings: [],
            }),
      );
    const gatewayA = makeScopeGateway("group-a", true);
    const gatewayB = makeScopeGateway("group-b");
    const navigation = createNavigation();

    function ScopeHarness({ groupId }: { groupId: string }) {
      useLayoutEffect(() => {
        if (groupId !== "group-b") return;
        expect(oldSignal?.aborted).toBe(false);
        if (outcome === "success")
          oldDetail.resolve({
            data: snapshotDetail("snapshot-a", "group-a"),
            warnings: [],
          });
        else oldDetail.reject(new Error("stale snapshot read failure"));
      }, [groupId, outcome]);
      return (
        <GroupDetail
          project={project}
          gateway={groupId === "group-a" ? gatewayA : gatewayB}
          navigation={navigation}
          kind="diagnostic"
          groupId={groupId}
        />
      );
    }

    const view = render(<ScopeHarness groupId="group-a" />);
    await waitFor(() => expect(readSnapshot).toHaveBeenCalledTimes(1));
    view.rerender(<ScopeHarness groupId="group-b" />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.queryByText("Selected immutable snapshot")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  },
);

it("settles synchronous read and list throws before scheduling one recovery pair", async () => {
  vi.useFakeTimers();
  const read = vi
    .fn()
    .mockImplementationOnce(() => {
      throw new Error("synchronous progress failure");
    })
    .mockResolvedValue(readResponse(groupProgress("group-a", "running", true)));
  const listSnapshots = vi
    .fn()
    .mockImplementationOnce(() => {
      throw new Error("synchronous snapshot-list failure");
    })
    .mockResolvedValue({ data: [], warnings: [] });
  const navigation = createNavigation();
  render(
    <GroupDetail
      project={project}
      gateway={gatewayFor(read, listSnapshots)}
      navigation={navigation}
      kind="diagnostic"
      groupId="group-a"
    />,
  );
  await act(async () => {
    await Promise.resolve();
  });
  expect(read).toHaveBeenCalledTimes(1);
  expect(listSnapshots).toHaveBeenCalledTimes(1);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2_500);
  });
  expect(read).toHaveBeenCalledTimes(2);
  expect(listSnapshots).toHaveBeenCalledTimes(2);
});

it("coalesces a known cancellation receipt into one follow-up pair and keeps it after a read error", async () => {
  const firstSnapshots = deferred<{ data: never[]; warnings: never[] }>();
  const read = vi
    .fn()
    .mockResolvedValueOnce(
      readResponse(groupProgress("group-a", "running", true)),
    )
    .mockRejectedValueOnce(new Error("read failed after the receipt"));
  const listSnapshots = vi
    .fn()
    .mockReturnValueOnce(firstSnapshots.promise)
    .mockResolvedValue({ data: [], warnings: [] });
  const cancel = vi.fn(async () => ({
    data: groupProgress("group-a", "cancelled", false),
    warnings: [],
  }));
  const baseGateway = gatewayFor(read, listSnapshots);
  const gateway = {
    ...baseGateway,
    debugging: {
      ...baseGateway.debugging,
      diagnostics: { ...baseGateway.debugging.diagnostics, cancel },
    },
  } as WorkspaceGateway;
  const navigation = createNavigation();
  render(
    <GroupDetail
      project={project}
      gateway={gateway}
      navigation={navigation}
      kind="diagnostic"
      groupId="group-a"
    />,
  );
  await screen.findByText("Current progress");
  expect(read).toHaveBeenCalledTimes(1);
  expect(listSnapshots).toHaveBeenCalledTimes(1);

  await act(async () => {
    screen.getByRole("button", { name: "Cancel group" }).click();
  });
  expect(
    await screen.findByText("Cancellation receipt received."),
  ).toBeTruthy();
  expect(cancel).toHaveBeenCalledTimes(1);

  await act(async () => {
    firstSnapshots.resolve({ data: [], warnings: [] });
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(read).toHaveBeenCalledTimes(2);
  await waitFor(() => expect(listSnapshots).toHaveBeenCalledTimes(2));
  expect(screen.getByText("Cancellation receipt received.")).toBeTruthy();
});

const settledMemberStates = [
  "cancelled",
  "completed",
  "completed_with_errors",
  "budget_exhausted",
  "interrupted",
  "preflight_failed",
];

it.each(settledMemberStates)(
  "shows %s as settled only when inactive",
  async (state) => {
    const navigation = createNavigation();
    const read = vi.fn(async () =>
      readResponse(groupProgress("group-a", state, false)),
    );
    render(
      <GroupDetail
        project={project}
        gateway={gatewayFor(read)}
        navigation={navigation}
        kind="diagnostic"
        groupId="group-a"
      />,
    );
    expect(await screen.findByText("Settled")).toBeTruthy();
  },
);

it.each([
  ["active completed", "completed", true],
  ["nonterminal", "failed", false],
  ["mixed members", "mixed", false],
  ["empty member list", "empty", false],
])("shows %s as running", async (_name, state, active) => {
  const navigation = createNavigation();
  let group =
    state === "mixed"
      ? groupProgress("group-a", "completed", false)
      : groupProgress(
          "group-a",
          String(state),
          Boolean(active),
          "1",
          state === "empty",
        );
  const firstMember = group.members[0];
  if (state === "mixed" && firstMember)
    group = {
      ...group,
      members: [
        ...group.members,
        {
          ...firstMember,
          run_id: "group-a-active-run",
          state: "running",
          execution_active: true,
        },
      ],
    };
  const read = vi.fn(async () => readResponse(group));
  render(
    <GroupDetail
      project={project}
      gateway={gatewayFor(read)}
      navigation={navigation}
      kind="diagnostic"
      groupId="group-a"
    />,
  );
  expect(await screen.findByText("Running")).toBeTruthy();
});
