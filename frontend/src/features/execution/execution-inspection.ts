import { ApiError, object } from "../../api/client";
import type { ApiOperationData } from "../../api/client";

type ResultRowSource =
  ApiOperationData<"listResults">["items"][number]["source"];
type CaseDetailData = ApiOperationData<"readResult">;
type CountText = string;

export interface ResultContextView {
  runId: string;
  evaluationId: string | null;
  resultSnapshotId: string;
  resultContentHash: string;
  labelSnapshotId: string;
  labelContentHash: string;
  decisionId: string;
  decisionRevisionId: string;
  decisionDefinitionHash: string;
  datasetId: string;
  datasetSnapshotId: string;
  datasetContentHash: string;
  evaluationMode: string;
  throughEventSequence: CountText;
}

export interface AssessmentCountsView {
  all: CountText;
  inspect: CountText;
  incorrect: CountText;
  unlabelled: CountText;
}

export interface ProbabilityView {
  optionId: string;
  optionName: string;
  probability: string;
}

export interface ResultRowView {
  caseId: string;
  split: string;
  tags: readonly string[];
  status: string;
  answerOptionId: string | null;
  expectedOptionIds: readonly string[];
  setCorrect: boolean | null;
  exclusionReasons: readonly string[];
  annotationCount: CountText;
}

export interface CaseDetailView extends ResultRowView {
  context: ResultContextView;
  caseInputHash: string;
  probabilities: readonly ProbabilityView[];
  probabilitiesUnavailableReason: string | null;
  runId: string;
  resultSnapshotId: string;
  labelSnapshotId: string;
  evaluationId: string | null;
  questionId: string | null;
  answer: Readonly<Record<string, string | null>> | null;
  legacyQuestionIds: readonly string[];
  legacyExpectedOptionIds: readonly (readonly string[])[];
  legacyExclusionReasons: readonly (readonly string[])[];
  labelProvenance: string | null;
  annotations: readonly {
    id: string;
    note: string;
    createdAt: string;
  }[];
  attempts: readonly AttemptView[];
  inputSource: string | null;
}

export interface AttemptView {
  attemptId: string;
  number: CountText;
  kind: string;
  state: string;
  requestBodyHash: string;
  errorCode: string | null;
  errorReason: string | null;
  requestBodySource: string | null;
  responseSource: string | null;
}

function invalid(): never {
  throw new ApiError(
    "response_invalid",
    "The local service returned unsupported frozen result data.",
  );
}

function text(value: unknown): value is string {
  return typeof value === "string";
}

function nullableText(value: unknown): value is string | null {
  return value === null || text(value);
}

function nullableTextWhenPresent(
  value: unknown,
): value is string | null | undefined {
  return value === undefined || nullableText(value);
}

function textList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(text);
}

function textLists(value: unknown): value is string[][] {
  return Array.isArray(value) && value.every(textList);
}

function booleanOrNull(value: unknown): value is boolean | null {
  return value === null || typeof value === "boolean";
}

function nonnegativeCountText(value: unknown): value is CountText {
  return typeof value === "string" && /^(?:0|[1-9][0-9]*)$/.test(value);
}

function positiveCountText(value: unknown): value is CountText {
  return typeof value === "string" && /^[1-9][0-9]*$/.test(value);
}

