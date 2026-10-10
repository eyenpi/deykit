import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { useEffect, useState } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { ApiOperationBody, ApiOperationData } from "../../api/client";
import { disconnectedWorkspace } from "../../workspace/gateway";
import type {
  DatasetAuthoringOperations,
  ExampleAuthoringOperations,
  ProjectOverview,
} from "../../workspace/gateway";
import { WorkspaceNavigation } from "../../workspace/navigation";
import type { CaseRead, DatasetRead, LabelView } from "./examples-admission";
import { ExamplesPage } from "./ExamplesPage";

type CasePage =
  ApiOperationData<"list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get">;
type CaseEditReceipt =
  ApiOperationData<"edit_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__put">;
type LabelBatchBody =
  ApiOperationBody<"batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post">;
type LabelBatchReceipt =
  ApiOperationData<"batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post">;

const sourceA = '{"case":"old"}';
const sourceB = '{"case":"target","n":9007199254740993}';
const decision = { id: "decision-1", name: "Decision" };
const project: ProjectOverview = {
  id: "registration-1",
  name: "Project",
  path: "/tmp/examples-admission",
  decisions: [decision],
  datasets: [{ id: "dataset-1", name: "Examples" }],
  warnings: [],
};

function caseRead(caseId: string, inputSource: string): CaseRead {
  return {
    schema_version: 1,
    dataset_etag: "dataset-etag-1",
    case: {
      schema_version: 1,
      etag: `etag-${caseId}`,
      record: {
        schema_version: 1,
        id: caseId,
        dataset_id: "dataset-1",
        input_kind: "json",
        input_source: inputSource,
      },
    },
  };
}

const caseA = caseRead("case-a", sourceA);
const caseB = caseRead("case-b", sourceB);
const dataset: DatasetRead = {
  schema_version: 1,
  etag: "dataset-etag-1",
  record: {
    schema_version: 1,
    id: "dataset-1",
    name: "Examples",
    created_at: "2026-01-01T00:00:00Z",
  },
};

function labelView(read: CaseRead): LabelView {
  return {
    schema_version: 1,
    status: "unlabelled",
    reasons: [],
    missing_option_ids: [],
    case: read.case.record,
    definition: {
      schema_version: 1,
      input_kind: "json",
      questions: [
        {
          id: "question-1",
          instructions: "Choose one",
          options: [
            { id: "option-a", name: "Option A" },
            { id: "option-b", name: "Option B" },
          ],
        },
      ],
    },
    label: null,
    review: {
      case_id: read.case.record.id,
      dataset_id: "dataset-1",
      decision_id: decision.id,
      question_id: "question-1",
      decision_etag: "decision-etag-1",
      draft_etag: "draft-etag-1",
      input_hash: `hash-${read.case.record.id}`,
      label_etag: null,
    },
  };
}

function labelReceipt(body: LabelBatchBody): LabelBatchReceipt {
  const edit = body.edits[0];
  if (!edit) throw new Error("Expected one staged label edit.");
  const label: NonNullable<LabelView["label"]> = {
    schema_version: 1,
    id: "label-a",
    case_id: "case-a",
    dataset_id: "dataset-1",
    decision_id: decision.id,
    question_id: "question-1",
    input_hash: "hash-case-a",
    acceptable_option_ids: edit.acceptable_option_ids ?? [],
    provenance: "human",
    updated_at: "2026-01-01T00:00:00Z",
    status: "active",
  };
  return {
    schema_version: 1,
    replayed: false,
    changes: [
      {
        schema_version: 1,
        id: "change-a",
        operation_id: body.operation_id,
        action: edit.action,
        created_at: "2026-01-01T00:00:00Z",
        case_id: "case-a",
        dataset_id: "dataset-1",
        decision_id: decision.id,
        question_id: "question-1",
        label: edit.action === "clear" ? null : label,
      },
    ],
  };
}

const listCases: CasePage = {
  schema_version: 1,
  dataset_etag: dataset.etag,
  items: [caseA.case, caseB.case],
  total: "2",
  next_cursor: null,
};
const emptyLabelPage: ApiOperationData<"list_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_get"> =
  {
    schema_version: 1,
    items: [],
    total: "0",
    next_cursor: null,
  };

let navigation: WorkspaceNavigation | undefined;
afterEach(() => {
  navigation?.dispose();
  navigation = undefined;
  window.history.replaceState(null, "", "#/");
  vi.restoreAllMocks();
});

