import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import type { ApiOperationData } from "../../api/client";
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

  await screen.findByText(sourceA);
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
