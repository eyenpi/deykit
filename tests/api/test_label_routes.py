"""Focused transport boundaries for unchanged label review edits."""

from deykit.api.dto.labels import LabelBatchRequest, LabelEditDTO, LabelReviewDTO
from deykit.api.routes.labels import _edit


def test_label_edit_preserves_review_tokens_provenance_note_and_empty_set() -> None:
    request = LabelBatchRequest(
        schema_version=1,
        operation_id="label-save",
        edits=(
            LabelEditDTO(
                review=LabelReviewDTO(
                    decision_id="decision-1",
                    dataset_id="dataset-1",
                    case_id="case-1",
                    question_id="question-1",
                    input_hash="a" * 64,
                    decision_etag="b" * 64,
                    draft_etag="c" * 64,
                    label_etag="d" * 64,
                ),
                action="set",
                acceptable_option_ids=(),
                provenance="authored_fixture",
                note="reviewed source note",
            ),
        ),
    )

    edit = _edit(request.edits[0])
    assert edit.action == "set"
    assert edit.acceptable_option_ids == ()
    assert edit.provenance == "authored_fixture"
    assert edit.note == "reviewed source note"
    assert edit.review.label_etag == "d" * 64


def test_label_edit_does_not_coerce_null_option_set_to_clear() -> None:
    request = LabelEditDTO(
        review=LabelReviewDTO(
            decision_id="decision-1",
            dataset_id="dataset-1",
            case_id="case-1",
            question_id="question-1",
            input_hash="a" * 64,
            decision_etag="b" * 64,
            draft_etag="c" * 64,
            label_etag=None,
        ),
        action="set",
        acceptable_option_ids=(),
    )

    edit = _edit(request)
    assert edit.action == "set"
    assert edit.acceptable_option_ids == ()
    assert edit.action != "clear"


def test_label_batch_json_arrays_are_admitted_without_losing_tokens() -> None:
    request = LabelBatchRequest.model_validate(
        {
            "schema_version": 1,
            "operation_id": "label-save",
            "edits": [
                {
                    "review": {
                        "decision_id": "decision-1",
                        "dataset_id": "dataset-1",
                        "case_id": "case-1",
                        "question_id": "question-1",
                        "input_hash": "a" * 64,
                        "decision_etag": "b" * 64,
                        "draft_etag": "c" * 64,
                        "label_etag": None,
                    },
                    "action": "set",
                    "acceptable_option_ids": ["option-a", "option-b"],
                    "provenance": "human",
                    "note": "human review",
                }
            ],
        }
    )

    edit = _edit(request.edits[0])
    assert edit.acceptable_option_ids == ("option-a", "option-b")
    assert edit.provenance == "human"
    assert edit.note == "human review"
