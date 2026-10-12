import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect, useState } from "react";
import { expect, it } from "vitest";
import type { ApiOperationData, ApiResult } from "../../api/client";
import { disconnectedWorkspace } from "../../workspace/gateway";
import { WorkspaceNavigation } from "../../workspace/navigation";
import { routeToHash } from "../../workspace/routes";
import { ComparisonPage } from "./ComparisonPage";

type Evaluation = ApiOperationData<"readEvaluation">;
type Comparison = ApiOperationData<"createComparison">;

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => {
    resolve = accept;
  });
  return { promise, resolve };
}

function evaluation(id: string): Evaluation {
  return {
    schema_version: 1,
    evaluation_id: id,
    run_id: `run-${id}`,
    result_snapshot_id: `result-${id}`,
    label_snapshot_id: `labels-${id}`,
    mode: "original",
    replayed: false,
    created_at: "2026-10-11T00:00:00Z",
    execution_operation_id: null,
    content_hash: `hash-${id}`,
    metrics: {},
    metrics_source: "fixture",
  };
}

function comparison(leftId: string, rightId: string): Comparison {
  return {
    schema_version: 1,
    comparison_id: "comparison-1",
    content_hash: "comparison-hash",
    created_at: "2026-10-11T00:00:00Z",
    left_evaluation_id: leftId,
    left_result_snapshot_id: `result-${leftId}`,
    outcomes: { primary_counts: {} },
    replayed: true,
    right_evaluation_id: rightId,
    right_result_snapshot_id: `result-${rightId}`,
  };
}

