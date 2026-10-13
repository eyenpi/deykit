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
const attemptMetadata = {
  attempt_id: "attempt-1",
  number: "1",
  kind: "fixture",
  state: "completed",
  request_body_hash: "a".repeat(64),
  error_code: null,
  error_reason: null,
} as const;
const attemptSource = {
  ...attemptMetadata,
  request_body_source: exactRequest,
  response_source: '{"answer":"option-1"}',
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
  annotation_count: "0",
  question_id: "question-1",
  answer: answerSource,
  legacy_question_ids: [],
  legacy_expected_option_ids: [],
  legacy_exclusion_reasons: [],
  label_provenance: "authored",
  annotations: [],
  attempts: [attemptSource],
  input_source: exactInput,
};

function detailData(
  source: ApiOperationData<"readResult">["source"] = caseDetailSource,
  probabilities: ApiOperationData<"readResult">["probabilities"] = [],
): ApiOperationData<"readResult"> {
  return {
    schema_version: 1,
    source,
    case_input_hash: "b".repeat(64),
    context: {
      run_id: "run-1",
      evaluation_id: "evaluation-1",
      result_snapshot_id: "result-snapshot-1",
      result_content_hash: "c".repeat(64),
      label_snapshot_id: "label-snapshot-1",
      label_content_hash: "d".repeat(64),
      decision_id: "decision-1",
      decision_revision_id: "revision-1",
      decision_definition_hash: "e".repeat(64),
      dataset_id: "dataset-1",
      dataset_snapshot_id: "dataset-snapshot-1",
      dataset_content_hash: "f".repeat(64),
      evaluation_mode: "original",
      through_event_sequence: "1",
    },
    probabilities,
    probabilities_unavailable_reason: "probabilities_not_provided",
  };
}

const caseDetailData = detailData();

