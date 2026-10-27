"""Bound experiment result records before and after provider dispatch."""

from deykit.contracts.json_value import RECORD_LIMITS, dump_json
from deykit.contracts.records import CaseResult, NormalizedAnswer

# Leave room for the snapshot envelope and per-result separators.
MAX_EXPERIMENT_RESULT_BYTES = RECORD_LIMITS.max_bytes - 4096
MAX_NONANSWER_RESULT_BYTES = 1024


def experiment_nonanswer_result_limit(case_count: int) -> int:
    return min(MAX_NONANSWER_RESULT_BYTES, MAX_EXPERIMENT_RESULT_BYTES // max(1, case_count)) - 1


def experiment_case_result_limit(case_count: int, max_attempts: int) -> int:
    count = max(1, case_count)
    baseline = min(MAX_NONANSWER_RESULT_BYTES, MAX_EXPERIMENT_RESULT_BYTES // count)
    available = max(0, MAX_EXPERIMENT_RESULT_BYTES - baseline * count)
    possible_answers = max(1, min(count, max_attempts))
    return baseline + available // possible_answers - 1


def result_size(result: CaseResult) -> int:
    return len(result.model_dump_json().encode("utf-8"))


def minimum_dense_result_size(case_id: str, question_id: str, option_ids: tuple[str, ...]) -> int:
    probabilities = dump_json({option: int(index == 0) for index, option in enumerate(option_ids)})
    answer = NormalizedAnswer(
        question_id=question_id,
        option_id=max(option_ids, key=len),
        probabilities_source=probabilities,
    )
    return result_size(
        CaseResult(
            case_id=case_id,
            input_hash="0" * 64,
            status="valid",
            attempt_id="a" * 128,
            answer=answer,
        )
    )
