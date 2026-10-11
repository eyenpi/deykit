import { useEffect, useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { ApiOperationData, ApiResult } from "../../api/client";
import { RunDetail } from "./RunDetail";
import { disconnectedWorkspace } from "../../workspace/gateway";
import type { ProjectOverview } from "../../workspace/gateway";
import { WorkspaceNavigation } from "../../workspace/navigation";
import type { WorkspaceRoute } from "../../workspace/routes";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => {
    resolve = accept;
  });
  return { promise, resolve };
}

const run: ApiOperationData<"readRun"> = {
  schema_version: 1,
  run_id: "run-1",
  mode: "fixture",
  state: "running",
  execution_active: true,
  decision_id: "decision-1",
  dataset_id: "dataset-1",
  requested_model: "authored-model",
  execution_group_id: null,
  group_attempts_remaining: null,
  attempts_used: "1",
  attempt_limit: "10",
  attempts_remaining: "9",
  replayed: false,
  reason: null,
  result_snapshot_ids: [],
  latest_result_snapshot_id: null,
  segment_ids: ["segment-1"],
  segments: [
    {
      segment_id: "segment-1",
      started_at: "2026-10-11T00:00:00Z",
      deadline_at: "2026-10-11T00:10:00Z",
      ended_at: null,
      retry_unknown: false,
    },
  ],
  attempts: [],
  cases: [{ case_id: "case-1", status: "running", attempt_id: "attempt-1", error: null }],
  settings: {
    max_attempts: "10",
    concurrency: "1",
    timeout_seconds: "30",
    deadline_seconds: "600",
    max_retries_per_case: "0",
  },
  sources: {
    decision_revision_id: "revision-1",
    dataset_snapshot_id: "dataset-snapshot-1",
    development_dataset_snapshot_id: "development-dataset-1",
    label_snapshot_id: "label-snapshot-1",
    development_label_snapshot_id: "development-label-1",
    fixture_set_id: "fixture-set-1",
    provider_profile_id: "fixture-profile-1",
    option_order: null,
    adapter: "fixture",
    compiler_id: "fixture-compiler",
    compiler_version: "1",
    compiler_id_unavailable_reason: null,
    evidence_mode: "authored_fixture",
  },
};

const project: ProjectOverview = {
  id: "registration-1",
  name: "Authored project",
  path: "/tmp/authored-project",
  decisions: [{ id: "decision-1", name: "Authored decision" }],
  datasets: [{ id: "dataset-1", name: "Authored dataset" }],
  warnings: [],
};

function RunRoute({
  navigation,
  execution,
}: {
  navigation: WorkspaceNavigation;
  execution: typeof disconnectedWorkspace.execution;
}) {
  const [route, setRoute] = useState<WorkspaceRoute>(navigation.current);
  useEffect(() => navigation.subscribe(setRoute), [navigation]);
  if (route.kind !== "run") return <h1>Runs</h1>;
  return (
    <RunDetail
      registrationId={route.registrationId}
      runId={route.runId}
      execution={execution}
      readRevision={disconnectedWorkspace.authoring.decisions.revision}
      project={project}
      navigation={navigation}
    />
  );
}

it("publishes the first progress read and suppresses a held refresh after route exit", async () => {
  window.history.replaceState(null, "", "#/p/registration-1/runs/run-1");
  const navigation = new WorkspaceNavigation(window);
  const reads: Array<ReturnType<typeof deferred<ApiResult<ApiOperationData<"readRun">>>>> = [];
  const read = vi.fn(() => {
    const pending = deferred<ApiResult<ApiOperationData<"readRun">>>();
    reads.push(pending);
    return pending.promise;
  });
  const execution = {
    ...disconnectedWorkspace.execution,
    runs: { ...disconnectedWorkspace.execution.runs, read },
  };
  const tree = render(<RunRoute navigation={navigation} execution={execution} />);
  const user = userEvent.setup();
  try {
    await waitFor(() => expect(read).toHaveBeenCalledTimes(1));
    reads[0]?.resolve({ data: run, warnings: [] });
    expect(await screen.findByRole("heading", { name: "Run run-1" })).toBeTruthy();
    expect(screen.getByText("running · execution active; fixture")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Refresh progress" }));
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    const obsoleteRead = reads[1];
    if (!obsoleteRead) throw new Error("The refresh request was not captured.");
    await navigation.navigate({ kind: "runs", registrationId: "registration-1" });
    expect(await screen.findByRole("heading", { name: "Runs" })).toBeTruthy();
    obsoleteRead.resolve({ data: { ...run, state: "completed", execution_active: false }, warnings: [] });
    await waitFor(() => expect(screen.getByRole("heading", { name: "Runs" })).toBeTruthy());
    expect(screen.queryByRole("heading", { name: "Run run-1" })).toBeNull();
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});