describe("execution evidence source projection", () => {
  it("retains opaque sanitized strings byte-for-byte and keeps source distinct from hashes", () => {
    const detail = decodeCaseDetail(caseDetailData);
    expect(detail.inputSource).toBe(exactInput);
    expect(detail.attempts[0]?.requestBodySource).toBe(exactRequest);
    expect(detail.attempts[0]?.requestBodyHash).toBe("a".repeat(64));
    expect(detail.answer?.native_confidence_source).toBeNull();
    expect(detail.setCorrect).toBe(true);
    expect(detail.caseInputHash).toBe("b".repeat(64));
    expect(detail.context.resultContentHash).toBe("c".repeat(64));
    expect(detail.probabilitiesUnavailableReason).toBe(
      "probabilities_not_provided",
    );
  });

  it("ignores supplemental answer properties but still validates required fields", () => {
    const withSupplement = detailData({
      ...caseDetailSource,
      answer: {
        ...answerSource,
        supplemental_source: '{"extension":9007199254740993}',
      },
    });
    const detail = decodeCaseDetail(withSupplement);
    expect(detail.answer).toEqual(answerSource);
    expect(Object.keys(detail.answer ?? {})).not.toContain(
      "supplemental_source",
    );

    const malformed = detailData({
      ...caseDetailSource,
      answer: { ...answerSource, reported_model: 17 },
    });
    expect(() => decodeCaseDetail(malformed)).toThrowError(
      expect.objectContaining({ code: "response_invalid" }),
    );
  });

  it("keeps server probability decimals as exact text and validates context association", () => {
    const probabilities = [
      { option_id: "option-1", option_name: "Question", probability: "0.62" },
      { option_id: "option-2", option_name: "Request", probability: "0.14" },
    ] satisfies ApiOperationData<"readResult">["probabilities"];
    const detail = decodeCaseDetail(
      detailData(caseDetailSource, probabilities),
    );
    expect(detail.probabilities.map((row) => row.probability)).toEqual([
      "0.62",
      "0.14",
    ]);
    expect(() =>
      decodeCaseDetail({
        ...detailData(),
        context: { ...detailData().context, label_snapshot_id: "other-label" },
      }),
    ).toThrowError(expect.objectContaining({ code: "response_invalid" }));
    expect(() =>
      decodeCaseDetail(
        detailData(caseDetailSource, [
          {
            option_id: "option-1",
            option_name: "Question",
            probability: "1.01",
          },
        ]),
      ),
    ).toThrowError(expect.objectContaining({ code: "response_invalid" }));
  });

  it("accepts omitted request and response sources for opt-in projections", () => {
    const metadataOnly = decodeCaseDetail(
      detailData({ ...caseDetailSource, attempts: [attemptMetadata] }),
    );
    expect(metadataOnly.attempts[0]?.requestBodySource).toBeNull();
    expect(metadataOnly.attempts[0]?.responseSource).toBeNull();

    const undefinedSources = decodeCaseDetail(
      detailData({
        ...caseDetailSource,
        attempts: [
          {
            ...attemptMetadata,
            request_body_source: undefined,
            response_source: undefined,
          },
        ],
      }),
    );
    expect(undefinedSources.attempts[0]?.requestBodySource).toBeNull();
    expect(undefinedSources.attempts[0]?.responseSource).toBeNull();

    const requestOnly = decodeCaseDetail(
      detailData({
        ...caseDetailSource,
        attempts: [{ ...attemptMetadata, request_body_source: exactRequest }],
      }),
    );
    expect(requestOnly.attempts[0]?.requestBodySource).toBe(exactRequest);
    expect(requestOnly.attempts[0]?.responseSource).toBeNull();

    const responseOnly = decodeCaseDetail(
      detailData({
        ...caseDetailSource,
        attempts: [
          { ...attemptMetadata, response_source: '{"answer":"option-1"}' },
        ],
      }),
    );
    expect(responseOnly.attempts[0]?.requestBodySource).toBeNull();
    expect(responseOnly.attempts[0]?.responseSource).toBe(
      '{"answer":"option-1"}',
    );
  });

  it("rejects malformed request or response source values when present", () => {
    for (const value of [0, false, {}, []]) {
      expect(() =>
        decodeCaseDetail(
          detailData({
            ...caseDetailSource,
            attempts: [{ ...attemptMetadata, request_body_source: value }],
          }),
        ),
      ).toThrowError(expect.objectContaining({ code: "response_invalid" }));
      expect(() =>
        decodeCaseDetail(
          detailData({
            ...caseDetailSource,
            attempts: [{ ...attemptMetadata, response_source: value }],
          }),
        ),
      ).toThrowError(expect.objectContaining({ code: "response_invalid" }));
    }
  });

  it("preserves exact large API count text without numeric conversion", () => {
    const exactCount = "9007199254740993";
    const detail = decodeCaseDetail(
      detailData({
        ...caseDetailSource,
        annotation_count: exactCount,
        attempts: [{ ...attemptSource, number: exactCount }],
      }),
    );
    expect(detail.annotationCount).toBe(exactCount);
    expect(detail.attempts[0]?.number).toBe(exactCount);
  });

  it("accepts zero annotations but rejects zero attempt numbers", () => {
    expect(decodeResultRow(caseDetailSource).annotationCount).toBe("0");
    expect(() =>
      decodeCaseDetail(
        detailData({
          ...caseDetailSource,
          attempts: [{ ...attemptSource, number: "0" }],
        }),
      ),
    ).toThrowError(expect.objectContaining({ code: "response_invalid" }));
  });

  it("rejects noncanonical or nontext count values", () => {
    const malformedValues: unknown[] = [
      0,
      1,
      1.5,
      -1,
      Number.POSITIVE_INFINITY,
      Number.NaN,
      null,
      undefined,
      "-1",
      "+1",
      "01",
      "1.0",
      "Infinity",
    ];
    for (const value of malformedValues) {
      expect(() =>
        decodeResultRow({ ...caseDetailSource, annotation_count: value }),
      ).toThrowError(expect.objectContaining({ code: "response_invalid" }));
      expect(() =>
        decodeCaseDetail(
          detailData({
            ...caseDetailSource,
            attempts: [{ ...attemptSource, number: value }],
          }),
        ),
      ).toThrowError(expect.objectContaining({ code: "response_invalid" }));
    }
  });
});
