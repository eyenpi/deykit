import { describe, expect, it } from "vitest";
import type { CaseRead, DatasetRead, LabelView } from "./examples-admission";
import {
  liveSelectionRouteMatches,
  matchesSelectionScope,
  sameCaseSource,
  selectionPairMatches,
} from "./examples-admission";

const source = '{"large":9007199254740993,"tail":';
const record: CaseRead["case"]["record"] = {
  schema_version: 1,
  id: "case-1",
  dataset_id: "dataset-1",
  input_kind: "json",
  input_source: source,
  operation_id: "case-op-1",
};
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
const caseRead: CaseRead = {
  schema_version: 1,
  dataset_etag: dataset.etag,
  case: { schema_version: 1, etag: "case-etag-1", record },
};
const labelView: LabelView = {
  schema_version: 1,
  status: "unlabelled",
  reasons: [],
  missing_option_ids: [],
  case: record,
  definition: {
    schema_version: 1,
    input_kind: "json",
    questions: [
      {
        id: "question-1",
        instructions: "Choose one",
        options: [{ id: "option-a", name: "Option A" }],
      },
    ],
  },
  label: null,
  review: {
    case_id: "case-1",
    dataset_id: "dataset-1",
    decision_id: "decision-1",
    question_id: "question-1",
    decision_etag: "decision-etag-1",
    draft_etag: "draft-etag-1",
    input_hash: "input-hash-1",
    label_etag: null,
  },
};

describe("Examples selection admission", () => {
  it("admits only the exact live route, including its decision context", () => {
    const route = {
      kind: "examples",
      registrationId: "registration-1",
      decisionId: "decision-1",
      datasetId: "dataset-1",
      caseId: "case-1",
    } as const;
    const expected = {
      registrationId: "registration-1",
      decisionId: "decision-1",
      datasetId: "dataset-1",
      caseId: "case-1",
    };

    expect(liveSelectionRouteMatches(route, expected, {})).toBe(true);
    expect(
      liveSelectionRouteMatches({ ...route, caseId: "case-2" }, expected, {}),
    ).toBe(false);
    expect(
      liveSelectionRouteMatches({ ...route, decisionId: null }, expected, {}),
    ).toBe(false);
  });

  it("keeps the exact opaque source and requires matching dataset and label reads", () => {
    expect(
      selectionPairMatches({
        datasetId: "dataset-1",
        decisionId: "decision-1",
        caseId: "case-1",
        dataset,
        caseRead,
        labelView,
      }),
    ).toBe(true);
    expect(sameCaseSource(record, labelView.case)).toBe(true);
    expect(
      sameCaseSource(record, { ...labelView.case, input_source: `${source} ` }),
    ).toBe(false);
    expect(
      selectionPairMatches({
        datasetId: "dataset-1",
        decisionId: "decision-1",
        caseId: "case-1",
        dataset,
        caseRead: { ...caseRead, dataset_etag: "old-etag" },
        labelView,
      }),
    ).toBe(false);
    expect(
      selectionPairMatches({
        datasetId: "dataset-1",
        decisionId: "decision-1",
        caseId: "case-1",
        dataset,
        caseRead,
        labelView: {
          ...labelView,
          review: { ...labelView.review, case_id: "case-2" },
        },
      }),
    ).toBe(false);
  });

  it("does not let a retained uncertain write borrow another case scope", () => {
    const target = {
      registrationId: "registration-1",
      datasetId: "dataset-1",
      decisionId: "decision-1",
      caseId: "case-1",
    };
    expect(matchesSelectionScope(target, target)).toBe(true);
    expect(matchesSelectionScope(target, { ...target, caseId: "case-2" })).toBe(
      false,
    );
    expect(
      matchesSelectionScope(target, {
        registrationId: target.registrationId,
        datasetId: target.datasetId,
        caseId: target.caseId,
      }),
    ).toBe(false);
  });
});
