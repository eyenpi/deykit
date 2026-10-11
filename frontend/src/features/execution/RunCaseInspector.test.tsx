import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import type { ApiOperationData } from "../../api/client";
import { disconnectedWorkspace } from "../../workspace/gateway";
import type { ExecutionGateway } from "../../workspace/gateway";
import { WorkspaceNavigation } from "../../workspace/navigation";
import { RunCaseInspector } from "./RunCaseInspector";

const exactInput = '{"large":9007199254740993,"fraction":1.2300}';
type ResultReadRequest = Parameters<
  ExecutionGateway["inspection"]["readResult"]
>[0];

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

const revision: ApiOperationData<"readDecisionRevision"> = {
  schema_version: 1,
  editor_source: "{}",
  revision: {
    etag: "revision-etag-1",
    record: {
      schema_version: 1,
      id: "revision-1",
      decision_id: "decision-1",
      created_at: "2026-10-11T00:00:00Z",
      content_hash: "revision-hash-1",
      definition: {
        schema_version: 1,
        input_kind: "json",
        input_schema_source: '{"type":"object"}',
        selected_fields: [],
        questions: [{ id: "question-1", instructions: "Choose", options: [] }],
      },
    },
  },
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
          source: {
            ...rowSource,
            input_source: includeInput ? exactInput : null,
          },
        });
      },
    },
  };
  window.history.replaceState(
    null,
    "",
    "#/p/registration-1/runs/run-inspector-1",
  );
  const navigation = new WorkspaceNavigation(window);
  const tree = render(
    <RunCaseInspector
      registrationId="registration-1"
      run={run}
      execution={execution}
      readRevision={async () => result(revision)}
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
    expect(reads[0]?.query).not.toHaveProperty("evaluation_id");
    expect(screen.queryByText(exactInput)).toBeNull();

    await user.click(screen.getByLabelText("Include input"));
    await waitFor(() => expect(reads).toHaveLength(2));
    expect(reads[1]?.query?.include_input).toBe("true");
    expect(reads[1]?.query).not.toHaveProperty("evaluation_id");
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

function resultPage(
  snapshot: string,
  source: ApiOperationData<"readResult">["source"],
  nextCursor: string | null,
): ApiOperationData<"listResults"> {
  return {
    schema_version: 1,
    run_id: run.run_id,
    evaluation_id: null,
    result_snapshot_id: snapshot,
    label_snapshot_id: `label-${snapshot}`,
    selected_count: "2",
    filtered_count: "2",
    status_counts: { valid: "2" },
    summary: {},
    items: [{ source }],
    next_cursor: nextCursor,
  };
}

function mountInspector(
  execution: ExecutionGateway,
  caseId?: string,
  evaluationId?: string,
  selectedRun: ApiOperationData<"readRun"> = run,
) {
  window.history.replaceState(
    null,
    "",
    "#/p/registration-1/runs/run-inspector-1",
  );
  const navigation = new WorkspaceNavigation(window);
  const tree = render(
    <RunCaseInspector
      registrationId="registration-1"
      run={selectedRun}
      execution={execution}
      readRevision={async () => result(revision)}
      navigation={navigation}
      evaluationId={evaluationId}
      caseId={caseId}
    />,
  );
  return { tree, navigation };
}

it("omits absent evaluation filters and preserves a selected evaluation", async () => {
  const evaluation: ApiOperationData<"readEvaluation"> = {
    schema_version: 1,
    evaluation_id: "evaluation-1",
    run_id: run.run_id,
    result_snapshot_id: "result-snapshot-1",
    label_snapshot_id: "label-result-snapshot-1",
    mode: "original",
    replayed: false,
    created_at: "2026-10-11T00:00:00Z",
    execution_operation_id: null,
    content_hash: "evaluation-hash-1",
    metrics: {},
    metrics_source: "{}",
  };
  const listQueries: unknown[] = [];
  const detailQueries: unknown[] = [];
  const execution: ExecutionGateway = {
    ...disconnectedWorkspace.execution,
    inspection: {
      ...disconnectedWorkspace.execution.inspection,
      listEvaluations: async () =>
        result({ items: [evaluation], next_cursor: null, total: "1" }),
      readEvaluation: async () => result(evaluation),
      listResults: async ({ query }) => {
        listQueries.push(query);
        return result({
          ...resultPage("result-snapshot-1", rowSource, null),
          evaluation_id: evaluation.evaluation_id,
          label_snapshot_id: evaluation.label_snapshot_id,
        });
      },
      readResult: async ({ query }) => {
        detailQueries.push(query);
        return result<ApiOperationData<"readResult">>({
          schema_version: 1,
          source: {
            ...rowSource,
            evaluation_id: evaluation.evaluation_id,
            label_snapshot_id: evaluation.label_snapshot_id,
          },
        });
      },
    },
  };
  const { tree, navigation } = mountInspector(
    execution,
    "case-1",
    evaluation.evaluation_id,
  );
  try {
    await waitFor(() => expect(listQueries).toHaveLength(1));
    await waitFor(() => expect(detailQueries).toHaveLength(1));
    expect(listQueries[0]).toMatchObject({
      evaluation_id: evaluation.evaluation_id,
    });
    expect(detailQueries[0]).toMatchObject({
      evaluation_id: evaluation.evaluation_id,
    });
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});

it("keeps an older result snapshot pinned until explicit refresh", async () => {
  const latestRun = { ...run, latest_result_snapshot_id: "result-snapshot-2" };
  let pageReads = 0;
  const execution: ExecutionGateway = {
    ...disconnectedWorkspace.execution,
    inspection: {
      ...disconnectedWorkspace.execution.inspection,
      listEvaluations: async () =>
        result({ items: [], next_cursor: null, total: "0" }),
      listResults: async () => {
        pageReads += 1;
        return result(
          resultPage(
            pageReads === 1 ? "result-snapshot-1" : "result-snapshot-2",
            rowSource,
            null,
          ),
        );
      },
    },
  };
  const { tree, navigation } = mountInspector(
    execution,
    undefined,
    undefined,
    latestRun,
  );
  const user = userEvent.setup();
  try {
    const publishedPair = screen.getByRole("status", {
      name: "Published result snapshot",
    });
    await waitFor(() =>
      expect(publishedPair).toHaveTextContent("result-snapshot-1"),
    );
    expect(
      screen.getByRole("status", { name: "Newer current result available" }),
    ).toHaveTextContent("result-snapshot-2");
    await user.click(
      screen.getByRole("button", { name: "Refresh frozen results" }),
    );
    await waitFor(() => expect(publishedPair).toHaveTextContent("result-snapshot-2"));
    expect(pageReads).toBe(2);
    expect(
      screen.queryByRole("status", { name: "Newer current result available" }),
    ).toBeNull();
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});

it("rejects a later result page from a different frozen snapshot", async () => {
  const otherRow: ApiOperationData<"readResult">["source"] = {
    ...rowSource,
    case_id: "case-2",
  };
  let pageReads = 0;
  const execution: ExecutionGateway = {
    ...disconnectedWorkspace.execution,
    inspection: {
      ...disconnectedWorkspace.execution.inspection,
      listEvaluations: async () =>
        result({ items: [], next_cursor: null, total: "0" }),
      listResults: async () => {
        pageReads += 1;
        return result(
          pageReads === 1
            ? resultPage("result-snapshot-1", rowSource, "next")
            : resultPage("result-snapshot-2", otherRow, null),
        );
      },
    },
  };
  const { tree, navigation } = mountInspector(execution);
  const user = userEvent.setup();
  try {
    expect(await screen.findByRole("button", { name: "case-1" })).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Load more results" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("button", { name: "case-1" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "case-2" })).toBeNull();
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});

it("rejects a case detail whose result and label snapshots differ from the first page", async () => {
  const execution: ExecutionGateway = {
    ...disconnectedWorkspace.execution,
    inspection: {
      ...disconnectedWorkspace.execution.inspection,
      listEvaluations: async () =>
        result({ items: [], next_cursor: null, total: "0" }),
      listResults: async () =>
        result(resultPage("result-snapshot-1", rowSource, null)),
      readResult: async () =>
        result<ApiOperationData<"readResult">>({
          schema_version: 1,
          source: {
            ...rowSource,
            result_snapshot_id: "result-snapshot-2",
            label_snapshot_id: "label-result-snapshot-2",
            input_source: exactInput,
          },
        }),
    },
  };
  const { tree, navigation } = mountInspector(execution, "case-1");
  try {
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText(exactInput)).toBeNull();
    expect(screen.getByRole("heading", { name: "case-1" })).toBeTruthy();
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});
