import { describe, expect, it } from "vitest";
import type { ApiOperationData } from "../../api/client";
import { decodeCaseDetail, decodeResultRow } from "./execution-inspection";

const exactInput = '{"large":9007199254740993,"fraction":1.2300}';
const exactRequest = '{"value":9007199254740993}';
const answerSource = {
  option_id: "option-1",
  question_id: "question-1",
  probabilities_source: null,
  native_confidence_source: null,
  native_confidence_semantics: null,
  reported_model: "fixture-model",
} as const;

const caseDetailSource: ApiOperationData<"readResult">["source"] = {
  run_id: "run-1",
  result_snapshot_id: "result-snapshot-1",
  label_snapshot_id: "label-snapshot-1",
  evaluation_id: "evaluation-1",
  case_id: "case-1",
  split: "development",
  tags: ["authored"],
  status: "valid",
  answer_option_id: "option-1",
  expected_option_ids: ["option-1"],
  set_correct: true,
  exclusion_reasons: [],
  annotation_count: 0,
  question_id: "question-1",
  answer: answerSource,
  legacy_question_ids: [],
  legacy_expected_option_ids: [],
  legacy_exclusion_reasons: [],
  label_provenance: "authored",
  annotations: [],
  attempts: [
    {
      attempt_id: "attempt-1",
      number: 1,
      kind: "fixture",
      state: "completed",
      request_body_hash: "a".repeat(64),
      error_code: null,
      error_reason: null,
      request_body_source: exactRequest,
      response_source: "{\"answer\":\"option-1\"}",
    },
  ],
  input_source: exactInput,
};

describe("execution evidence source projection", () => {
  it("retains opaque sanitized strings byte-for-byte and keeps source distinct from hashes", () => {
    const detail = decodeCaseDetail(caseDetailSource);
    expect(detail.inputSource).toBe(exactInput);
    expect(detail.attempts[0]?.requestBodySource).toBe(exactRequest);
    expect(detail.attempts[0]?.requestBodyHash).toBe("a".repeat(64));
    expect(detail.answer?.native_confidence_source).toBeNull();
    expect(detail.setCorrect).toBe(true);
  });

  it("ignores supplemental answer properties but still validates required fields", () => {
    const withSupplement = {
      ...caseDetailSource,
      answer: {
        ...answerSource,
        supplemental_source: '{"extension":9007199254740993}',
      },
    };
    const detail = decodeCaseDetail(withSupplement);
    expect(detail.answer).toEqual(answerSource);
    expect(Object.keys(detail.answer ?? {})).not.toContain("supplemental_source");

    const malformed = {
      ...caseDetailSource,
      answer: { ...answerSource, reported_model: 17 },
    };
    expect(() => decodeCaseDetail(malformed)).toThrowError(
      expect.objectContaining({ code: "response_invalid" }),
    );
  });

  it("fails closed when a required service count is not a safe integer", () => {
    const malformed = {
      ...caseDetailSource,
      annotation_count: "9007199254740993",
    };
    expect(() => decodeResultRow(malformed)).toThrowError(
      expect.objectContaining({ code: "response_invalid" }),
    );
  });
});
