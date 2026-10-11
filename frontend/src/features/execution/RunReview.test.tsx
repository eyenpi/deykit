import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { RunReview } from "./RunReview";
import { WorkspaceNavigation } from "../../workspace/navigation";
import { disconnectedWorkspace } from "../../workspace/gateway";
import type { ProjectOverview, WorkspaceGateway } from "../../workspace/gateway";

const requestSource = '{"large":9007199254740993,"fraction":1.2300}';

function result<T>(data: T) {
  return Promise.resolve({ data, warnings: [] });
}

it("retries an unknown run start with the exact reviewed request and operation id", async () => {
  const decision = { id: "decision-1", name: "Classify the example" };
  const project: ProjectOverview = {
    id: "registration-1",
    name: "Offline fixture project",
    path: "/tmp/offline-fixture",
    decisions: [decision],
    datasets: [{ id: "dataset-1", name: "Authored examples" }],
    warnings: [],
  };
  const preview: ApiOperationData<"previewRun"> = {
    schema_version: 1,
    decision_id: "decision-1",
    dataset_id: "dataset-1",
    mode: "fixture",
    fixture_set_id: "fixture-set-1",
    provider_id: "fixture-provider",
    requested_model: "fixture-model",
    selected_case_ids: ["case-1"],
    initial_requests: "1",
    invalid_cases: [],
    dry_run: true,
    development_case_count: "1",
    settings: {
      max_attempts: "100",
      concurrency: "2",
      timeout_seconds: "60",
      deadline_seconds: "600",
      max_retries_per_case: "1",
    },
    review_context_hash: "a".repeat(64),
    review_context: {
      schema_version: 1,
      definition_source: "draft",
      revision_id: null,
      definition_hash: "b".repeat(64),
      source_context_hash: "c".repeat(64),
      provider_id: "fixture-provider",
      destination: "authored fixture",
      adapter: "fixture",
      requested_model: "fixture-model",
      compiler_id: "fixture-compiler",
      compiler_version: "1",
      fixture_set_id: "fixture-set-1",
      development_case_ids: ["case-1"],
      development_label_count: "1",
      source_records: [],
    },
    case_reviews: [
      {
        case_id: "case-1",
        input_hash: "d".repeat(64),
        request_hash: "e".repeat(64),
        compiler: "fixture-compiler",
        compiler_version: "1",
        requested_model: "fixture-model",
        input_error: null,
        request_source: requestSource,
        request_source_redacted: false,
      },
    ],
  };
  const fixture: ApiOperationData<"listFixtureSets">["items"][number] = {
    schema_version: 1,
    id: "fixture-set-1",
    name: "Offline fixture",
    dataset_id: "dataset-1",
    decision_id: "decision-1",
    model_identity: "fixture-model",
    content_hash: "f".repeat(64),
    binding_count: "1",
    bindings: [
      {
        schema_version: 1,
        id: "binding-1",
        case_id: "case-1",
        model_identity: "fixture-model",
        compiler: "fixture-compiler",
        compiler_version: "1",
        request_hash: "e".repeat(64),
        answer_question_id: "question-1",
        answer_option_id: "option-1",
        error_code: null,
        error_reason: null,
      },
    ],
    requests: [requestSource],
    created_at: "2026-10-11T00:00:00Z",
  };
  const previewBodies: ApiOperationBody<"previewRun">[] = [];
  const previewCall = vi.fn(async ({ body }: { body: ApiOperationBody<"previewRun"> }) => {
    previewBodies.push(body);
    return result(preview);
  });
  const startCalls: ApiOperationBody<"startRun">[] = [];
  const accepted: ApiOperationData<"startRun"> = {
    schema_version: 1,
    run_id: "run-1",
    mode: "fixture",
    operation_id: "operation-1",
    segment_id: "segment-1",
    replayed: true,
    progress_path: "/api/v1/projects/registration-1/runs/run-1",
  };
  let startCount = 0;
  const start = vi.fn(async ({ body }: { body: ApiOperationBody<"startRun"> }) => {
    startCalls.push(body);
    startCount += 1;
    if (startCount === 1) throw new Error("connection closed after dispatch");
    return { data: { ...accepted, operation_id: body.operation_id }, warnings: [] };
  });
  const gateway: WorkspaceGateway = {
    ...disconnectedWorkspace,
    execution: {
      ...disconnectedWorkspace.execution,
      runs: {
        ...disconnectedWorkspace.execution.runs,
        preview: previewCall,
        start,
      },
    },
    authoring: {
      ...disconnectedWorkspace.authoring,
      examples: {
        ...disconnectedWorkspace.authoring.examples,
        listCases: async () => result({
          schema_version: 1,
          dataset_etag: "a".repeat(64),
          items: [],
          next_cursor: null,
          total: "0",
        }),
      },
      providers: {
        ...disconnectedWorkspace.authoring.providers,
        list: async () => result({ schema_version: 1, items: [], next_cursor: null, total: "0" }),
      },
      fixtures: {
        ...disconnectedWorkspace.authoring.fixtures,
        list: async () => result({ schema_version: 1, items: [fixture], next_cursor: null, total: "1" }),
      },
      decisions: {
        ...disconnectedWorkspace.authoring.decisions,
        revisions: async () => result({ schema_version: 1, items: [], next_cursor: null, total: "0" }),
      },
    },
  };
  window.history.replaceState(null, "", "#/p/registration-1/d/decision-1");
  const navigation = new WorkspaceNavigation(window);
  const onClose = vi.fn();
  const onStarted = vi.fn();
  const user = userEvent.setup();
  const view = render(
    <RunReview
      project={project}
      decision={decision}
      gateway={gateway}
      navigation={navigation}
      onClose={onClose}
      onStarted={onStarted}
    />,
  );
  try {
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Review run" }).hasAttribute("disabled"),
      ).toBe(false);
    });
    const concurrency = screen.getByLabelText("Concurrency (1–64)");
    await user.clear(concurrency);
    await user.type(concurrency, "1");
    await user.click(await screen.findByRole("button", { name: "Review run" }));
    expect(await screen.findByRole("region", { name: "Reviewed run context" })).toBeTruthy();
    expect(previewCall).toHaveBeenCalledTimes(1);
    expect(previewBodies[0]?.request.settings?.concurrency).toBe(1);
    await user.click(screen.getByRole("button", { name: "Start reviewed run" }));
    expect(await screen.findByRole("button", { name: "Retry original start request" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Start reviewed run" }).hasAttribute("disabled"),
    ).toBe(true);
    expect(startCalls).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Retry original start request" }));
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith("run-1"));
    expect(startCalls).toHaveLength(2);
    expect(startCalls[1]).toEqual(startCalls[0]);
    expect(startCalls[0]?.operation_id).toBeTruthy();
  } finally {
    view.unmount();
    navigation.dispose();
  }
});
