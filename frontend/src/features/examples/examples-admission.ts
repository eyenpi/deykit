import type { ApiOperationData } from "../../api/client";
import type { WorkspaceRoute } from "../../workspace/routes";

export type CasePage = ApiOperationData<
  "list_cases_api_v1_projects__registration_id__datasets__dataset_id__cases_get"
>;
export type CaseRead = ApiOperationData<
  "read_case_api_v1_projects__registration_id__datasets__dataset_id__cases__case_id__get"
>;
export type DatasetRead = ApiOperationData<
  "read_dataset_api_v1_projects__registration_id__datasets__dataset_id__get"
>;
export type LabelPage = ApiOperationData<
  "list_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_get"
>;
export type LabelView = ApiOperationData<
  "read_label_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels__case_id__get"
>;

export type ReadContext = {
  registrationId: string;
  datasetId: string;
  decisionId?: string;
  selectedCaseId?: string;
  refreshGeneration: number;
  refreshToken: number;
};

export type DatasetScope = { registrationId: string; datasetId: string };
export type SelectionScope = DatasetScope & { decisionId?: string; caseId: string };

export type DatasetAdmission = {
  registrationId: string;
  datasetId: string;
  refreshGeneration: number;
  refreshToken: number;
  epoch: number;
  read: DatasetRead;
};

export type SelectionAdmission = {
  registrationId: string;
  datasetId: string;
  decisionId?: string;
  caseId: string;
  readEpoch: number;
  navigationEpoch: number;
  datasetAdmission: DatasetAdmission;
  caseRead: CaseRead;
  labelView?: LabelView;
};

export type StagedOwner = {
  readEpoch: number;
  navigationEpoch: number;
};

export function liveDatasetRouteMatches(
  route: WorkspaceRoute,
  expected: DatasetScope,
  fallbackDatasetId?: string,
): boolean {
  return (
    route.kind === "examples" &&
    route.registrationId === expected.registrationId &&
    (route.datasetId ?? fallbackDatasetId ?? "") === expected.datasetId
  );
}

export function liveSelectionRouteMatches(
  route: WorkspaceRoute,
  expected: SelectionScope,
  fallback: { datasetId?: string; caseId?: string },
): boolean {
  return (
    route.kind === "examples" &&
    route.registrationId === expected.registrationId &&
    (route.datasetId ?? fallback.datasetId ?? "") === expected.datasetId &&
    (route.decisionId === null ? undefined : route.decisionId) ===
      expected.decisionId &&
    (route.caseId ?? fallback.caseId) === expected.caseId
  );
}

export function matchesSelectionScope(
  scope: SelectionScope,
  admission: SelectionScope,
): boolean {
  return (
    scope.registrationId === admission.registrationId &&
    scope.datasetId === admission.datasetId &&
    scope.decisionId === admission.decisionId &&
    scope.caseId === admission.caseId
  );
}

export function matchesDatasetScope(
  scope: DatasetScope,
  admission: DatasetScope,
): boolean {
  return (
    scope.registrationId === admission.registrationId &&
    scope.datasetId === admission.datasetId
  );
}

export function sameCaseSource(
  left: CaseRead["case"]["record"],
  right: LabelView["case"],
): boolean {
  const sameItems = (a: readonly string[] = [], b: readonly string[] = []) =>
    a.length === b.length && a.every((item, index) => item === b[index]);
  return (
    left.id === right.id &&
    left.dataset_id === right.dataset_id &&
    left.input_kind === right.input_kind &&
    left.input_source === right.input_source &&
    (left.metadata_source ?? "{}") === (right.metadata_source ?? "{}") &&
    (left.split ?? "development") === (right.split ?? "development") &&
    (left.group_id ?? null) === (right.group_id ?? null) &&
    sameItems(left.tags, right.tags) &&
    sameItems(left.derived_from, right.derived_from)
  );
}

export type LabelRecord = NonNullable<
  ApiOperationData<
    "batch_labels_api_v1_projects__registration_id__decisions__decision_id__datasets__dataset_id__labels_batch_post"
  >["changes"][number]["label"]
>;

export function sameLabelRecord(
  left: LabelRecord | null,
  right: LabelRecord | null,
): boolean {
  if (left === null || right === null) return left === right;
  return (
    left.id === right.id &&
    left.case_id === right.case_id &&
    left.dataset_id === right.dataset_id &&
    left.decision_id === right.decision_id &&
    left.question_id === right.question_id &&
    left.input_hash === right.input_hash &&
    left.schema_version === right.schema_version &&
    left.hash_format === right.hash_format &&
    left.provenance === right.provenance &&
    left.status === right.status &&
    left.note === right.note &&
    left.updated_at === right.updated_at &&
    left.acceptable_option_ids.length === right.acceptable_option_ids.length &&
    left.acceptable_option_ids.every(
      (optionId, index) => optionId === right.acceptable_option_ids[index],
    )
  );
}

export function sameLabelReview(left: LabelView, right: LabelView): boolean {
  return (
    left.review.case_id === right.review.case_id &&
    left.review.dataset_id === right.review.dataset_id &&
    left.review.decision_id === right.review.decision_id &&
    left.review.question_id === right.review.question_id &&
    left.review.decision_etag === right.review.decision_etag &&
    left.review.draft_etag === right.review.draft_etag &&
    left.review.input_hash === right.review.input_hash &&
    sameLabelRecord(left.label ?? null, right.label ?? null)
  );
}

export function selectionPairMatches(args: {
  datasetId: string;
  decisionId?: string;
  caseId: string;
  dataset: DatasetRead;
  caseRead: CaseRead;
  labelView?: LabelView;
}): boolean {
  const { dataset, caseRead, labelView } = args;
  return (
    dataset.record.id === args.datasetId &&
    caseRead.case.record.id === args.caseId &&
    caseRead.case.record.dataset_id === args.datasetId &&
    caseRead.dataset_etag === dataset.etag &&
    ((args.decisionId === undefined) === (labelView === undefined)) &&
    (labelView === undefined ||
      (labelView.review.case_id === args.caseId &&
        labelView.review.dataset_id === args.datasetId &&
        labelView.review.decision_id === args.decisionId &&
        labelView.review.question_id ===
          labelView.definition.questions[0]?.id &&
        labelView.review.input_hash.length > 0 &&
        sameCaseSource(caseRead.case.record, labelView.case)))
  );
}
