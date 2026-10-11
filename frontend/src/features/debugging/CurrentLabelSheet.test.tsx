import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { ApiOperationData, ApiResult } from "../../api/client";
import { disconnectedWorkspace } from "../../workspace/gateway";
import type { ExampleAuthoringOperations } from "../../workspace/gateway";
import { WorkspaceNavigation } from "../../workspace/navigation";
import { CurrentLabelSheet } from "./CurrentLabelSheet";

vi.mock("../../components/Modal", () => ({
  Modal: ({ children, title }: { children: ReactNode; title: string }) => (
    <div role="dialog" aria-label={title}>
      {children}
    </div>
  ),
}));

type LabelView =
  ApiOperationData<"read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get">;
type LabelReceipt =
  ApiOperationData<"batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post">;

function labelReceipt(
  request: Parameters<
    typeof disconnectedWorkspace.authoring.examples.saveLabels
  >[0],
  labelId: string,
  replayed = false,
): ApiResult<LabelReceipt> {
  const edit = request.body.edits[0]!;
  return {
    data: {
      schema_version: 1,
      replayed,
      changes: [
        {
          schema_version: 1,
          id: `change-${labelId}`,
          operation_id: request.body.operation_id,
          action: edit.action,
          decision_id: request.decisionId,
          dataset_id: request.datasetId,
          case_id: edit.review.case_id,
          question_id: edit.review.question_id,
          created_at: "2026-10-11T00:00:00Z",
          label: {
            schema_version: 1,
            id: labelId,
            decision_id: request.decisionId,
            dataset_id: request.datasetId,
            case_id: edit.review.case_id,
            question_id: edit.review.question_id,
            input_hash: edit.review.input_hash,
            acceptable_option_ids: edit.acceptable_option_ids ?? [],
            provenance: "human",
            updated_at: "2026-10-11T00:00:00Z",
          },
        },
      ],
    },
    warnings: [],
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => {
    resolve = accept;
  });
  return { promise, resolve };
}

function currentReviewHash(hash: string) {
  return (_content: string, element: Element | null) =>
    element?.tagName === "P" &&
    element.textContent?.includes(`Current review input hash ${hash}`) === true;
}

function labelView(caseId: string, inputHash: string): LabelView {
  return {
    schema_version: 1,
    case: {
      schema_version: 1,
      id: caseId,
      dataset_id: "dataset-1",
      input_kind: "json",
      input_source: "{}",
    },
    definition: {
      schema_version: 1,
      input_kind: "json",
      input_schema_source: null,
      selected_fields: [],
      questions: [
        {
          id: "question-1",
          instructions: "Choose one",
          options: [{ id: "option-1", name: "Option one" }],
        },
      ],
    },
    label: null,
    missing_option_ids: [],
    reasons: [],
    review: {
      case_id: caseId,
      dataset_id: "dataset-1",
      decision_etag: "decision-etag",
      draft_etag: "draft-etag",
      decision_id: "decision-1",
      input_hash: inputHash,
      label_etag: null,
      question_id: "question-1",
    },
    status: "unlabelled",
  };
}

