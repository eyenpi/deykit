import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import type { ApiOperationData } from "../../api/client";
import { disconnectedWorkspace } from "../../workspace/gateway";
import type { ExecutionGateway } from "../../workspace/gateway";
import { WorkspaceNavigation } from "../../workspace/navigation";
import { RunCaseInspector } from "./RunCaseInspector";

const exactInput = '{"large":9007199254740993,"fraction":1.2300}';
type ResultReadRequest = Parameters<ExecutionGateway["inspection"]["readResult"]>[0];

const run: ApiOperationData<"readRun"> = {
  schema_version: 1,
  run_id: "run-inspector-1",
  mode: "fixture",
  state: "completed",
  execution_active: false,
  decision_id: "decision-1",
  dataset_id: "dataset-1",
  requested_model: "authored-model",
  execution_group_id: null,
  group_attempts_remaining: null,
  attempts_used: "1",
  attempt_limit: "2",
  attempts_remaining: "1",
  replayed: false,
  reason: null,
  result_snapshot_ids: ["result-snapshot-1"],
  latest_result_snapshot_id: "result-snapshot-1",
  segment_ids: ["segment-1"],
  segments: [],
  attempts: [],
  cases: [
    {
      case_id: "case-1",
      status: "completed",
      attempt_id: "attempt-1",
      error: null,
    },
  ],
  settings: {
    max_attempts: "2",
    concurrency: "1",
    timeout_seconds: "30",
    deadline_seconds: "60",
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

const rowSource: ApiOperationData<"readResult">["source"] = {
  run_id: run.run_id,
  result_snapshot_id: "result-snapshot-1",
  label_snapshot_id: "label-snapshot-1",
  evaluation_id: null,
  case_id: "case-1",
  split: "development",
  tags: ["authored"],
  status: "valid",
  answer_option_id: "option-1",
  expected_option_ids: ["option-1"],
  set_correct: true,
  exclusion_reasons: [],
  annotation_count: "0",
  question_id: "question-1",
  answer: {
    option_id: "option-1",
    question_id: "question-1",
    probabilities_source: null,
    native_confidence_source: null,
    native_confidence_semantics: null,
    reported_model: "authored-model",
  },
  legacy_question_ids: [],
  legacy_expected_option_ids: [],
  legacy_exclusion_reasons: [],
  label_provenance: "authored",
  annotations: [],
  attempts: [],
  input_source: null,
};

function result<T>(data: T) {
  return Promise.resolve({ data, warnings: [] });
}

it("reveals exact saved input only after opt-in and clears it when hidden", async () => {
  const reads: ResultReadRequest[] = [];
  const execution = {
    ...disconnectedWorkspace.execution,
    inspection: {
      ...disconnectedWorkspace.execution.inspection,
      listEvaluations: async () =>
        result({ items: [], next_cursor: null, total: "0" }),
      listResults: async () =>
        result<ApiOperationData<"listResults">>({
          schema_version: 1,
          run_id: run.run_id,
          evaluation_id: null,
          result_snapshot_id: "result-snapshot-1",
          label_snapshot_id: "label-snapshot-1",
          selected_count: "1",
          filtered_count: "1",
          status_counts: { valid: "1" },
          summary: {},
          items: [{ source: rowSource }],
          next_cursor: null,
        }),
      readResult: async (args: ResultReadRequest) => {
        reads.push(args);
        const includeInput = args.query?.include_input === "true";
        return result<ApiOperationData<"readResult">>({
          schema_version: 1,
          source: { ...rowSource, input_source: includeInput ? exactInput : null },
        });
      },
    },
  };
  window.history.replaceState(null, "", "#/p/registration-1/runs/run-inspector-1");
  const navigation = new WorkspaceNavigation(window);
  const tree = render(
    <RunCaseInspector
      registrationId="registration-1"
      run={run}
      execution={execution}
      readRevision={disconnectedWorkspace.authoring.decisions.revision}
      navigation={navigation}
      caseId="case-1"
    />,
  );
  const user = userEvent.setup();
  try {
    await waitFor(() => expect(reads).toHaveLength(1));
    expect(reads[0]?.query).toMatchObject({
      include_input: "false",
      include_request: "false",
      include_response: "false",
      include_attempts: "false",
    });
    expect(screen.queryByText(exactInput)).toBeNull();

    await user.click(screen.getByLabelText("Include input"));
    await waitFor(() => expect(reads).toHaveLength(2));
    expect(reads[1]?.query?.include_input).toBe("true");
    expect(await screen.findByText(exactInput)).toBeTruthy();

    await user.click(screen.getByLabelText("Include input"));
    await waitFor(() => expect(reads).toHaveLength(3));
    expect(reads[2]?.query?.include_input).toBe("false");
    await waitFor(() => expect(screen.queryByText(exactInput)).toBeNull());
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});