function mountExamples(
  overrides: Partial<ExampleAuthoringOperations> = {},
  datasetOverrides: Partial<DatasetAuthoringOperations> = {},
  initialCaseId: string | null = "case-a",
  followNavigation = false,
) {
  window.history.replaceState(
    null,
    "",
    `#/p/registration-1/d/decision-1/examples?dataset=dataset-1${
      initialCaseId ? `&case=${initialCaseId}` : ""
    }`,
  );
  const activeNavigation = new WorkspaceNavigation(window);
  navigation = activeNavigation;
  const saveLabels = vi.fn<ExampleAuthoringOperations["saveLabels"]>(
    async () => {
      throw new ApiError("preflight_failed", "Synthetic rejection.", 422);
    },
  );
  const operations: ExampleAuthoringOperations = {
    ...disconnectedWorkspace.authoring.examples,
    listCases: async () => ({ data: listCases, warnings: [] }),
    readCase: async ({ caseId }) => ({
      data: caseId === "case-b" ? caseB : caseA,
      warnings: [],
    }),
    listLabels: async () => ({ data: emptyLabelPage, warnings: [] }),
    readLabel: async ({ caseId }) => ({
      data: labelView(caseId === "case-b" ? caseB : caseA),
      warnings: [],
    }),
    saveLabels,
    ...overrides,
  };
  const datasetOperations: DatasetAuthoringOperations = {
    ...disconnectedWorkspace.authoring.datasets,
    read: async () => ({ data: dataset, warnings: [] }),
    ...datasetOverrides,
  };
  const user = userEvent.setup();
  const renderPage = (datasetFromRoute: string, caseFromRoute?: string) => (
    <ExamplesPage
      project={project}
      decision={decision}
      operations={operations}
      datasetOperations={datasetOperations}
      navigation={activeNavigation}
      datasetFromRoute={datasetFromRoute}
      caseFromRoute={caseFromRoute}
      refreshToken={0}
      onDatasetChange={(_, caseId) =>
        activeNavigation.navigate({
          kind: "examples",
          registrationId: project.id,
          decisionId: decision.id,
          datasetId: "dataset-1",
          caseId,
        })
      }
      onImport={() => undefined}
      onSplit={() => undefined}
    />
  );
  function NavigationAwarePage() {
    const [route, setRoute] = useState(activeNavigation.current);
    useEffect(() => activeNavigation.subscribe(setRoute), []);
    const examplesRoute = route.kind === "examples" ? route : undefined;
    return renderPage(
      examplesRoute?.datasetId ?? "dataset-1",
      examplesRoute?.caseId,
    );
  }
  render(
    followNavigation ? (
      <NavigationAwarePage />
    ) : (
      renderPage("dataset-1", initialCaseId ?? undefined)
    ),
  );
  return { user, operations, saveLabels: operations.saveLabels };
}

async function waitForSelectedSource(expected: string) {
  await waitFor(() => {
    expect(
      screen.getByLabelText("Complete example input source").textContent,
    ).toBe(expected);
  });
}

