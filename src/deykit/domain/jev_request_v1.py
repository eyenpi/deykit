"""Frozen Jev v1 request validation over in-memory evidence."""

from collections.abc import Callable

from deykit.contracts.json_value import JsonValue, parse_json
from deykit.contracts.records import ChoiceOption, ChoiceQuestion, CompiledRequest
from deykit.domain.choice_response import ResponseInvalid
from deykit.domain.choice_response import object_value_v1 as _object


def verify_request_v1(
    request: CompiledRequest,
    *,
    verify_images: Callable[[dict[str, JsonValue], str], None] | None = None,
) -> None:
    """Validate v1 requests; image support requires an explicit image verifier."""
    try:
        CompiledRequest.model_validate(request.model_dump())
        root = _object(parse_json(request.body, request.body_limits), "invalid_request")
        expected = {"state", "model", "questions"}
        if "assets" in root:
            expected.add("assets")
        if set(root) != expected:
            raise ValueError
        if "assets" in root:
            if verify_images is None:
                raise ValueError
            verify_images(root, request.semantic_headers_source)
        elif request.semantic_headers_source != "{}":
            raise ValueError
        if root["model"] != request.requested_model or not isinstance(root["state"], (str, dict)):
            raise ValueError
        questions = _object(root["questions"], "invalid_request")
        if len(questions) != 1:
            raise ValueError
        question_id = next(iter(questions))
        question = _object(questions[question_id], "invalid_request")
        if set(question) != {"type", "instructions", "criteria"} or question["type"] != "choice":
            raise ValueError
        criteria = _object(question["criteria"], "invalid_request")
        if not 2 <= len(criteria) <= 255:
            raise ValueError
        options = []
        for key, value in criteria.items():
            option = _object(value, "invalid_request")
            if set(option) != {"name", "description"}:
                raise ValueError
            options.append(ChoiceOption.model_validate({"id": key, **option}))
        ChoiceQuestion.model_validate(
            {"id": question_id, "instructions": question["instructions"], "options": tuple(options)}
        )
    except ValueError:
        raise ResponseInvalid("invalid_request") from None
