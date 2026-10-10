import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { ApiOperationData, ApiResult } from "../../api/client";
import { disconnectedWorkspace } from "../../workspace/gateway";
import type { DecisionAuthoringOperations } from "../../workspace/gateway";
import { WorkspaceNavigation } from "../../workspace/navigation";
import { DecisionPage } from "./DecisionPage";

type DecisionRead = ApiOperationData<"readDecision">;
type EditorProjection = ApiOperationData<"projectDecisionEditor">;
type TransformReview = ApiOperationData<"transformDecisionEditor">;
type RevisionReceipt = ApiOperationData<"saveDecisionRevision">;
type DraftReceipt = ApiOperationData<"updateDecisionDraft">;

const registrationId = "registration-1";
const decisionId = "decision-1";
const source0 =
  '{"instructions":"Start","exact":9007199254740993,"fraction":0.1234567890123456789}';
const source1 =
  '{"instructions":"First represented","exact":9007199254740993,"fraction":0.1234567890123456789}';
const source2 =
  '{"instructions":"Second queued","exact":9007199254740993,"fraction":0.1234567890123456789}';

function apiResult<T>(data: T): ApiResult<T> {
  return { data, warnings: [] };
}

function decisionRead(
  editorSource: string,
  draftEtag: string,
  options: {
    decisionId?: string;
    latestRevisionId?: string;
    baseRevisionId?: string;
  } = {},
): DecisionRead {
  return {
    schema_version: 1,
    decision: {
      etag: "decision-etag-1",
      record: {
        schema_version: 1,
        id: options.decisionId ?? decisionId,
        name: "Question",
        archived: false,
        latest_revision_id: options.latestRevisionId ?? null,
      },
    },
    draft: {
      etag: draftEtag,
      record: {
        schema_version: 1,
        decision_id: options.decisionId ?? decisionId,
        editor_source: editorSource,
        updated_at: "2026-10-10T00:00:00Z",
        base_revision_id: options.baseRevisionId ?? null,
      },
    },
  };
}

function editorForm(instructions: string) {
  return {
    input_kind: "json",
    input_schema_source: '{"type":"object"}',
    instructions,
    options: [
      { id: "option-a", name: "Option A", description: null },
      { id: "option-b", name: "Option B", description: null },
    ],
    question_id: "question-1",
    selected_fields: [],
  } as const;
}

function projection(
  editorSource: string,
  instructions: string,
): EditorProjection {
  return {
    schema_version: 1,
    editor_source: editorSource,
    form: editorForm(instructions),
    form_unavailable_reason: null,
    source_hash: "source-hash",
    validation_advice: [],
  };
}

function transformReview(
  editorSource: string,
  instructions: string,
): TransformReview {
  return {
    schema_version: 1,
    incompatible_references: null,
    transform: {
      schema_version: 1,
      editor_source: editorSource,
      original_source_hash: "original-hash",
      projection: projection(editorSource, instructions),
      source_hash: "source-hash",
      validation_advice: [],
    },
  };
}

function draftReceipt(
  editorSource: string,
  etag: string,
  targetDecisionId = decisionId,
): DraftReceipt {
  return {
    etag,
    record: {
      schema_version: 1,
      decision_id: targetDecisionId,
      editor_source: editorSource,
      updated_at: "2026-10-10T00:00:01Z",
      base_revision_id: null,
    },
  };
}

function revisionReceipt(
  editorSource: string,
  targetDecisionId = decisionId,
): RevisionReceipt {
  return {
    schema_version: 1,
    editor_source: editorSource,
    revision: {
      etag: "revision-etag-1",
      record: {
        schema_version: 1,
        id: "revision-1",
        decision_id: targetDecisionId,
        created_at: "2026-10-10T00:00:02Z",
        content_hash: "revision-hash",
        definition: {
          schema_version: 1,
          input_kind: "json",
          input_schema_source: '{"type":"object"}',
          selected_fields: [],
          questions: [
            {
              id: "question-1",
              instructions: "Second queued",
              options: [
                { id: "option-a", name: "Option A", description: null },
                { id: "option-b", name: "Option B", description: null },
              ],
            },
          ],
        },
      },
    },
  };
}

