import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { ApiOperationBody, ApiOperationData } from "../../../api/client";
import { disconnectedWorkspace } from "../../../workspace/gateway";
import type { ProjectOverview, WorkspaceGateway } from "../../../workspace/gateway";
import { WorkspaceNavigation } from "../../../workspace/navigation";
import { GroupReview } from "./GroupReview";

function response<T>(data: T) {
  return Promise.resolve({ data, warnings: [] });
}

const project: ProjectOverview = {
  id: "registration-1",
  name: "Fixture project",
  path: "/tmp/fixture-project",
  decisions: [{ id: "decision-1", name: "Choose an option" }],
  datasets: [{ id: "dataset-1", name: "Examples" }],
  warnings: [],
};

const preview = {
  schema_version: 1,
  kind: "choice_order",
  dry_run: true,
  algorithm: "seeded-v1",
  seed: "9007199254740993",
  independent_case_count: "1",
  initial_requests: "2",
  attempt_limit: "4",
  deadline_seconds: "600",
  review_context_hash: "a".repeat(64),
  members: [
    {
      schema_version: 1,
      identity: {
        schema_version: 1,
        run_id: null,
        option_order: ["option-a", "option-b"],
        requests: [{ case_id: "case-1", input_hash: "b".repeat(64), request_hash: "c".repeat(64), compiler: "fixture-compiler", compiler_version: "1", requested_model: "fixture-model", schema_version: 1 }],
      },
      preview: {
        schema_version: 1,
        decision_id: "decision-1",
        dataset_id: "dataset-1",
        mode: "fixture",
        fixture_set_id: "fixture-1",
        provider_id: "fixture-provider",
        development_case_count: "1",
        dry_run: true,
        invalid_cases: [],
        review_context_hash: "a".repeat(64),
        settings: { max_attempts: "100", concurrency: "2", timeout_seconds: "60", deadline_seconds: "600", max_retries_per_case: "1" },
        requested_model: "fixture-model",
        selected_case_ids: ["case-1"],
        initial_requests: "1",
      },
    },
    {
      schema_version: 1,
      identity: { schema_version: 1, run_id: null, option_order: ["option-b", "option-a"], requests: [] },
      preview: { schema_version: 1, decision_id: "decision-1", dataset_id: "dataset-1", mode: "fixture", fixture_set_id: "fixture-1", provider_id: "fixture-provider", development_case_count: "1", dry_run: true, invalid_cases: [], review_context_hash: "a".repeat(64), settings: { max_attempts: "100", concurrency: "2", timeout_seconds: "60", deadline_seconds: "600", max_retries_per_case: "1" }, requested_model: "fixture-model", selected_case_ids: ["case-1"], initial_requests: "1" },
    },
  ],
} as unknown as ApiOperationData<"previewChoiceOrder">;

it("keeps the reviewed seed and operation identity across an unknown group start retry", async () => {
  const fixture = {
    schema_version: 1,
    id: "fixture-1",
    name: "Authored fixture",
    dataset_id: "dataset-1",
    decision_id: "decision-1",
    model_identity: "fixture-model",
    content_hash: "d".repeat(64),
    binding_count: "1",
    bindings: [],
    requests: [],
    created_at: "2026-10-11T00:00:00Z",
  } as ApiOperationData<"listFixtureSets">["items"][number];
  const previewCall = vi.fn(async () => response(preview));
  const startBodies: ApiOperationBody<"startChoiceOrder">[] = [];
  let attempt = 0;
  const accepted = {
    schema_version: 1,
    kind: "choice_order",
    group_id: "group-1",
    member_run_ids: ["run-1", "run-2"],
    operation_id: "operation-1",
    mode: "fixture",
    replayed: true,
  } as ApiOperationData<"startChoiceOrder">;
  const start = vi.fn(async ({ body }: { body: ApiOperationBody<"startChoiceOrder"> }) => {
    startBodies.push(body);
    attempt += 1;
    if (attempt === 1) throw new Error("connection closed after dispatch");
    return response({ ...accepted, operation_id: body.operation_id });
  });
  const gateway = {
    ...disconnectedWorkspace,
    debugging: {
      ...disconnectedWorkspace.debugging,
      diagnostics: { ...disconnectedWorkspace.debugging.diagnostics, preview: previewCall, start },
    },
    authoring: {
      ...disconnectedWorkspace.authoring,
      examples: {
        ...disconnectedWorkspace.authoring.examples,
        listCases: async () => response({ schema_version: 1, dataset_etag: "e".repeat(64), items: [], next_cursor: null, total: "0" }),
      },
      providers: { ...disconnectedWorkspace.authoring.providers, list: async () => response({ schema_version: 1, items: [], next_cursor: null, total: "0" }) },
      fixtures: { ...disconnectedWorkspace.authoring.fixtures, list: async () => response({ schema_version: 1, items: [fixture], next_cursor: null, total: "1" }) },
      decisions: { ...disconnectedWorkspace.authoring.decisions, revisions: async () => response({ schema_version: 1, items: [], next_cursor: null, total: "0" }) },
    },
  } as unknown as WorkspaceGateway;
  const navigation = new WorkspaceNavigation(window);
  const onStarted = vi.fn();
  const view = render(<GroupReview project={project} decision={project.decisions[0]} gateway={gateway} navigation={navigation} onClose={vi.fn()} onStarted={onStarted} kind="diagnostic" />);

  await screen.findByText("Authored fixture");
  fireEvent.change(screen.getByLabelText("Fixture set"), { target: { value: "fixture-1" } });
  fireEvent.change(screen.getByLabelText(/Seed/), { target: { value: "9007199254740993" } });
  fireEvent.click(screen.getByRole("button", { name: "Review choice order" }));
  await screen.findByText("Reviewed group context");
  expect(screen.getByText("9007199254740993")).toBeTruthy();
  expect(screen.getByText("c".repeat(64))).toBeTruthy();

  const startButton = screen.getByRole("button", { name: "Start reviewed group" });
  fireEvent.click(startButton);
  fireEvent.click(startButton);
  await screen.findByText(/connection closed after dispatch/);
  expect(start).toHaveBeenCalledTimes(1);
  view.rerender(<GroupReview project={project} decision={{ id: "decision-2", name: "Different decision" }} gateway={gateway} navigation={navigation} onClose={vi.fn()} onStarted={onStarted} kind="diagnostic" />);
  expect(screen.getByRole("button", { name: "Retry original start request" })).toHaveProperty("disabled", true);
  view.rerender(<GroupReview project={project} decision={project.decisions[0]} gateway={gateway} navigation={navigation} onClose={vi.fn()} onStarted={onStarted} kind="diagnostic" />);
  fireEvent.click(screen.getByRole("button", { name: "Retry original start request" }));
  await screen.findByText(/Group accepted:/);
  expect(start).toHaveBeenCalledTimes(2);
  expect(startBodies[1]).toEqual(startBodies[0]);
  expect(startBodies[0].request.seed).toBe("9007199254740993");
  expect(onStarted).toHaveBeenCalledWith("group-1");
  navigation.dispose();
});
