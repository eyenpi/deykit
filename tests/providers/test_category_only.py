"""A category-only policy cannot silently repair other response errors."""

from copy import deepcopy
from decimal import Decimal

import pytest
from test_choice import definition, request, valid

from deykit.contracts.json_value import bytes_hash, dump_json, parse_json
from deykit.contracts.records import ChoiceOption
from deykit.domain.jev_response_v1 import category_only_choice
from deykit.providers.choice import ResponseInvalid, validate_response


def selected_choice(request, source, reason, **expected):
    question = definition().questions[0]
    if "question" in expected:
        question = question.model_copy(update={"id": expected["question"]})
    if "options" in expected:
        existing = {option.id: option for option in question.options}
        options = tuple(
            existing.get(option_id) or ChoiceOption(id=option_id, name=option_id)
            for option_id in expected["options"]
        )
        question = question.model_copy(update={"options": options})
    return category_only_choice(
        request,
        source,
        reason,
        expected_question=question,
        expected_order=expected.get("order", tuple(option.id for option in question.options)),
        expected_input="Why?",
        has_selected_images=False,
    )


@pytest.mark.parametrize(
    ("probabilities", "reason"),
    [
        (None, "missing_probabilities"),
        ({"question": Decimal("1")}, "probability_option_mismatch"),
        ({"question": True, "report": False}, "invalid_probability"),
        ({"question": Decimal("0.8"), "report": Decimal("0.8")}, "invalid_probability_sum"),
        ({"question": Decimal("0.2"), "report": Decimal("0.8")}, "choice_not_argmax"),
    ],
)
def test_jev_category_only_accepts_explicit_choice_only_for_probability_failures(
    probabilities, reason
):
    wire = valid()
    wire["answers"]["category"]["probabilities"] = probabilities
    source = dump_json(wire)
    with pytest.raises(ResponseInvalid) as error:
        validate_response(request(), source)
    assert error.value.reason == reason
    assert selected_choice(request(), source, reason) == "question"
    assert source == dump_json(wire)


@pytest.mark.parametrize("damage", ["question", "choice", "confidence", "model", "usage"])
def test_jev_category_only_rejects_other_invalid_fields_even_with_bad_probabilities(damage):
    wire = deepcopy(valid())
    answer = wire["answers"]["category"]
    answer["probabilities"] = {"question": Decimal("0.8"), "report": Decimal("0.8")}
    if damage == "question":
        wire["answers"] = {"other": answer}
    elif damage == "choice":
        answer["choice"] = "unknown"
    elif damage == "confidence":
        answer["confidence"] = True
    elif damage == "model":
        wire["model"] = "unexpected-model"
    else:
        wire["usage"]["input_tokens"] = True
    assert selected_choice(request(), dump_json(wire), "invalid_probability_sum") is None


def test_jev_category_only_requires_matching_saved_probability_failure():
    wire = valid()
    wire["answers"]["category"]["probabilities"] = {
        "question": Decimal("0.8"),
        "report": Decimal("0.8"),
    }
    source = dump_json(wire)
    assert selected_choice(request(), source, "invalid_probability") is None
    assert selected_choice(request(), dump_json(valid()), "invalid_probability_sum") is None
    assert (
        selected_choice(
            request().model_copy(update={"adapter": "openai"}), source, "invalid_probability_sum"
        )
        is None
    )
    assert selected_choice(request(), source, "invalid_probability_sum", question="other") is None
    assert (
        selected_choice(request(), source, "invalid_probability_sum", options=("question", "other"))
        is None
    )


def test_category_only_accepts_response_at_source_size_limit():
    wire = valid()
    wire["answers"]["category"]["probabilities"] = None
    wire["unused"] = ""
    padding = 1_048_576 - len(dump_json(wire).encode())
    wire["unused"] = "x" * padding
    source = dump_json(wire)
    assert len(source.encode()) == 1_048_576
    with pytest.raises(ResponseInvalid) as error:
        validate_response(request(), source)
    assert error.value.reason == "missing_probabilities"
    assert selected_choice(request(), source, "missing_probabilities") == "question"


def test_category_only_v1_is_independent_of_current_compiler_version(monkeypatch):
    wire = valid()
    wire["answers"]["category"]["probabilities"] = None
    compiled = request()
    monkeypatch.setattr("deykit.providers.choice.COMPILER_VERSION", "2")

    def future_validator(*args):
        raise AssertionError("The frozen v1 policy must not call a future validator")

    monkeypatch.setattr("deykit.providers.choice.validate_response", future_validator)
    assert selected_choice(compiled, dump_json(wire), "missing_probabilities") == "question"


def test_category_only_v1_is_independent_of_current_probability_tolerance(monkeypatch):
    wire = valid()
    wire["answers"]["category"]["probabilities"] = {
        "question": Decimal("0.500002"),
        "report": Decimal("0.5"),
    }
    source = dump_json(wire)
    with pytest.raises(ResponseInvalid) as error:
        validate_response(request(), source)
    assert error.value.reason == "invalid_probability_sum"
    monkeypatch.setattr("deykit.providers.response.TOLERANCE", Decimal("0.01"))
    assert selected_choice(request(), source, "invalid_probability_sum") == "question"


def test_category_only_rejects_saved_error_for_an_invalid_compiled_request():
    wire = valid()
    wire["answers"]["category"]["probabilities"] = {
        "question": Decimal("0.8"),
        "report": Decimal("0.8"),
    }
    compiled = request()
    body = parse_json(compiled.body)
    body["model"] = "jev-9.9.9"
    encoded = dump_json(body).encode()
    forged = compiled.model_copy(update={"body": encoded, "body_hash": bytes_hash(encoded)})
    with pytest.raises(ResponseInvalid) as error:
        validate_response(forged, dump_json(wire))
    assert error.value.reason == "invalid_request"
    assert selected_choice(forged, dump_json(wire), "invalid_probability_sum") is None


@pytest.mark.parametrize("change", ["destination", "model", "instructions", "option_name", "input"])
def test_category_only_requires_frozen_jev_profile_and_request_semantics(change):
    wire = valid()
    wire["answers"]["category"]["probabilities"] = {
        "question": Decimal("0.8"),
        "report": Decimal("0.8"),
    }
    compiled = request()
    body = parse_json(compiled.body)
    updates = {}
    if change == "destination":
        updates["destination"] = "https://example.invalid/not-jev"
    elif change == "model":
        body["model"] = "another-provider"
        updates["requested_model"] = "another-provider"
    elif change == "instructions":
        body["questions"]["category"]["instructions"] = "Choose the opposite category."
    elif change == "option_name":
        body["questions"]["category"]["criteria"]["question"]["name"] = "Observation"
    else:
        body["state"] = "A different input."
    encoded = dump_json(body).encode()
    updates.update(body=encoded, body_hash=bytes_hash(encoded))
    forged = compiled.model_copy(update=updates)
    assert selected_choice(forged, dump_json(wire), "invalid_probability_sum") is None


def test_category_only_requires_the_frozen_option_order():
    wire = valid()
    wire["answers"]["category"]["probabilities"] = None
    compiled = request()
    body = parse_json(compiled.body)
    criteria = body["questions"]["category"]["criteria"]
    body["questions"]["category"]["criteria"] = dict(reversed(tuple(criteria.items())))
    encoded = dump_json(body).encode()
    changed = compiled.model_copy(update={"body": encoded, "body_hash": bytes_hash(encoded)})
    assert selected_choice(changed, dump_json(wire), "missing_probabilities") is None
    assert (
        selected_choice(
            changed, dump_json(wire), "missing_probabilities", order=("report", "question")
        )
        == "question"
    )