function mountDecision(overrides: Partial<DecisionAuthoringOperations> = {}) {
  const base = {
    ...disconnectedWorkspace.authoring.decisions,
    read: async ({ decisionId: targetDecisionId }) =>
      apiResult(
        decisionRead(source0, "draft-0", { decisionId: targetDecisionId }),
      ),
    projectEditor: async ({ body }) =>
      apiResult(projection(body.editor_source, "Start")),
    updateDraft: async ({ body }) =>
      apiResult(draftReceipt(body.editor_source, "draft-next")),
    transformEditor: async () =>
      apiResult(transformReview(source1, "First represented")),
    saveRevision: async () => apiResult(revisionReceipt(source2)),
  } satisfies DecisionAuthoringOperations;
  const operations = { ...base, ...overrides };
  const navigation = new WorkspaceNavigation(window);
  const page = (targetDecisionId: string) => (
    <DecisionPage
      registrationId={registrationId}
      decisionId={targetDecisionId}
      operations={operations}
      navigation={navigation}
      onDecisionRenamed={() => undefined}
      onHistory={() => undefined}
      onExamples={() => undefined}
      onArchiveChanged={() => undefined}
    />
  );
  const mounted = render(page(decisionId));
  return {
    operations,
    rerenderDecision: (targetDecisionId: string) =>
      mounted.rerender(page(targetDecisionId)),
    unmount: mounted.unmount,
  };
}

async function editQuestion(value: string) {
  const question = screen.getByRole("textbox", { name: "Question" });
  fireEvent.focus(question);
  fireEvent.change(question, { target: { value } });
  fireEvent.blur(question);
}

function expectTextboxValue(name: string, expected: string) {
  const textbox = screen.getByRole("textbox", { name });
  if (
    !(textbox instanceof HTMLInputElement) &&
    !(textbox instanceof HTMLTextAreaElement)
  )
    throw new Error(`Expected ${name} to be an input or textarea.`);
  expect(textbox.value).toBe(expected);
}

async function advanceTransformDelay() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(500);
  });
}

afterEach(() => vi.useRealTimers());

it("flushes the represented draft before transforming and saving a version", async () => {
  let readCount = 0;
  let updateCount = 0;
  let releasePriorDraft!: (result: ApiResult<DraftReceipt>) => void;
  const priorDraftAck = new Promise<ApiResult<DraftReceipt>>((resolve) => {
    releasePriorDraft = resolve;
  });
  const transformBodies: Array<
    Parameters<DecisionAuthoringOperations["transformEditor"]>[0]["body"]
  > = [];
  const updateBodies: Array<
    Parameters<DecisionAuthoringOperations["updateDraft"]>[0]["body"]
  > = [];
  const revisionBodies: Array<
    Parameters<DecisionAuthoringOperations["saveRevision"]>[0]["body"]
  > = [];
  mountDecision({
    read: async () => {
      readCount += 1;
      if (readCount === 1) return apiResult(decisionRead(source0, "draft-0"));
      if (readCount === 2) return apiResult(decisionRead(source2, "draft-2"));
      return apiResult(
        decisionRead(source2, "draft-3", {
          latestRevisionId: "revision-1",
          baseRevisionId: "revision-1",
        }),
      );
    },
    updateDraft: async ({ body }) => {
      updateBodies.push(body);
      updateCount += 1;
      if (updateCount === 1) return priorDraftAck;
      return apiResult(draftReceipt(body.editor_source, "draft-2"));
    },
    transformEditor: async ({ body }) => {
      transformBodies.push(body);
      return apiResult(
        transformBodies.length === 1
          ? transformReview(source1, "First represented")
          : transformReview(source2, "Second queued"),
      );
    },
    saveRevision: async ({ body }) => {
      revisionBodies.push(body);
      return apiResult(revisionReceipt(source2));
    },
  });

  await screen.findByRole("textbox", { name: "Question" });
  vi.useFakeTimers();
  await editQuestion("First represented");
  await act(async () => {
    await vi.advanceTimersByTimeAsync(500);
  });
  expect(transformBodies).toHaveLength(1);
  expect(transformBodies[0]?.editor_source).toBe(source0);
  expect(updateBodies).toHaveLength(0);

  await editQuestion("Second queued");
  fireEvent.click(screen.getByRole("button", { name: "Save version" }));
  await waitFor(() => expect(updateBodies).toHaveLength(1));
  expect(updateBodies[0]?.editor_source).toBe(source1);
  expect(updateBodies[0]?.editor_source).toContain("9007199254740993");
  expect(updateBodies[0]?.editor_source).toContain("0.1234567890123456789");
  expect(transformBodies).toHaveLength(1);
  expect(revisionBodies).toHaveLength(0);
  expectTextboxValue("Question", "Second queued");

  await act(async () => {
    releasePriorDraft(apiResult(draftReceipt(source1, "draft-1")));
  });
  await waitFor(() => expect(revisionBodies).toHaveLength(1));
  expect(transformBodies).toHaveLength(2);
  expect(transformBodies[1]).toMatchObject({
    editor_source: source1,
    expected_draft_etag: "draft-1",
    edit: { kind: "set_instructions", value: "Second queued" },
  });
  expect(
    updateBodies.map((body) => [body.editor_source, body.expected_etag]),
  ).toEqual([
    [source1, "draft-0"],
    [source2, "draft-1"],
  ]);
  expect(revisionBodies[0]?.expected_draft_etag).toBe("draft-2");
  expect(revisionBodies).toHaveLength(1);
});