it("keeps the old display read-only until the selected case and label pair is admitted", async () => {
  window.history.replaceState(
    null,
    "",
    "#/p/registration-1/d/decision-1/examples?dataset=dataset-1&case=case-a",
  );
  navigation = new WorkspaceNavigation(window);
  let releaseTargetRead!: () => void;
  const heldTargetRead = new Promise<{ data: CaseRead; warnings: [] }>(
    (resolve) => {
      releaseTargetRead = () => resolve({ data: caseB, warnings: [] });
    },
  );
  const readCase = vi.fn<ExampleAuthoringOperations["readCase"]>(
    ({ caseId }) =>
      caseId === "case-b"
        ? heldTargetRead
        : Promise.resolve({ data: caseA, warnings: [] }),
  );
  const saveLabels = vi.fn<ExampleAuthoringOperations["saveLabels"]>(
    async () => {
      throw new ApiError("preflight_failed", "Synthetic rejection.", 422);
    },
  );
  const operations: ExampleAuthoringOperations = {
    ...disconnectedWorkspace.authoring.examples,
    listCases: async () => ({ data: listCases, warnings: [] }),
    readCase,
    listLabels: async () => ({ data: emptyLabelPage, warnings: [] }),
    readLabel: async ({ caseId }) => ({
      data: labelView(caseId === "case-b" ? caseB : caseA),
      warnings: [],
    }),
    saveLabels,
  };
  const datasetOperations: DatasetAuthoringOperations = {
    ...disconnectedWorkspace.authoring.datasets,
    read: async () => ({ data: dataset, warnings: [] }),
  };
  const user = userEvent.setup();
  render(
    <ExamplesPage
      project={project}
      decision={decision}
      operations={operations}
      datasetOperations={datasetOperations}
      navigation={navigation}
      datasetFromRoute="dataset-1"
      caseFromRoute="case-a"
      refreshToken={0}
      onDatasetChange={(_, caseId) =>
        navigation!.navigate({
          kind: "examples",
          registrationId: project.id,
          decisionId: decision.id,
          datasetId: "dataset-1",
          caseId,
        })
      }
      onImport={() => undefined}
      onSplit={() => undefined}
    />,
  );

  await waitForSelectedSource(sourceA);
  await user.click(screen.getByRole("button", { name: "case-b" }));
  await screen.findByRole("region", { name: "Selected review status" });
  expect(
    screen.getByLabelText("Complete example input source").textContent,
  ).toBe(sourceA);
  const optionA = screen.getByRole("checkbox", { name: "Option A" });
  expect(optionA.matches(":disabled")).toBe(true);
  expect(saveLabels).not.toHaveBeenCalled();

  releaseTargetRead();
  await waitFor(() => {
    expect(
      screen.getByLabelText("Complete example input source").textContent,
    ).toBe(sourceB);
  });
  await user.click(screen.getByRole("checkbox", { name: "Option A" }));
  await user.click(
    screen.getByRole("button", { name: "Save expected answer" }),
  );
  await waitFor(() => expect(saveLabels).toHaveBeenCalledTimes(1));
  const request = saveLabels.mock.calls[0]?.[0];
  expect(request?.registrationId).toBe(project.id);
  expect(request?.decisionId).toBe(decision.id);
  expect(request?.datasetId).toBe("dataset-1");
  expect(request?.body.edits[0]?.review.case_id).toBe("case-b");
});

it("keeps the last admitted pair read-only after the selected label read fails", async () => {
  let failedTargetRead = false;
  const readLabel = vi.fn<ExampleAuthoringOperations["readLabel"]>(
    async ({ caseId }) => {
      if (caseId === "case-b" && !failedTargetRead) {
        failedTargetRead = true;
        throw new ApiError("source_busy", "Read failed.", 503);
      }
      return {
        data: labelView(caseId === "case-b" ? caseB : caseA),
        warnings: [],
      };
    },
  );
  const { user, saveLabels } = mountExamples({ readLabel });

  await waitForSelectedSource(sourceA);
  await user.click(screen.getByRole("button", { name: "case-b" }));
  await screen.findByText(
    "The selected example is not ready for changes. Reload its current review.",
  );
  expect(
    screen.getByLabelText("Complete example input source").textContent,
  ).toBe(sourceA);
  expect(
    screen.getByRole("checkbox", { name: "Option A" }).matches(":disabled"),
  ).toBe(true);
  expect(
    screen
      .getByRole("button", { name: "Reload selected review" })
      .matches(":disabled"),
  ).toBe(false);
  expect(saveLabels).not.toHaveBeenCalled();

  await user.click(
    screen.getByRole("button", { name: "Reload selected review" }),
  );
  await waitFor(() => {
    expect(
      screen.getByLabelText("Complete example input source").textContent,
    ).toBe(sourceB);
  });
  expect(
    readLabel.mock.calls.filter(([args]) => args.caseId === "case-b"),
  ).toHaveLength(2);
  expect(saveLabels).not.toHaveBeenCalled();
});

it("does not publish an old A-to-B read after a rapid return to A", async () => {
  const refreshedA = caseRead("case-a", '{"case":"returned-a"}');
  let releaseB!: () => void;
  const heldB = new Promise<{ data: CaseRead; warnings: [] }>((resolve) => {
    releaseB = () => {
      resolve({ data: caseB, warnings: [] });
    };
  });
  let aReads = 0;
  const readCase = vi.fn<ExampleAuthoringOperations["readCase"]>(
    ({ caseId }) => {
      if (caseId === "case-b") return heldB;
      aReads += 1;
      return Promise.resolve({
        data: aReads === 1 ? caseA : refreshedA,
        warnings: [],
      });
    },
  );
  const readLabel = vi.fn<ExampleAuthoringOperations["readLabel"]>(
    async ({ caseId }) => ({
      data: labelView(
        caseId === "case-b" ? caseB : aReads === 1 ? caseA : refreshedA,
      ),
      warnings: [],
    }),
  );
  const { user } = mountExamples({ readCase, readLabel });

  await waitForSelectedSource(sourceA);
  await user.click(screen.getByRole("button", { name: "case-b" }));
  await waitFor(() => {
    expect(readCase.mock.calls.some(([args]) => args.caseId === "case-b")).toBe(
      true,
    );
  });
  await user.click(screen.getByRole("button", { name: "case-a" }));
  await waitFor(() => {
    expect(
      screen.getByLabelText("Complete example input source").textContent,
    ).toBe(refreshedA.case.record.input_source);
  });

  await act(async () => {
    releaseB();
    await heldB;
  });
  expect(
    screen.getByLabelText("Complete example input source").textContent,
  ).toBe(refreshedA.case.record.input_source);
  expect(readLabel.mock.calls.some(([args]) => args.caseId === "case-b")).toBe(
    false,
  );
});