it("rejects mismatched comparison receipt IDs and retries the exact retained request", async () => {
  window.history.replaceState(null, "", "#/p/registration-1/comparisons");
  const navigation = new WorkspaceNavigation(window);
  const createRequests: Parameters<
    typeof disconnectedWorkspace.debugging.comparisons.create
  >[0][] = [];
  let creates = 0;
  let evaluationReads = 0;
  const debugging = {
    ...disconnectedWorkspace.debugging,
    comparisons: {
      ...disconnectedWorkspace.debugging.comparisons,
      create: async (
        request: Parameters<
          typeof disconnectedWorkspace.debugging.comparisons.create
        >[0],
      ) => {
        createRequests.push(request);
        creates += 1;
        const ids =
          creates === 1
            ? ["wrong-left", "wrong-right"]
            : ["evaluation-left", "evaluation-right"];
        return { data: comparison(ids[0]!, ids[1]!), warnings: [] };
      },
    },
  };
  const execution = {
    ...disconnectedWorkspace.execution,
    inspection: {
      ...disconnectedWorkspace.execution.inspection,
      readEvaluation: async ({
        evaluationId,
      }: {
        registrationId: string;
        evaluationId: string;
      }) => {
        evaluationReads += 1;
        return { data: evaluation(evaluationId), warnings: [] };
      },
    },
  };
  const tree = render(
    <ComparisonPage
      registrationId="registration-1"
      debugging={debugging}
      execution={execution}
      navigation={navigation}
    />,
  );
  const user = userEvent.setup();
  try {
    await user.type(
      screen.getByLabelText("Left saved evaluation ID"),
      "evaluation-left",
    );
    await user.type(
      screen.getByLabelText("Right saved evaluation ID"),
      "evaluation-right",
    );
    await user.click(
      screen.getByRole("button", { name: "Verify saved evaluations" }),
    );
    expect(
      await screen.findByLabelText("Verified evaluation context"),
    ).toBeTruthy();
    expect(evaluationReads).toBe(2);
    await user.click(
      screen.getByRole("button", { name: "Create saved comparison" }),
    );
    expect(
      await screen.findByRole("button", {
        name: "Retry original unchanged comparison",
      }),
    ).toBeTruthy();
    expect(createRequests).toHaveLength(1);
    const original = createRequests[0]!;
    expect(original.body.left_evaluation_id).toBe("evaluation-left");
    expect(original.body.right_evaluation_id).toBe("evaluation-right");
    expect(screen.queryByText(/Comparison comparison-1/)).toBeNull();

    await user.click(
      screen.getByRole("button", {
        name: "Retry original unchanged comparison",
      }),
    );
    expect(createRequests).toHaveLength(2);
    expect(createRequests[1]?.body).toBe(original.body);
    expect(createRequests[1]?.body).toEqual(original.body);
    expect(createRequests[1]?.body.operation_id).toBe(
      original.body.operation_id,
    );
    expect(creates).toBe(2);
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});

it("keeps a committed comparison receipt when a real dirty guard denies navigation", async () => {
  window.history.replaceState(null, "", "#/p/registration-1/comparisons");
  const navigation = new WorkspaceNavigation(window);
  let creates = 0;
  let evaluationReads = 0;
  let comparisonReads = 0;
  const comparisonReadIdentities: Array<{
    registrationId: string;
    comparisonId: string;
  }> = [];
  let savedComparison: ApiOperationData<"readComparison"> | undefined;
  const debugging = {
    ...disconnectedWorkspace.debugging,
    comparisons: {
      ...disconnectedWorkspace.debugging.comparisons,
      create: async (
        request: Parameters<
          typeof disconnectedWorkspace.debugging.comparisons.create
        >[0],
      ) => {
        creates += 1;
        const receipt: ApiOperationData<"readComparison"> = {
          ...comparison(
            request.body.left_evaluation_id,
            request.body.right_evaluation_id,
          ),
          replayed: false,
        };
        savedComparison = receipt;
        return { data: receipt, warnings: [] };
      },
      list: async () => ({
        data: { items: [], next_cursor: null, total: "0" },
        warnings: [],
      }),
      read: async (
        request: Parameters<
          typeof disconnectedWorkspace.debugging.comparisons.read
        >[0],
      ) => {
        comparisonReads += 1;
        comparisonReadIdentities.push({
          registrationId: request.registrationId,
          comparisonId: request.comparisonId,
        });
        if (!savedComparison)
          throw new Error("The comparison receipt was not saved.");
        return { data: savedComparison, warnings: [] };
      },
    },
  };
  const execution = {
    ...disconnectedWorkspace.execution,
    inspection: {
      ...disconnectedWorkspace.execution.inspection,
      readEvaluation: async ({
        evaluationId,
      }: {
        registrationId: string;
        evaluationId: string;
      }) => {
        evaluationReads += 1;
        return { data: evaluation(evaluationId), warnings: [] };
      },
    },
  };

  function RoutedComparisonPage() {
    const [route, setRoute] = useState(navigation.current);
    useEffect(() => navigation.subscribe(setRoute), []);
    if (route.kind === "comparison")
      return (
        <ComparisonPage
          key={`saved:${route.comparisonId}`}
          registrationId={route.registrationId}
          comparisonId={route.comparisonId}
          debugging={debugging}
          execution={execution}
          navigation={navigation}
        />
      );
    return (
      <ComparisonPage
        key="comparison-list"
        registrationId="registration-1"
        debugging={debugging}
        execution={execution}
        navigation={navigation}
      />
    );
  }

  const tree = render(<RoutedComparisonPage />);
  const user = userEvent.setup();
  let foreignGuardCalls = 0;
  let unregisterForeignGuard: (() => void) | undefined;
  try {
    await user.type(
      screen.getByLabelText("Left saved evaluation ID"),
      "evaluation-left",
    );
    await user.type(
      screen.getByLabelText("Right saved evaluation ID"),
      "evaluation-right",
    );
    await user.click(
      screen.getByRole("button", { name: "Verify saved evaluations" }),
    );
    await screen.findByLabelText("Verified evaluation context");
    expect(evaluationReads).toBe(2);

    await user.click(
      screen.getByRole("button", { name: "Create saved comparison" }),
    );
    const openSaved = await screen.findByRole("button", {
      name: "Open saved comparison",
    });
    expect(creates).toBe(1);
    expect(savedComparison?.comparison_id).toBe("comparison-1");

    const denyNavigation = Object.assign(
      async () => {
        foreignGuardCalls += 1;
        return false;
      },
      { isDirty: () => true },
    );
    unregisterForeignGuard = navigation.registerDirtyGuard(
      "unrelated-dirty-editor",
      denyNavigation,
    );
    await user.click(openSaved);
    await waitFor(() => expect(foreignGuardCalls).toBe(1));
    expect(navigation.current.kind).toBe("comparisons");
    expect(
      screen.getByRole("button", { name: "Open saved comparison" }),
    ).toBeTruthy();
    expect(
      (screen.getByLabelText("Left saved evaluation ID") as HTMLInputElement)
        .value,
    ).toBe("evaluation-left");
    expect(
      (screen.getByLabelText("Right saved evaluation ID") as HTMLInputElement)
        .value,
    ).toBe("evaluation-right");
    expect(
      (
        screen.getByRole("button", {
          name: "Create saved comparison",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(
      screen.queryByRole("dialog", { name: "Unsaved changes" }),
    ).toBeNull();
    expect(creates).toBe(1);
    expect(evaluationReads).toBe(2);
    expect(comparisonReads).toBe(0);

    unregisterForeignGuard();
    unregisterForeignGuard = undefined;
    await user.click(
      screen.getByRole("button", { name: "Open saved comparison" }),
    );
    const pinned = await screen.findByRole("region", {
      name: "Pinned comparison details",
    });
    const expectedRoute = {
      kind: "comparison" as const,
      registrationId: "registration-1",
      comparisonId: "comparison-1",
    };
    await waitFor(() => expect(navigation.current).toEqual(expectedRoute));
    expect(window.location.hash).toBe(routeToHash(expectedRoute));
    expect(comparisonReads).toBe(1);
    expect(comparisonReadIdentities).toEqual([
      {
        registrationId: "registration-1",
        comparisonId: "comparison-1",
      },
    ]);
    expect(pinned.querySelector("code")?.textContent).toBe("comparison-1");
    const pinnedSides = pinned.querySelectorAll("dd");
    expect(pinnedSides[0]?.textContent?.trim()).toBe(
      "evaluation-left · result result-evaluation-left",
    );
    expect(pinnedSides[1]?.textContent?.trim()).toBe(
      "evaluation-right · result result-evaluation-right",
    );
    expect(
      screen.queryByRole("dialog", { name: "Unsaved changes" }),
    ).toBeNull();

    await act(async () => {
      await expect(
        navigation.navigate({
          kind: "comparisons",
          registrationId: "registration-1",
        }),
      ).resolves.toBe(true);
    });
    expect(navigation.current.kind).toBe("comparisons");
    expect(
      (
        (await screen.findByLabelText(
          "Left saved evaluation ID",
        )) as HTMLInputElement
      ).value,
    ).toBe("");
    expect(
      (screen.getByLabelText("Right saved evaluation ID") as HTMLInputElement)
        .value,
    ).toBe("");
    expect(
      screen.queryByRole("button", { name: "Open saved comparison" }),
    ).toBeNull();
    expect(
      (
        screen.getByRole("button", {
          name: "Create saved comparison",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(creates).toBe(1);
    expect(evaluationReads).toBe(2);
    expect(comparisonReads).toBe(1);
    expect(comparisonReadIdentities).toHaveLength(1);
  } finally {
    unregisterForeignGuard?.();
    tree.unmount();
    navigation.dispose();
  }
});

it("does not publish stale saved-evaluation reads across A-to-B-to-A registration scopes", async () => {
  window.history.replaceState(null, "", "#/p/registration-1/comparisons");
  const navigation = new WorkspaceNavigation(window);
  const pending: Array<ReturnType<typeof deferred<ApiResult<Evaluation>>>> = [];
  let settledReads = 0;
  const debugging = {
    ...disconnectedWorkspace.debugging,
    comparisons: {
      ...disconnectedWorkspace.debugging.comparisons,
      list: async () => ({
        data: { items: [], next_cursor: null, total: "0" },
        warnings: [],
      }),
    },
  };
  const execution = {
    ...disconnectedWorkspace.execution,
    inspection: {
      ...disconnectedWorkspace.execution.inspection,
      readEvaluation: () => {
        const request = deferred<ApiResult<Evaluation>>();
        pending.push(request);
        return request.promise.then((result) => {
          settledReads += 1;
          return result;
        });
      },
    },
  };
  const tree = render(
    <ComparisonPage
      registrationId="registration-1"
      debugging={debugging}
      execution={execution}
      navigation={navigation}
    />,
  );
  const user = userEvent.setup();
  try {
    await user.type(
      screen.getByLabelText("Left saved evaluation ID"),
      "evaluation-old-left",
    );
    await user.type(
      screen.getByLabelText("Right saved evaluation ID"),
      "evaluation-old-right",
    );
    await user.click(
      screen.getByRole("button", { name: "Verify saved evaluations" }),
    );
    await waitFor(() => expect(pending).toHaveLength(2));
    tree.rerender(
      <ComparisonPage
        registrationId="registration-B"
        debugging={debugging}
        execution={execution}
        navigation={navigation}
      />,
    );
    tree.rerender(
      <ComparisonPage
        registrationId="registration-1"
        debugging={debugging}
        execution={execution}
        navigation={navigation}
      />,
    );
    await user.type(
      screen.getByLabelText("Left saved evaluation ID"),
      "evaluation-new-left",
    );
    await user.type(
      screen.getByLabelText("Right saved evaluation ID"),
      "evaluation-new-right",
    );
    await user.click(
      screen.getByRole("button", { name: "Verify saved evaluations" }),
    );
    await waitFor(() => expect(pending).toHaveLength(4));

    pending[2]?.resolve({
      data: evaluation("evaluation-new-left"),
      warnings: [],
    });
    pending[3]?.resolve({
      data: evaluation("evaluation-new-right"),
      warnings: [],
    });
    expect(
      await screen.findByLabelText("Verified evaluation context"),
    ).toBeTruthy();
    pending[0]?.resolve({
      data: evaluation("evaluation-old-left"),
      warnings: [],
    });
    pending[1]?.resolve({
      data: evaluation("evaluation-old-right"),
      warnings: [],
    });
    await waitFor(() => expect(settledReads).toBe(4));
    expect(
      screen.getByLabelText("Verified evaluation context").textContent,
    ).toContain("evaluation-new-left");
    expect(
      screen.getByLabelText("Verified evaluation context").textContent,
    ).not.toContain("evaluation-old-left");
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});