it("pauses queued transforms while the represented draft acknowledgement overlaps composition", async () => {
  let releasePriorDraft!: (result: ApiResult<DraftReceipt>) => void;
  const priorDraftAck = new Promise<ApiResult<DraftReceipt>>((resolve) => {
    releasePriorDraft = resolve;
  });
  let updateCount = 0;
  const transformBodies: Array<
    Parameters<DecisionAuthoringOperations["transformEditor"]>[0]["body"]
  > = [];
  const revisionBodies: Array<
    Parameters<DecisionAuthoringOperations["saveRevision"]>[0]["body"]
  > = [];
  mountDecision({
    updateDraft: async ({ body }) => {
      updateCount += 1;
      if (updateCount === 1) return priorDraftAck;
      return apiResult(
        draftReceipt(body.editor_source, `draft-${updateCount}`),
      );
    },
    transformEditor: async ({ body }) => {
      transformBodies.push(body);
      const next = transformBodies.length === 1 ? source1 : source2;
      const instructions =
        transformBodies.length === 1 ? "First represented" : "Second queued";
      return apiResult(transformReview(next, instructions));
    },
    saveRevision: async ({ body }) => {
      revisionBodies.push(body);
      return apiResult(revisionReceipt(source2));
    },
  });

  await screen.findByRole("textbox", { name: "Question" });
  vi.useFakeTimers();
  await editQuestion("First represented");
  await advanceTransformDelay();
  await editQuestion("Second queued");
  fireEvent.click(screen.getByRole("button", { name: "Save version" }));
  expect(updateCount).toBe(1);

  const schema = screen.getByRole("textbox", {
    name: "Advanced JSON Schema source",
  });
  fireEvent.focus(schema);
  fireEvent.compositionStart(schema);
  fireEvent.change(schema, { target: { value: '{"type":"string"}' } });
  await act(async () => {
    releasePriorDraft(apiResult(draftReceipt(source1, "draft-1")));
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(transformBodies).toHaveLength(1);
  expect(revisionBodies).toHaveLength(0);
  expectTextboxValue("Question", "Second queued");

  fireEvent.compositionEnd(schema);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(500);
  });
  expect(transformBodies).toHaveLength(3);
  expect(transformBodies[1]?.editor_source).toBe(source1);
  expect(transformBodies[2]?.editor_source).toBe(source2);
  expect(transformBodies[2]?.edit).toMatchObject({
    kind: "replace_schema",
    input_schema_source: '{"type":"string"}',
  });
  expect(revisionBodies).toHaveLength(0);
});

it.each([
  { code: "etag_conflict", status: 409, state: "conflict" },
  { code: "service_unavailable", status: 503, state: "unknown" },
])(
  "retains the queued edit without transforming or saving a version after a draft $state",
  async ({ code, status, state }) => {
    const updateDraft = vi.fn(async () => {
      throw new ApiError(code, "Draft save did not complete.", status);
    });
    const transformEditor = vi.fn(async () =>
      apiResult(transformReview(source1, "First represented")),
    );
    const saveRevision = vi.fn(async () => apiResult(revisionReceipt(source2)));
    mountDecision({ updateDraft, transformEditor, saveRevision });

    await screen.findByRole("textbox", { name: "Question" });
    vi.useFakeTimers();
    await editQuestion("First represented");
    await advanceTransformDelay();
    await editQuestion("Second queued");
    fireEvent.click(screen.getByRole("button", { name: "Save version" }));

    await screen.findByRole("button", { name: "Retry pending edits" });
    expect(transformEditor).toHaveBeenCalledTimes(1);
    expect(updateDraft).toHaveBeenCalledTimes(1);
    expect(saveRevision).not.toHaveBeenCalled();
    expectTextboxValue("Question", "Second queued");
    expect(
      screen.queryByRole("button", {
        name:
          state === "unknown"
            ? "Retry unchanged save"
            : "Review current and reapply my source",
      }),
    ).not.toBeNull();
  },
);