it("saves the old admitted case before completing a dirty navigation", async () => {
  let currentDataset: DatasetRead = dataset;
  let currentCase = caseA;
  let routeAtWrite: string | undefined;
  const editCase = vi.fn<ExampleAuthoringOperations["editCase"]>(
    async ({ caseId, body }) => {
      routeAtWrite =
        navigation?.current.kind === "examples"
          ? navigation.current.caseId
          : undefined;
      const updated = caseRead(caseId, body.input_source);
      currentDataset = {
        ...dataset,
        etag: "dataset-etag-saved",
      };
      currentCase = {
        ...updated,
        dataset_etag: currentDataset.etag,
        case: { ...updated.case, etag: "etag-case-a-saved" },
      };
      const receipt: CaseEditReceipt = {
        schema_version: 1,
        case: currentCase.case,
        dataset: currentDataset,
        cleared_label_ids: [],
        replayed: false,
      };
      return { data: receipt, warnings: [] };
    },
  );
  const readCase = vi.fn<ExampleAuthoringOperations["readCase"]>(
    async ({ caseId }) => ({
      data:
        caseId === "case-a"
          ? currentCase
          : { ...caseB, dataset_etag: currentDataset.etag },
      warnings: [],
    }),
  );
  const readLabel = vi.fn<ExampleAuthoringOperations["readLabel"]>(
    async ({ caseId }) => ({
      data: labelView(
        caseId === "case-a"
          ? currentCase
          : { ...caseB, dataset_etag: currentDataset.etag },
      ),
      warnings: [],
    }),
  );
  const { user } = mountExamples(
    {
      editCase,
      readCase,
      readLabel,
      listCases: async () => ({
        data: {
          ...listCases,
          dataset_etag: currentDataset.etag,
          items: [currentCase.case, caseB.case],
        },
        warnings: [],
      }),
    },
    { read: async () => ({ data: currentDataset, warnings: [] }) },
    "case-a",
    true,
  );

  await waitForSelectedSource(sourceA);
  await user.click(screen.getByRole("button", { name: "Edit input" }));
  const savedSource = '{"case":"saved-before-leaving"}';
  fireEvent.change(screen.getByRole("textbox", { name: "Input source" }), {
    target: { value: savedSource },
  });
  await user.click(screen.getByRole("button", { name: "case-b" }));
  await screen.findByRole("button", { name: "Save and leave" });
  await user.click(screen.getByRole("button", { name: "Save and leave" }));

  await waitForSelectedSource(sourceB);
  expect(editCase).toHaveBeenCalledTimes(1);
  expect(editCase.mock.calls[0]?.[0].caseId).toBe("case-a");
  expect(editCase.mock.calls[0]?.[0].body.input_source).toBe(savedSource);
  expect(routeAtWrite).toBe("case-a");
  expect(navigation?.current.kind).toBe("examples");
  if (navigation?.current.kind === "examples")
    expect(navigation.current.caseId).toBe("case-b");
});