function resultContext(value: unknown): ResultContextView {
  const context = object(value);
  if (
    !text(context.run_id) ||
    !nullableText(context.evaluation_id) ||
    !text(context.result_snapshot_id) ||
    !text(context.result_content_hash) ||
    !text(context.label_snapshot_id) ||
    !text(context.label_content_hash) ||
    !text(context.decision_id) ||
    !text(context.decision_revision_id) ||
    !text(context.decision_definition_hash) ||
    !text(context.dataset_id) ||
    !text(context.dataset_snapshot_id) ||
    !text(context.dataset_content_hash) ||
    !text(context.evaluation_mode) ||
    !nonnegativeCountText(context.through_event_sequence)
  )
    return invalid();
  return {
    runId: context.run_id,
    evaluationId: context.evaluation_id,
    resultSnapshotId: context.result_snapshot_id,
    resultContentHash: context.result_content_hash,
    labelSnapshotId: context.label_snapshot_id,
    labelContentHash: context.label_content_hash,
    decisionId: context.decision_id,
    decisionRevisionId: context.decision_revision_id,
    decisionDefinitionHash: context.decision_definition_hash,
    datasetId: context.dataset_id,
    datasetSnapshotId: context.dataset_snapshot_id,
    datasetContentHash: context.dataset_content_hash,
    evaluationMode: context.evaluation_mode,
    throughEventSequence: context.through_event_sequence,
  };
}

export function decodeResultContext(value: unknown): ResultContextView {
  return resultContext(value);
}

export function decodeAssessmentCounts(value: unknown): AssessmentCountsView {
  const counts = object(value);
  if (
    !nonnegativeCountText(counts.all) ||
    !nonnegativeCountText(counts.inspect) ||
    !nonnegativeCountText(counts.incorrect) ||
    !nonnegativeCountText(counts.unlabelled)
  )
    return invalid();
  return {
    all: counts.all,
    inspect: counts.inspect,
    incorrect: counts.incorrect,
    unlabelled: counts.unlabelled,
  };
}

export function sameResultContext(
  left: ResultContextView,
  right: ResultContextView,
): boolean {
  return (
    left.runId === right.runId &&
    left.evaluationId === right.evaluationId &&
    left.resultSnapshotId === right.resultSnapshotId &&
    left.resultContentHash === right.resultContentHash &&
    left.labelSnapshotId === right.labelSnapshotId &&
    left.labelContentHash === right.labelContentHash &&
    left.decisionId === right.decisionId &&
    left.decisionRevisionId === right.decisionRevisionId &&
    left.decisionDefinitionHash === right.decisionDefinitionHash &&
    left.datasetId === right.datasetId &&
    left.datasetSnapshotId === right.datasetSnapshotId &&
    left.datasetContentHash === right.datasetContentHash &&
    left.evaluationMode === right.evaluationMode &&
    left.throughEventSequence === right.throughEventSequence
  );
}

export function sameAssessmentCounts(
  left: AssessmentCountsView,
  right: AssessmentCountsView,
): boolean {
  return (
    left.all === right.all &&
    left.inspect === right.inspect &&
    left.incorrect === right.incorrect &&
    left.unlabelled === right.unlabelled
  );
}

function rowView(value: unknown): ResultRowView {
  const row = object(value);
  if (
    !text(row.case_id) ||
    !text(row.split) ||
    !textList(row.tags) ||
    !text(row.status) ||
    !nullableText(row.answer_option_id) ||
    !textList(row.expected_option_ids) ||
    !booleanOrNull(row.set_correct) ||
    !textList(row.exclusion_reasons) ||
    !nonnegativeCountText(row.annotation_count)
  )
    return invalid();
  return {
    caseId: row.case_id,
    split: row.split,
    tags: row.tags,
    status: row.status,
    answerOptionId: row.answer_option_id,
    expectedOptionIds: row.expected_option_ids,
    setCorrect: row.set_correct,
    exclusionReasons: row.exclusion_reasons,
    annotationCount: row.annotation_count,
  };
}

export function decodeResultRow(source: ResultRowSource): ResultRowView {
  return rowView(source);
}

function nullableTextRecord(
  value: unknown,
): Readonly<Record<string, string | null>> | null {
  if (value === null) return null;
  const answer = object(value);
  if (
    !nullableText(answer.option_id) ||
    !nullableText(answer.question_id) ||
    !nullableText(answer.probabilities_source) ||
    !nullableText(answer.native_confidence_source) ||
    !nullableText(answer.native_confidence_semantics) ||
    !nullableText(answer.reported_model)
  )
    return invalid();
  return {
    option_id: answer.option_id,
    question_id: answer.question_id,
    probabilities_source: answer.probabilities_source,
    native_confidence_source: answer.native_confidence_source,
    native_confidence_semantics: answer.native_confidence_semantics,
    reported_model: answer.reported_model,
  };
}