it("drops an obsolete queued form edit when exact raw source replaces its sequence during draft flush", async () => {
  let releasePriorDraft!: (result: ApiResult<DraftReceipt>) => void;
  const priorDraftAck = new Promise<ApiResult<DraftReceipt>>((resolve) => {
    releasePriorDraft = resolve;
  });
  const updateBodies: Array<
    Parameters<DecisionAuthoringOperations["updateDraft"]>[0]["body"]
  > = [];
  const transformBodies: Array<
    Parameters<DecisionAuthoringOperations["transformEditor"]>[0]["body"]
  > = [];
  const rawSource =
    '{ "raw": 9007199254740993, "fraction": 0.1234567890123456789 }';
  let updateCount = 0;
  mountDecision({
    updateDraft: async ({ body }) => {
      updateBodies.push(body);
      updateCount += 1;
      if (updateCount === 1) return priorDraftAck;
      return apiResult(
        draftReceipt(body.editor_source, `draft-${updateCount}`),
      );
    },
    transformEditor: async ({ body }) => {
      transformBodies.push(body);
      return apiResult(transformReview(source1, "First represented"));
    },
  });

  await screen.findByRole("textbox", { name: "Question" });
  vi.useFakeTimers();
  await editQuestion("First represented");
  await advanceTransformDelay();
  await editQuestion("Second queued");
  fireEvent.click(screen.getByRole("button", { name: "Save version" }));
  expect(updateBodies).toHaveLength(1);

  fireEvent.click(screen.getByText("Advanced editor source"));
  fireEvent.change(screen.getByRole("textbox", { name: "Decision source" }), {
    target: { value: rawSource },
  });
  await act(async () => {
    releasePriorDraft(apiResult(draftReceipt(source1, "draft-1")));
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(transformBodies).toHaveLength(1);
  expect(updateBodies.map((body) => body.editor_source)).toEqual([
    source1,
    rawSource,
  ]);
  expectTextboxValue("Decision source", rawSource);
  expect(transformBodies).toHaveLength(1);
});

it("does not continue an old drain after the same page is reused for another decision", async () => {
  let releasePriorDraft!: (result: ApiResult<DraftReceipt>) => void;
  const priorDraftAck = new Promise<ApiResult<DraftReceipt>>((resolve) => {
    releasePriorDraft = resolve;
  });
  const updateRequests: Array<
    Parameters<DecisionAuthoringOperations["updateDraft"]>[0]
  > = [];
  const transformEditor = vi.fn(async () =>
    apiResult(transformReview(source1, "First represented")),
  );
  const saveRevision = vi.fn(async () => apiResult(revisionReceipt(source2)));
  const mounted = mountDecision({
    read: async ({ decisionId: targetDecisionId }) =>
      apiResult(
        decisionRead(source0, `draft-${targetDecisionId}`, {
          decisionId: targetDecisionId,
        }),
      ),
    updateDraft: async (request) => {
      updateRequests.push(request);
      if (updateRequests.length === 1) return priorDraftAck;
      return apiResult(
        draftReceipt(
          request.body.editor_source,
          "draft-next",
          request.decisionId,
        ),
      );
    },
    transformEditor,
    saveRevision,
  });

  await screen.findByRole("textbox", { name: "Question" });
  vi.useFakeTimers();
  await editQuestion("First represented");
  await advanceTransformDelay();
  await editQuestion("Second queued");
  fireEvent.click(screen.getByRole("button", { name: "Save version" }));
  expect(updateRequests).toHaveLength(1);

  const rawSource = '{ "new-page-only": 9007199254740993 }';
  fireEvent.click(screen.getByText("Advanced editor source"));
  fireEvent.change(screen.getByRole("textbox", { name: "Decision source" }), {
    target: { value: rawSource },
  });
  expectTextboxValue("Decision source", rawSource);

  mounted.rerenderDecision("decision-2");
  await waitFor(() => expectTextboxValue("Question", "Start"));
  await act(async () => {
    releasePriorDraft(apiResult(draftReceipt(source1, "draft-old-ack")));
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(transformEditor).toHaveBeenCalledTimes(1);
  expect(saveRevision).not.toHaveBeenCalled();
  expectTextboxValue("Question", "Start");
  expect(updateRequests).toHaveLength(1);

  await editQuestion("New page edit");
  await advanceTransformDelay();
  await waitFor(() => expect(updateRequests).toHaveLength(2));
  expect(updateRequests[1]?.decisionId).toBe("decision-2");
  expect(updateRequests[1]?.body).toMatchObject({
    editor_source: source1,
    expected_etag: "draft-decision-2",
  });
  expect(transformEditor).toHaveBeenCalledTimes(2);
  expect(saveRevision).not.toHaveBeenCalled();
});