it("recaptures the acknowledged same-scope label after a guard saves the case", async () => {
  let currentDataset = dataset;
  let currentCase = caseA;
  let currentLabel: LabelView["label"] = null;
  const events: string[] = [];
  const editCase = vi.fn<ExampleAuthoringOperations["editCase"]>(
    async ({ caseId, body }) => {
      events.push("edit-case");
      const updated = caseRead(caseId, body.input_source);
      currentDataset = { ...dataset, etag: "dataset-etag-after-case" };
      currentCase = {
        ...updated,
        dataset_etag: currentDataset.etag,
        case: {
          ...updated.case,
          etag: "etag-case-a-after-case",
          record: {
            ...updated.case.record,
            metadata_source: body.metadata_source,
          },
        },
      };
      return {
        data: {
          schema_version: 1,
          case: currentCase.case,
          dataset: currentDataset,
          cleared_label_ids: [],
          replayed: false,
        },
        warnings: [],
      };
    },
  );
  const readCase = vi.fn<ExampleAuthoringOperations["readCase"]>(
    async ({ caseId }) => {
      events.push(`read-case:${caseId}`);
      return {
        data:
          caseId === "case-a"
            ? currentCase
            : { ...caseB, dataset_etag: currentDataset.etag },
        warnings: [],
      };
    },
  );
  const readLabel = vi.fn<ExampleAuthoringOperations["readLabel"]>(
    async ({ caseId }) => {
      events.push(`read-label:${caseId}`);
      const read =
        caseId === "case-a"
          ? currentCase
          : { ...caseB, dataset_etag: currentDataset.etag };
      const view = labelView(read);
      return {
        data: {
          ...view,
          status: currentLabel ? "applicable" : "unlabelled",
          label: currentLabel,
          review: {
            ...view.review,
            label_etag: currentLabel ? "label-etag-after-save" : null,
          },
        },
        warnings: [],
      };
    },
  );
  const saveLabels = vi.fn<ExampleAuthoringOperations["saveLabels"]>(
    async ({ body }) => {
      events.push("save-label");
      const receipt = labelReceipt(body);
      currentLabel = receipt.changes[0]?.label ?? null;
      return { data: receipt, warnings: [] };
    },
  );
  const { user } = mountExamples(
    {
      editCase,
      readCase,
      readLabel,
      saveLabels,
      listCases: async () => ({
        data: {
          ...listCases,
          dataset_etag: currentDataset.etag,
          items: [currentCase.case, caseB.case],
        },
        warnings: [],
      }),
    },
    { read: async () => ({ data: currentDataset, warnings: [] }) },
    "case-a",
    true,
  );

  await waitForSelectedSource(sourceA);
  await user.click(screen.getByRole("checkbox", { name: "Option A" }));
  await user.click(screen.getByRole("button", { name: "Edit input" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Metadata source" }), {
    target: { value: '{"guard":"saved first"}' },
  });
  await user.click(screen.getByRole("button", { name: "case-b" }));
  await screen.findByRole("button", { name: "Save and leave" });
  await user.click(screen.getByRole("button", { name: "Save and leave" }));

  await waitForSelectedSource(sourceB);
  expect(editCase).toHaveBeenCalledTimes(1);
  expect(saveLabels).toHaveBeenCalledTimes(1);
  const labelRequest = saveLabels.mock.calls[0]?.[0];
  expect(labelRequest?.body.edits[0]?.review.case_id).toBe("case-a");
  const caseSave = events.indexOf("edit-case");
  const refreshedCase = events.indexOf("read-case:case-a", caseSave + 1);
  const refreshedLabel = events.indexOf("read-label:case-a", caseSave + 1);
  const labelSave = events.indexOf("save-label");
  expect(caseSave).toBeGreaterThanOrEqual(0);
  expect(refreshedCase).toBeGreaterThan(caseSave);
  expect(refreshedLabel).toBeGreaterThan(refreshedCase);
  expect(labelSave).toBeGreaterThan(refreshedLabel);
});

it("rejects a stale expected-answer callback after live navigation publishes before render", async () => {
  const { saveLabels } = mountExamples();
  await waitForSelectedSource(sourceA);
  const answer = screen.getByRole("checkbox", { name: "Option A" });
  await act(async () => {
    await navigation!.navigate({
      kind: "examples",
      registrationId: project.id,
      decisionId: "decision-2",
      datasetId: "dataset-1",
      caseId: "case-a",
    });
    expect(answer.matches(":disabled")).toBe(false);
    fireEvent.click(answer);
  });

  expect(answer.matches(":checked")).toBe(false);
  expect(saveLabels).not.toHaveBeenCalled();
});

it("rejects a stale source callback after live navigation publishes before render", async () => {
  const editCase = vi.fn<ExampleAuthoringOperations["editCase"]>(async () => {
    throw new ApiError("preflight_failed", "Should not write.", 422);
  });
  const { user } = mountExamples({ editCase });
  await waitForSelectedSource(sourceA);
  await user.click(screen.getByRole("button", { name: "Edit input" }));
  const sourceEditor = screen.getByRole("textbox", { name: "Input source" });
  if (!(sourceEditor instanceof HTMLTextAreaElement))
    throw new Error("Expected the input source editor to be a textarea.");
  await act(async () => {
    await navigation!.navigate({
      kind: "examples",
      registrationId: project.id,
      decisionId: "decision-2",
      datasetId: "dataset-1",
      caseId: "case-a",
    });
    expect(sourceEditor.readOnly).toBe(false);
    fireEvent.change(sourceEditor, { target: { value: sourceB } });
  });

  expect(sourceEditor.value).toBe(sourceA);
  expect(editCase).not.toHaveBeenCalled();
});

it("rejects A's retained callback after B's paired admission publishes before render", async () => {
  let releaseTargetLabel!: () => void;
  let reportTargetLabelStarted!: () => void;
  const targetLabelStarted = new Promise<void>((resolve) => {
    reportTargetLabelStarted = resolve;
  });
  const heldTargetLabel = new Promise<{ data: LabelView; warnings: [] }>(
    (resolve) => {
      releaseTargetLabel = () =>
        resolve({ data: labelView(caseB), warnings: [] });
    },
  );
  const readLabel = vi.fn<ExampleAuthoringOperations["readLabel"]>(
    ({ caseId }) => {
      if (caseId === "case-b") {
        reportTargetLabelStarted();
        return heldTargetLabel;
      }
      return Promise.resolve({ data: labelView(caseA), warnings: [] });
    },
  );
  const saveLabels = vi.fn<ExampleAuthoringOperations["saveLabels"]>(
    async () => {
      throw new ApiError("preflight_failed", "Unexpected label write.", 422);
    },
  );
  const { user } = mountExamples({ readLabel, saveLabels });

  await waitForSelectedSource(sourceA);
  const oldOption = screen.getByRole("checkbox", { name: "Option A" });
  await user.click(screen.getByRole("button", { name: "case-b" }));
  await targetLabelStarted;
  expect(
    screen.getByLabelText("Complete example input source").textContent,
  ).toBe(sourceA);

  await act(async () => {
    releaseTargetLabel();
    await heldTargetLabel;
    fireEvent.click(oldOption);
  });

  expect(
    screen.getByLabelText("Complete example input source").textContent,
  ).toBe(sourceB);
  expect(
    screen.getByRole("checkbox", { name: "Option A" }).matches(":checked"),
  ).toBe(false);
  expect(saveLabels).not.toHaveBeenCalled();
  await user.click(screen.getByRole("checkbox", { name: "Option A" }));
  await user.click(
    screen.getByRole("button", { name: "Save expected answer" }),
  );
  await waitFor(() => expect(saveLabels).toHaveBeenCalledTimes(1));
  expect(saveLabels.mock.calls[0]?.[0].body.edits[0]?.review.case_id).toBe(
    "case-b",
  );
});

it("admits one same-turn label write and releases the lock after its refresh", async () => {
  type LabelSaveResult = Awaited<
    ReturnType<ExampleAuthoringOperations["saveLabels"]>
  >;
  let resolveFirst!: (result: LabelSaveResult) => void;
  let firstBody: LabelBatchBody | undefined;
  let currentLabel: LabelView["label"] = null;
  const firstRequest = new Promise<LabelSaveResult>((resolve) => {
    resolveFirst = resolve;
  });
  const saveLabels = vi
    .fn<ExampleAuthoringOperations["saveLabels"]>()
    .mockImplementationOnce(({ body }) => {
      firstBody = body;
      return firstRequest;
    })
    .mockRejectedValue(new ApiError("validation_failed", "Rejected.", 422));
  const readLabel = vi.fn<ExampleAuthoringOperations["readLabel"]>(async () => {
    const view = labelView(caseA);
    return {
      data: {
        ...view,
        status: currentLabel ? "applicable" : "unlabelled",
        label: currentLabel,
        review: {
          ...view.review,
          label_etag: currentLabel ? "label-etag-a" : null,
        },
      },
      warnings: [],
    };
  });
  const { user } = mountExamples({ saveLabels, readLabel });

  await waitForSelectedSource(sourceA);
  await user.click(screen.getByRole("checkbox", { name: "Option A" }));
  const save = screen.getByRole("button", { name: "Save expected answer" });
  await act(async () => {
    fireEvent.click(save);
    fireEvent.click(save);
  });
  expect(saveLabels).toHaveBeenCalledTimes(1);
  const firstOperationId = saveLabels.mock.calls[0]?.[0].body.operation_id;
  if (!firstBody) throw new Error("The first label body was not captured.");
  const firstLabelReceipt = labelReceipt(firstBody);
  currentLabel = firstLabelReceipt.changes[0]?.label ?? null;
  resolveFirst({ data: firstLabelReceipt, warnings: [] });
  await screen.findByText("Applicable · human");
  await waitFor(() => {
    expect(
      screen
        .getByRole("button", { name: "Save expected answer" })
        .matches(":disabled"),
    ).toBe(false);
  });

  await user.click(screen.getByRole("checkbox", { name: "Option B" }));
  await user.click(
    screen.getByRole("button", { name: "Save expected answer" }),
  );
  expect(saveLabels).toHaveBeenCalledTimes(2);
  expect(firstOperationId).toBeDefined();
  expect(saveLabels.mock.calls[1]?.[0].body.operation_id).not.toBe(
    firstOperationId,
  );
  await waitFor(() => {
    expect(
      screen
        .getByRole("button", { name: "Save expected answer" })
        .matches(":disabled"),
    ).toBe(false);
  });
});

it("does not admit a captured case write while label conflict review is reading", async () => {
  let holdReviewRead = false;
  let injectCapturedSave = false;
  let capturedSave: HTMLElement | undefined;
  let reportReviewReadStarted!: () => void;
  let releaseReviewRead!: () => void;
  const reviewReadStarted = new Promise<void>((resolve) => {
    reportReviewReadStarted = resolve;
  });
  const heldReviewRead = new Promise<{ data: DatasetRead; warnings: [] }>(
    (resolve) => {
      releaseReviewRead = () => resolve({ data: dataset, warnings: [] });
    },
  );
  const readDataset = vi.fn<DatasetAuthoringOperations["read"]>(async () => {
    if (holdReviewRead) {
      if (injectCapturedSave) {
        injectCapturedSave = false;
        if (!capturedSave)
          throw new Error("The original save control was not captured.");
        expect(capturedSave.matches(":disabled")).toBe(false);
        fireEvent.click(capturedSave);
        reportReviewReadStarted();
      }
      return heldReviewRead;
    }
    return { data: dataset, warnings: [] };
  });
  const saveLabels = vi.fn<ExampleAuthoringOperations["saveLabels"]>(
    async () => {
      throw new ApiError("etag_conflict", "Conflict.", 409);
    },
  );
  const editCase = vi.fn<ExampleAuthoringOperations["editCase"]>(async () => {
    throw new Error("A case write must not start during label review.");
  });
  const { user } = mountExamples(
    { saveLabels, editCase },
    { read: readDataset },
  );

  await waitForSelectedSource(sourceA);
  await user.click(screen.getByRole("button", { name: "Edit input" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Input source" }), {
    target: { value: sourceB },
  });
  await user.click(screen.getByRole("checkbox", { name: "Option A" }));
  await user.click(
    screen.getByRole("button", { name: "Save expected answer" }),
  );
  expect(saveLabels).toHaveBeenCalledTimes(1);
  await screen.findByRole("button", { name: "Review current label" });

  holdReviewRead = true;
  injectCapturedSave = true;
  capturedSave = screen.getByRole("button", { name: "Save input" });
  await user.click(
    screen.getByRole("button", { name: "Review current label" }),
  );
  await reviewReadStarted;
  expect(editCase).not.toHaveBeenCalled();

  releaseReviewRead();
  await waitFor(() => {
    expect(
      screen.queryByRole("button", { name: "Review current label" }),
    ).toBeNull();
  });
});

it("writes the latest same-owner case fields before React mirrors the edits", async () => {
  const editCase = vi.fn<ExampleAuthoringOperations["editCase"]>(async () => {
    throw new ApiError("validation_failed", "Rejected for the test.", 422);
  });
  const { user } = mountExamples({ editCase });

  await waitForSelectedSource(sourceA);
  await user.click(screen.getByRole("button", { name: "Edit input" }));
  const inputSource = screen.getByRole("textbox", { name: "Input source" });
  const metadataSource = screen.getByRole("textbox", {
    name: "Metadata source",
  });
  const save = screen.getByRole("button", { name: "Save input" });
  const latestSource = '{"case":"latest","value":9007199254740993}';
  const latestMetadata = '{"attempt":2}';

  await act(async () => {
    fireEvent.change(inputSource, { target: { value: sourceB } });
    fireEvent.change(inputSource, { target: { value: latestSource } });
    fireEvent.change(metadataSource, { target: { value: '{"attempt":1}' } });
    fireEvent.change(metadataSource, { target: { value: latestMetadata } });
    fireEvent.click(save);
  });

  await waitFor(() => expect(editCase).toHaveBeenCalledTimes(1));
  expect(editCase.mock.calls[0]?.[0].body.input_source).toBe(latestSource);
  expect(editCase.mock.calls[0]?.[0].body.metadata_source).toBe(latestMetadata);
});

it("accumulates same-owner answer toggles and the latest note in the write snapshot", async () => {
  const saveLabels = vi.fn<ExampleAuthoringOperations["saveLabels"]>(
    async () => {
      throw new ApiError("validation_failed", "Rejected for the test.", 422);
    },
  );
  const { user } = mountExamples({ saveLabels });

  await waitForSelectedSource(sourceA);
  await user.click(screen.getByRole("checkbox", { name: "Option A" }));
  const optionB = screen.getByRole("checkbox", { name: "Option B" });
  const note = screen.getByRole("textbox", { name: "Provenance note" });
  const save = screen.getByRole("button", { name: "Save expected answer" });
  await act(async () => {
    fireEvent.click(optionB);
    fireEvent.change(note, { target: { value: "first note" } });
    fireEvent.change(note, { target: { value: "latest note" } });
    fireEvent.click(save);
  });

  await waitFor(() => expect(saveLabels).toHaveBeenCalledTimes(1));
  const edit = saveLabels.mock.calls[0]?.[0].body.edits[0];
  expect(edit?.acceptable_option_ids).toEqual(["option-a", "option-b"]);
  expect(edit?.note).toBe("latest note");
});

it("rejects an old dataset Add callback after its route is replaced", async () => {
  mountExamples();
  await waitForSelectedSource(sourceA);
  const oldAddButton = screen.getByRole("button", { name: "Add example" });

  await act(async () => {
    const moved = await navigation!.navigate({
      kind: "examples",
      registrationId: project.id,
      decisionId: decision.id,
      datasetId: "dataset-2",
    });
    expect(moved).toBe(true);
    fireEvent.click(oldAddButton);
  });

  expect(screen.queryByRole("dialog", { name: "Add example" })).toBeNull();
});

it("keeps Add available from a dataset admission without a selected case", async () => {
  const addCase = vi.fn<ExampleAuthoringOperations["addCase"]>(async () => {
    throw new ApiError("validation_failed", "Rejected for the test.", 422);
  });
  const { user } = mountExamples({ addCase }, {}, null);

  await screen.findByRole("heading", { name: "Cases" });
  await user.click(screen.getByRole("button", { name: "Add example" }));
  await user.click(
    within(screen.getByRole("dialog", { name: "Add example" })).getByRole(
      "radio",
      { name: "JSON" },
    ),
  );
  fireEvent.change(screen.getByRole("textbox", { name: "Input source" }), {
    target: { value: '{"dataset-only":true}' },
  });
  await user.click(
    within(screen.getByRole("dialog", { name: "Add example" })).getByRole(
      "button",
      { name: "Add example" },
    ),
  );

  await waitFor(() => expect(addCase).toHaveBeenCalledTimes(1));
  const request = addCase.mock.calls[0]?.[0];
  expect(request?.datasetId).toBe("dataset-1");
  expect(request?.body.input_source).toBe('{"dataset-only":true}');
});

it("rejects an A1 callback after the live route moves through B and back to A", async () => {
  const saveLabels = vi.fn<ExampleAuthoringOperations["saveLabels"]>(
    async () => {
      throw new ApiError(
        "validation_failed",
        "A stale callback must not write.",
        422,
      );
    },
  );
  mountExamples({ saveLabels });
  await waitForSelectedSource(sourceA);
  const oldAnswer = screen.getByRole("checkbox", { name: "Option A" });

  await act(async () => {
    await navigation!.navigate({
      kind: "examples",
      registrationId: project.id,
      decisionId: decision.id,
      datasetId: "dataset-1",
      caseId: "case-b",
    });
    await navigation!.navigate({
      kind: "examples",
      registrationId: project.id,
      decisionId: decision.id,
      datasetId: "dataset-1",
      caseId: "case-a",
    });
    fireEvent.click(oldAnswer);
  });

  expect(saveLabels).not.toHaveBeenCalled();
  expect(oldAnswer.matches(":checked")).toBe(false);
});
