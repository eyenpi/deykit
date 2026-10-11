import { ApiError, object } from "../../api/client";
import type { ApiOperationData } from "../../api/client";

type ResultRowSource = ApiOperationData<"listResults">["items"][number]["source"];
type CaseDetailSource = ApiOperationData<"readResult">["source"];

export interface ResultRowView {
  caseId: string;
  split: string;
  tags: readonly string[];
  status: string;
  answerOptionId: string | null;
  expectedOptionIds: readonly string[];
  setCorrect: boolean | null;
  exclusionReasons: readonly string[];
  annotationCount: number;
}

export interface CaseDetailView extends ResultRowView {
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
  number: number;
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

function textList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(text);
}

function textLists(value: unknown): value is string[][] {
  return Array.isArray(value) && value.every(textList);
}

function booleanOrNull(value: unknown): value is boolean | null {
  return value === null || typeof value === "boolean";
}

function safeCount(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
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
    !safeCount(row.annotation_count)
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
  const required = [
    "option_id",
    "question_id",
    "probabilities_source",
    "native_confidence_source",
    "native_confidence_semantics",
    "reported_model",
  ] as const;
  if (
    Reflect.ownKeys(answer).some(
      (key) => typeof key !== "string" || !required.includes(key as (typeof required)[number]),
    ) ||
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

export function decodeCaseDetail(source: CaseDetailSource): CaseDetailView {
  const detail = object(source);
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
    !nullableText(detail.input_source)
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
      !safeCount(attempt.number) ||
      !text(attempt.kind) ||
      !text(attempt.state) ||
      !text(attempt.request_body_hash) ||
      !nullableText(attempt.error_code) ||
      !nullableText(attempt.error_reason) ||
      !nullableText(attempt.request_body_source) ||
      !nullableText(attempt.response_source)
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
      requestBodySource: attempt.request_body_source,
      responseSource: attempt.response_source,
    };
  });
  return {
    ...row,
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
