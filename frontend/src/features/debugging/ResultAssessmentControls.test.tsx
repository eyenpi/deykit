import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { ApiOperationData } from "../../api/client";
import { disconnectedWorkspace } from "../../workspace/gateway";
import { WorkspaceNavigation } from "../../workspace/navigation";
import { ResultAssessmentControls } from "./ResultAssessmentControls";

function result<T>(data: T) {
  return Promise.resolve({ data, warnings: [] });
}

it("retains an evaluation body after an unknown response and blocks a duplicate submit", async () => {
  window.history.replaceState(null, "", "#/p/registration-1/runs/run-1");
  const navigation = new WorkspaceNavigation(window);
  const calls: Parameters<typeof disconnectedWorkspace.debugging.evaluations.create>[0][] = [];
  const receipt: ApiOperationData<"createEvaluation"> = {
    schema_version: 1,
    evaluation_id: "evaluation-1",
    run_id: "run-1",
    result_snapshot_id: "result-1",
    label_snapshot_id: "labels-1",
    mode: "original",
    replayed: true,
    created_at: "2026-10-11T00:00:00Z",
    execution_operation_id: null,
    content_hash: "a".repeat(64),
    metrics: {},
    metrics_source: "{}",
  };
  let sends = 0;
  const operations = {
    ...disconnectedWorkspace.debugging.evaluations,
    create: async (request: (typeof calls)[number]) => {
      calls.push(request);
      sends += 1;
      if (sends === 1) throw new Error("connection closed after send");
      return result(receipt);
    },
  };
  const onBusyChange = vi.fn();
  const tree = render(
    <ResultAssessmentControls
      registrationId="registration-1"
      runId="run-1"
      resultSnapshotId="result-1"
      labelSnapshotId="labels-1"
      scopeIdentity="registration-1|run-1|epoch-1"
      isCurrent
      onBusyChange={onBusyChange}
      operations={operations}
      navigation={navigation}
    />,
  );
  try {
    const save = screen.getByRole("button", { name: "Save evaluation" });
    fireEvent.click(save);
    fireEvent.click(save);
    await waitFor(() => expect(screen.getByRole("button", { name: "Retry original unchanged request" })).toBeTruthy());
    expect(calls).toHaveLength(1);
    const retained = calls[0];
    if (!retained) throw new Error("The evaluation request was not captured.");
    await screen.getByRole("button", { name: "Retry original unchanged request" }).click();
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("evaluation-1"));
    expect(calls).toHaveLength(2);
    expect(calls[1]).toEqual(retained);
    expect(calls[1]?.body.operation_id).toBe(retained.body.operation_id);
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});
