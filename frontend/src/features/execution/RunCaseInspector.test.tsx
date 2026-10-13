import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import type { ApiOperationArguments, ApiOperationData } from "../../api/client";
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

function context(
  resultSnapshotId: string,
  labelSnapshotId: string,
  evaluationId: string | null,
): ApiOperationData<"listResults">["context"] {
  return {
    run_id: run.run_id,
    evaluation_id: evaluationId,
    result_snapshot_id: resultSnapshotId,
    result_content_hash: "b".repeat(64),
    label_snapshot_id: labelSnapshotId,
    label_content_hash: "c".repeat(64),
    decision_id: run.decision_id,
    decision_revision_id: "revision-1",
    decision_definition_hash: "d".repeat(64),
    dataset_id: run.dataset_id,
    dataset_snapshot_id: "dataset-snapshot-1",
    dataset_content_hash: "e".repeat(64),
    evaluation_mode: "original",
    through_event_sequence: "1",
  };
}

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
          context: context("result-snapshot-1", "label-snapshot-1", null),
          assessment_counts: {
            all: "1",
            inspect: "0",
            incorrect: "0",
            unlabelled: "0",
          },
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
          case_input_hash: "f".repeat(64),
          context: context("result-snapshot-1", "label-snapshot-1", null),
          probabilities: [],
          probabilities_unavailable_reason: "probabilities_not_provided",
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
      debugging={disconnectedWorkspace.debugging}
      labelOperations={disconnectedWorkspace.authoring.examples}
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
    context: context(snapshot, `label-${snapshot}`, null),
    assessment_counts: {
      all: "2",
      inspect: "0",
      incorrect: "0",
      unlabelled: "0",
    },
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
      debugging={disconnectedWorkspace.debugging}
      labelOperations={disconnectedWorkspace.authoring.examples}
      readRevision={async () => result(revision)}
      navigation={navigation}
      evaluationId={evaluationId}
      caseId={caseId}
    />,
  );
  return { tree, navigation };
}

