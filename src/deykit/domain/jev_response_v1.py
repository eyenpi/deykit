"""Frozen Jev v1 response rules for strict and category-only evidence."""

import re
from collections.abc import Callable

from deykit.contracts.json_value import JsonValue, dump_json, parse_json
from deykit.contracts.records import ChoiceQuestion, CompiledRequest, NormalizedAnswer
from deykit.domain.choice_response import ResponseInvalid, validate_distribution_v1
from deykit.domain.choice_response import object_value_v1 as _object
from deykit.domain.choice_response import probability_v1 as _probability
from deykit.domain.choice_response import usage_count_v1 as _usage
from deykit.domain.jev_request_v1 import verify_request_v1

MODEL_VERSION_V1 = re.compile(r"jev-[0-9]+\.[0-9]+\.[0-9]+(?:[-.][A-Za-z0-9]+)*\Z")
JEV_DESTINATION_V1 = "https://api.typesafe.ai/v1/systemone"


def validate_response_v1(
    request: CompiledRequest,
    source: str | bytes,
    *,
    verify_request: Callable[[CompiledRequest], None] = verify_request_v1,
) -> NormalizedAnswer:
    """Validate the saved v1 response; an adapter may also verify the request."""
    try:
        root = _object(parse_json(source), "object_required")
    except ValueError:
        raise ResponseInvalid("invalid_json") from None
    verify_request(request)
    compiled = _object(parse_json(request.body, request.body_limits), "invalid_request")
    questions = _object(compiled.get("questions"), "invalid_request")
    if len(questions) != 1:
        raise ResponseInvalid("invalid_request")
    question_id = next(iter(questions))
    criteria = _object(
        _object(questions[question_id], "invalid_request").get("criteria"), "invalid_request"
    )
    answers = _object(root.get("answers"), "missing_answers")
    if set(answers) != {question_id}:
        raise ResponseInvalid("question_mismatch")
    answer = _object(answers[question_id], "invalid_answer")
    if answer.get("type") != "choice":
        raise ResponseInvalid("type_mismatch")
    choice = answer.get("choice")
    if not isinstance(choice, str) or choice not in criteria:
        raise ResponseInvalid("unknown_option")
    probabilities = _object(answer.get("probabilities"), "missing_probabilities")
    if set(probabilities) != set(criteria):
        raise ResponseInvalid("probability_option_mismatch")
    numeric = {
        key: _probability(value, "invalid_probability") for key, value in probabilities.items()
    }
    validate_distribution_v1(numeric, choice)
    confidence, model = _remaining_fields_v1(request, root, answer)
    return NormalizedAnswer(
        question_id=question_id,
        option_id=choice,
        probabilities_source=dump_json(probabilities),
        native_confidence_source=dump_json(confidence),
        native_confidence_semantics="jev_native_distribution_confidence",
        reported_model=model,
    )


def _remaining_fields_v1(
    request: CompiledRequest, root: dict[str, JsonValue], answer: dict[str, JsonValue]
) -> tuple[JsonValue, str]:
    confidence = _probability(answer.get("confidence"), "invalid_confidence")
    model = root.get("model")
    if not isinstance(model, str) or not MODEL_VERSION_V1.fullmatch(model):
        raise ResponseInvalid("invalid_model")
    if MODEL_VERSION_V1.fullmatch(request.requested_model) and model != request.requested_model:
        raise ResponseInvalid("model_pin_mismatch")
    usage = _object(root.get("usage"), "missing_usage")
    _usage(usage.get("input_tokens"))
    _usage(usage.get("output_tokens"))
    return confidence, model


_PROBABILITY_ERRORS_V1 = frozenset(
    {
        "missing_probabilities",
        "probability_option_mismatch",
        "invalid_probability",
        "invalid_probability_sum",
        "choice_not_argmax",
    }
)


def category_only_choice(
    request: CompiledRequest,
    source: str,
    saved_reason: str | None,
    *,
    expected_question: ChoiceQuestion,
    expected_order: tuple[str, ...],
    expected_input: JsonValue,
    has_selected_images: bool,
) -> str | None:
    """Apply the frozen category-only policy without changing strict evidence."""
    if (
        has_selected_images
        or request.adapter not in {"jev", "fixture"}
        or request.compiler != "jev-choice"
        or request.compiler_version != "1"
        or saved_reason not in _PROBABILITY_ERRORS_V1
    ):
        return None
    if request.adapter == "jev":
        if request.destination != JEV_DESTINATION_V1 or not (
            MODEL_VERSION_V1.fullmatch(request.requested_model)
            or request.requested_model in {"jev-latest", "jev-preview"}
        ):
            return None
    elif request.destination != "fixture:jev-choice" or (
        request.requested_model.strip() != request.requested_model
    ):
        return None
    try:
        validate_response_v1(request, source)
    except ResponseInvalid as error:
        if error.reason != saved_reason:
            return None
    except ValueError:
        return None
    else:
        return None
    try:
        root = _object(parse_json(source), "invalid_response")
        compiled = _object(parse_json(request.body, request.body_limits), "invalid_request")
        questions = _object(compiled.get("questions"), "invalid_request")
        question_id = next(iter(questions))
        question = _object(questions[question_id], "invalid_request")
        criteria = _object(question.get("criteria"), "invalid_request")
        if (
            question_id != expected_question.id
            or question.get("instructions") != expected_question.instructions
            or tuple(criteria) != expected_order
            or criteria
            != {
                option.id: {"name": option.name, "description": option.description}
                for option in expected_question.options
            }
            or dump_json(compiled.get("state")) != dump_json(expected_input)
        ):
            return None
        answers = _object(root.get("answers"), "missing_answers")
        answer = _object(answers.get(question_id), "invalid_answer")
        choice = answer.get("choice")
        if not isinstance(choice, str) or choice not in criteria:
            return None
        _remaining_fields_v1(request, root, answer)
        return choice
    except (ValueError, StopIteration):
        return None