it("keeps delayed current-label reads inside their A-to-B-to-A rendered scope", async () => {
  window.history.replaceState(null, "", "#/p/registration-1/runs/run-1");
  const navigation = new WorkspaceNavigation(window);
  const pending: Array<ReturnType<typeof deferred<ApiResult<LabelView>>>> = [];
  const operations = {
    ...disconnectedWorkspace.authoring.examples,
    readLabel: () => {
      const request = deferred<ApiResult<LabelView>>();
      pending.push(request);
      return request.promise;
    },
  };
  const props = {
    registrationId: "registration-1",
    decisionId: "decision-1",
    datasetId: "dataset-1",
    frozenQuestionId: "question-1",
    frozenOptionIds: ["option-1"],
    frozenExpectedOptionIds: [],
    operations,
    navigation,
    onClose: () => undefined,
  };
  const tree = render(
    <CurrentLabelSheet {...props} caseId="case-A" frozenInputHash="hash-a1" />,
  );
  try {
    await waitFor(() => expect(pending).toHaveLength(1));
    tree.rerender(
      <CurrentLabelSheet {...props} caseId="case-B" frozenInputHash="hash-b" />,
    );
    await waitFor(() => expect(pending).toHaveLength(2));
    tree.rerender(
      <CurrentLabelSheet
        {...props}
        caseId="case-A"
        frozenInputHash="hash-a2"
      />,
    );
    await waitFor(() => expect(pending).toHaveLength(3));

    pending[0]?.resolve({ data: labelView("case-A", "hash-a1"), warnings: [] });
    pending[1]?.resolve({ data: labelView("case-B", "hash-b"), warnings: [] });
    await Promise.resolve();
    expect(screen.queryByText(currentReviewHash("hash-a1"))).toBeNull();
    expect(screen.queryByText(currentReviewHash("hash-b"))).toBeNull();

    pending[2]?.resolve({ data: labelView("case-A", "hash-a2"), warnings: [] });
    expect(await screen.findByText(currentReviewHash("hash-a2"))).toBeTruthy();
    expect(screen.queryByText(currentReviewHash("hash-a1"))).toBeNull();
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});

it("keeps a known label receipt and permits only a read-only refresh after the detail read fails", async () => {
  window.history.replaceState(null, "", "#/p/registration-1/runs/run-1");
  const navigation = new WorkspaceNavigation(window);
  const submitted: Parameters<
    typeof disconnectedWorkspace.authoring.examples.saveLabels
  >[0][] = [];
  const writeReceipt = deferred<ApiResult<LabelReceipt>>();
  let readsOnReplacement = 0;
  const originalOperations: ExampleAuthoringOperations = {
    ...disconnectedWorkspace.authoring.examples,
    readLabel: async () => {
      return { data: labelView("case-A", "frozen-input-hash"), warnings: [] };
    },
    saveLabels: async (request: (typeof submitted)[number]) => {
      submitted.push(request);
      return writeReceipt.promise;
    },
  };
  const replacementOperations: ExampleAuthoringOperations = {
    ...disconnectedWorkspace.authoring.examples,
    readLabel: async () => {
      readsOnReplacement += 1;
      if (readsOnReplacement === 2)
        throw new ApiError("read_unavailable", "label read unavailable", 503);
      return { data: labelView("case-A", "frozen-input-hash"), warnings: [] };
    },
    saveLabels: async () => {
      throw new Error(
        "replacement operation must not receive the retained save",
      );
    },
  };
  const tree = render(
    <CurrentLabelSheet
      registrationId="registration-1"
      decisionId="decision-1"
      datasetId="dataset-1"
      caseId="case-A"
      frozenInputHash="frozen-input-hash"
      frozenQuestionId="question-1"
      frozenOptionIds={["option-1"]}
      frozenExpectedOptionIds={[]}
      operations={originalOperations}
      navigation={navigation}
      onClose={() => undefined}
    />,
  );
  const user = userEvent.setup();
  try {
    await user.click(await screen.findByLabelText(/Option one/));
    await user.click(
      screen.getByRole("button", { name: "Save current label" }),
    );
    await waitFor(() => expect(submitted).toHaveLength(1));
    tree.rerender(
      <CurrentLabelSheet
        registrationId="registration-1"
        decisionId="decision-1"
        datasetId="dataset-1"
        caseId="case-A"
        frozenInputHash="frozen-input-hash"
        frozenQuestionId="question-1"
        frozenOptionIds={["option-1"]}
        frozenExpectedOptionIds={[]}
        operations={replacementOperations}
        navigation={navigation}
        onClose={() => undefined}
      />,
    );
    await waitFor(() => expect(readsOnReplacement).toBe(1));
    writeReceipt.resolve(labelReceipt(submitted[0]!, "label-1"));
    expect(await screen.findByText(/Label receipt recorded/)).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain(
        "label read unavailable",
      ),
    );
    expect(submitted).toHaveLength(1);
    expect(submitted[0]?.body.edits[0]?.review.input_hash).toBe(
      "frozen-input-hash",
    );
    expect(submitted[0]?.body.edits[0]?.acceptable_option_ids).toEqual([
      "option-1",
    ]);
    expect(readsOnReplacement).toBe(2);

    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByText(currentReviewHash("frozen-input-hash")),
    ).toBeTruthy();
    expect(readsOnReplacement).toBe(3);
    expect(submitted).toHaveLength(1);
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});