export function decodeCaseDetail(data: CaseDetailData): CaseDetailView {
  const detail = object(data.source);
  const row = rowView(detail);
  if (
    !text(detail.run_id) ||
    !text(detail.result_snapshot_id) ||
    !text(detail.label_snapshot_id) ||
    !nullableText(detail.evaluation_id) ||
    !nullableText(detail.question_id) ||
    !textLists(detail.legacy_expected_option_ids) ||
    !textLists(detail.legacy_exclusion_reasons) ||
    !textList(detail.legacy_question_ids) ||
    !nullableText(detail.label_provenance) ||
    !Array.isArray(detail.annotations) ||
    !Array.isArray(detail.attempts) ||
    !nullableText(detail.input_source) ||
    !text(data.case_input_hash) ||
    !nullableText(data.probabilities_unavailable_reason) ||
    !Array.isArray(data.probabilities)
  )
    return invalid();
  const annotations = detail.annotations.map((value) => {
    const annotation = object(value);
    if (
      !text(annotation.id) ||
      !text(annotation.note) ||
      !text(annotation.created_at)
    )
      return invalid();
    return {
      id: annotation.id,
      note: annotation.note,
      createdAt: annotation.created_at,
    };
  });
  const attempts = detail.attempts.map((value) => {
    const attempt = object(value);
    if (
      !text(attempt.attempt_id) ||
      !positiveCountText(attempt.number) ||
      !text(attempt.kind) ||
      !text(attempt.state) ||
      !text(attempt.request_body_hash) ||
      !nullableText(attempt.error_code) ||
      !nullableText(attempt.error_reason) ||
      !nullableTextWhenPresent(attempt.request_body_source) ||
      !nullableTextWhenPresent(attempt.response_source)
    )
      return invalid();
    return {
      attemptId: attempt.attempt_id,
      number: attempt.number,
      kind: attempt.kind,
      state: attempt.state,
      requestBodyHash: attempt.request_body_hash,
      errorCode: attempt.error_code,
      errorReason: attempt.error_reason,
      requestBodySource: attempt.request_body_source ?? null,
      responseSource: attempt.response_source ?? null,
    };
  });
  const probabilities = data.probabilities.map((value) => {
    const probability = object(value);
    if (
      !text(probability.option_id) ||
      !text(probability.option_name) ||
      typeof probability.probability !== "string" ||
      !/^(?:0(?:\.[0-9]+)?|1(?:\.0+)?)$/.test(probability.probability)
    )
      return invalid();
    return {
      optionId: probability.option_id,
      optionName: probability.option_name,
      probability: probability.probability,
    };
  });
  const context = resultContext(data.context);
  if (
    context.runId !== detail.run_id ||
    context.resultSnapshotId !== detail.result_snapshot_id ||
    context.labelSnapshotId !== detail.label_snapshot_id ||
    context.evaluationId !== detail.evaluation_id
  )
    return invalid();
  return {
    ...row,
    context,
    caseInputHash: data.case_input_hash,
    probabilities,
    probabilitiesUnavailableReason: data.probabilities_unavailable_reason,
    runId: detail.run_id,
    resultSnapshotId: detail.result_snapshot_id,
    labelSnapshotId: detail.label_snapshot_id,
    evaluationId: detail.evaluation_id,
    questionId: detail.question_id,
    answer: nullableTextRecord(detail.answer),
    legacyQuestionIds: detail.legacy_question_ids,
    legacyExpectedOptionIds: detail.legacy_expected_option_ids,
    legacyExclusionReasons: detail.legacy_exclusion_reasons,
    labelProvenance: detail.label_provenance,
    annotations,
    attempts,
    inputSource: detail.input_source,
  };
}