it("keeps the frozen pair while the service reports status-intersected global assessments", async () => {
  const queries: NonNullable<ApiOperationArguments<"listResults">["query"]>[] =
    [];
  const execution: ExecutionGateway = {
    ...disconnectedWorkspace.execution,
    inspection: {
      ...disconnectedWorkspace.execution.inspection,
      listEvaluations: async () =>
        result({ items: [], next_cursor: null, total: "0" }),
      listResults: async ({ query }) => {
        queries.push(query ?? {});
        const validOnly = query?.status === "valid";
        const statuses = Array.from({ length: 12 }, (_, index) =>
          index < 10
            ? "valid"
            : index === 10
              ? "input_invalid"
              : "response_error",
        );
        const items = statuses
          .map((status, index) => ({
            source: {
              ...rowSource,
              case_id: `fixture-case-${index + 1}`,
              status,
            },
          }))
          .filter((item) => !validOnly || item.source.status === "valid");
        return result<ApiOperationData<"listResults">>({
          ...resultPage("result-snapshot-1", rowSource, null),
          selected_count: "12",
          filtered_count: validOnly ? "10" : "12",
          status_counts: {
            valid: "10",
            input_invalid: "1",
            response_error: "1",
          },
          assessment_counts: validOnly
            ? { all: "10", inspect: "2", incorrect: "2", unlabelled: "2" }
            : { all: "12", inspect: "4", incorrect: "2", unlabelled: "2" },
          items,
        });
      },
    },
  };
  const { tree, navigation } = mountInspector(execution);
  const user = userEvent.setup();
  try {
    await screen.findByRole("status", { name: "Published result snapshot" });
    const counts = screen.getByLabelText("Global assessment counts");
    await waitFor(() => {
      expect(counts.textContent).toContain("All12");
      expect(counts.textContent).toContain("Needs inspection4");
      expect(counts.textContent).toContain("Incorrect2");
      expect(counts.textContent).toContain("Unlabelled2");
    });
    await user.selectOptions(screen.getByLabelText("Status"), "valid");
    await waitFor(() => expect(queries).toHaveLength(2));
    await waitFor(() => {
      const filteredCounts = screen.getByLabelText("Global assessment counts");
      expect(filteredCounts.textContent).toContain("All10");
      expect(filteredCounts.textContent).toContain("Needs inspection2");
      expect(filteredCounts.textContent).toContain("Incorrect2");
      expect(filteredCounts.textContent).toContain("Unlabelled2");
    });
    expect(queries[1]).toMatchObject({
      status: "valid",
      expected_result_snapshot_id: "result-snapshot-1",
      expected_label_snapshot_id: "label-result-snapshot-1",
    });
    expect(
      screen.getByRole("status", { name: "Published result snapshot" })
        .textContent,
    ).toContain(
      "Result snapshot result-snapshot-1; label snapshot label-result-snapshot-1.",
    );
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});

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
          context: context(
            evaluation.result_snapshot_id,
            evaluation.label_snapshot_id,
            evaluation.evaluation_id,
          ),
        });
      },
      readResult: async ({ query }) => {
        detailQueries.push(query);
        return result<ApiOperationData<"readResult">>({
          schema_version: 1,
          case_input_hash: "f".repeat(64),
          context: context(
            evaluation.result_snapshot_id,
            evaluation.label_snapshot_id,
            evaluation.evaluation_id,
          ),
          probabilities: [],
          probabilities_unavailable_reason: "probabilities_not_provided",
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
    const publishedPair = await screen.findByRole("status", {
      name: "Published result snapshot",
    });
    await waitFor(() =>
      expect(publishedPair.textContent).toContain("result-snapshot-1"),
    );
    expect(
      screen
        .getByRole("status", { name: "Newer current result available" })
        .textContent?.includes("result-snapshot-2"),
    ).toBe(true);
    await user.click(
      screen.getByRole("button", { name: "Refresh frozen results" }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("status", { name: "Published result snapshot" })
          .textContent,
      ).toContain("result-snapshot-2"),
    );
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
          case_input_hash: "f".repeat(64),
          context: context(
            "result-snapshot-1",
            "label-result-snapshot-1",
            null,
          ),
          probabilities: [],
          probabilities_unavailable_reason: "probabilities_not_provided",
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

it.each(["request", "response"] as const)(
  "reveals and clears %s independently of structured attempts",
  async (mode) => {
    const reads: ResultReadRequest[] = [];
    const requestSource = '{"large":9007199254740993,"fraction":1.2300}';
    const responseSource = '{"answer":"option-1"}';
    const execution: ExecutionGateway = {
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
            context: context("result-snapshot-1", "label-snapshot-1", null),
            assessment_counts: {
              all: "1",
              inspect: "0",
              incorrect: "0",
              unlabelled: "0",
            },
            selected_count: "1",
            filtered_count: "1",
            status_counts: { valid: "1" },
            summary: {},
            items: [{ source: rowSource }],
            next_cursor: null,
          }),
        readResult: async (args) => {
          reads.push(args);
          const request = args.query?.include_request === "true";
          const response = args.query?.include_response === "true";
          const attempts = args.query?.include_attempts === "true";
          return result<ApiOperationData<"readResult">>({
            schema_version: 1,
            case_input_hash: "f".repeat(64),
            context: context("result-snapshot-1", "label-snapshot-1", null),
            probabilities: [],
            probabilities_unavailable_reason: "probabilities_not_provided",
            source: {
              ...rowSource,
              attempts:
                request || response || attempts
                  ? [
                      {
                        attempt_id: "attempt-1",
                        number: "1",
                        kind: "fixture",
                        state: "completed",
                        request_body_hash: "a".repeat(64),
                        error_code: null,
                        error_reason: null,
                        ...(request
                          ? { request_body_source: requestSource }
                          : {}),
                        ...(response
                          ? { response_source: responseSource }
                          : {}),
                      },
                    ]
                  : [],
            },
          });
        },
      },
    };
    const { tree, navigation } = mountInspector(execution, "case-1");
    const user = userEvent.setup();
    const selectedSource = mode === "request" ? requestSource : responseSource;
    const otherSource = mode === "request" ? responseSource : requestSource;
    try {
      await waitFor(() => expect(reads).toHaveLength(1));
      expect(screen.queryByText(selectedSource)).toBeNull();
      await user.click(screen.getByLabelText(`Include ${mode}`));
      expect(await screen.findByText(selectedSource)).toBeTruthy();
      expect(screen.queryByText(otherSource)).toBeNull();
      expect(
        (screen.getByLabelText("Include attempts") as HTMLInputElement).checked,
      ).toBe(false);
      expect(reads.at(-1)?.query?.include_attempts).toBe("false");
      expect(
        screen.queryByRole("heading", {
          name: "Attempt 1 · fixture · completed",
        }),
      ).toBeNull();
      await user.click(screen.getByLabelText(`Include ${mode}`));
      await waitFor(() =>
        expect(screen.queryByText(selectedSource)).toBeNull(),
      );
      await user.click(screen.getByLabelText("Include attempts"));
      expect(
        await screen.findByRole("heading", {
          name: "Attempt 1 · fixture · completed",
        }),
      ).toBeTruthy();
      expect(screen.queryByText(requestSource)).toBeNull();
      expect(screen.queryByText(responseSource)).toBeNull();
    } finally {
      tree.unmount();
      navigation.dispose();
    }
  },
);