it("retries the captured label hash and operation port after the frozen scope is replaced", async () => {
  window.history.replaceState(null, "", "#/p/registration-1/runs/run-1");
  const navigation = new WorkspaceNavigation(window);
  const requests: Parameters<
    typeof disconnectedWorkspace.authoring.examples.saveLabels
  >[0][] = [];
  let saves = 0;
  let replacementSaves = 0;
  const originalOperations: ExampleAuthoringOperations = {
    ...disconnectedWorkspace.authoring.examples,
    readLabel: async () => ({
      data: labelView("case-A", "frozen-hash-A"),
      warnings: [],
    }),
    saveLabels: async (request: (typeof requests)[number]) => {
      requests.push(request);
      saves += 1;
      if (saves === 1) throw new Error("reply lost");
      return labelReceipt(request, "label-A", true);
    },
  };
  const replacementOperations: ExampleAuthoringOperations = {
    ...disconnectedWorkspace.authoring.examples,
    readLabel: async () => ({
      data: labelView("case-A", "frozen-hash-B"),
      warnings: [],
    }),
    saveLabels: async () => {
      replacementSaves += 1;
      throw new Error(
        "replacement label port must not receive the retained save",
      );
    },
  };
  const baseProps = {
    registrationId: "registration-1",
    decisionId: "decision-1",
    datasetId: "dataset-1",
    frozenQuestionId: "question-1",
    frozenOptionIds: ["option-1"],
    frozenExpectedOptionIds: [],
    navigation,
    onClose: () => undefined,
  };
  const tree = render(
    <CurrentLabelSheet
      {...baseProps}
      caseId="case-A"
      frozenInputHash="frozen-hash-A"
      operations={originalOperations}
    />,
  );
  const user = userEvent.setup();
  try {
    await user.click(await screen.findByLabelText(/Option one/));
    await user.click(
      screen.getByRole("button", { name: "Save current label" }),
    );
    expect(
      await screen.findByRole("button", {
        name: "Retry original unchanged label save",
      }),
    ).toBeTruthy();
    expect(requests).toHaveLength(1);
    const original = requests[0]!;
    expect(original.body.edits[0]?.review.input_hash).toBe("frozen-hash-A");

    tree.rerender(
      <CurrentLabelSheet
        {...baseProps}
        caseId="case-A"
        frozenInputHash="frozen-hash-B"
        operations={replacementOperations}
      />,
    );
    expect(
      await screen.findByText(currentReviewHash("frozen-hash-B")),
    ).toBeTruthy();
    await user.click(
      screen.getByRole("button", {
        name: "Retry original unchanged label save",
      }),
    );
    expect(
      await screen.findByText(currentReviewHash("frozen-hash-B")),
    ).toBeTruthy();
    expect(requests).toHaveLength(2);
    const replayed = requests[1]!;
    expect(replayed.registrationId).toBe(original.registrationId);
    expect(replayed.decisionId).toBe(original.decisionId);
    expect(replayed.datasetId).toBe(original.datasetId);
    expect(replayed.body).toEqual(original.body);
    expect(replayed.body.edits[0]?.review.case_id).toBe(
      original.body.edits[0]?.review.case_id,
    );
    expect(replayed.body.operation_id).toBe(original.body.operation_id);
    expect(replayed.body.edits[0]?.review).toEqual(
      original.body.edits[0]?.review,
    );
    expect(replayed.body.edits[0]?.review.decision_etag).toBe(
      original.body.edits[0]?.review.decision_etag,
    );
    expect(replayed.body.edits[0]?.review.draft_etag).toBe(
      original.body.edits[0]?.review.draft_etag,
    );
    expect(replayed.body.edits[0]?.review.label_etag).toBe(
      original.body.edits[0]?.review.label_etag,
    );
    expect(replayed.body.edits[0]?.review.input_hash).toBe("frozen-hash-A");
    expect(saves).toBe(2);
    expect(replacementSaves).toBe(0);
  } finally {
    tree.unmount();
    navigation.dispose();
  }
});
