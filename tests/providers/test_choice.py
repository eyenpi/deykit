from copy import deepcopy
from decimal import Decimal, localcontext
from hashlib import sha256
from pathlib import Path

import pytest

from deykit.contracts.json_value import dump_json, parse_json
from deykit.contracts.records import (
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    NormalizedAnswer,
)
from deykit.providers.choice import ResponseInvalid, compile_choice, validate_response

CORPUS = Path(__file__).parent / "corpus"


def definition(*, kind="text", fields=(), reverse=False):
    options = (
        ChoiceOption(id="question", name="Question", description=None),
        ChoiceOption(id="report", name="Observation", description=""),
    )
    return ChoiceDefinition(
        input_kind=kind,
        selected_fields=fields,
        questions=(
            ChoiceQuestion(
                id="category",
                instructions="Choose a category.",
                options=tuple(reversed(options)) if reverse else options,
            ),
        ),
    )


def request(model="jev-1.13.0"):
    return compile_choice(definition(), "Why?", model)


def valid():
    return parse_json((CORPUS / "valid-choice.json").read_bytes())


def test_a28_exact_bytes_stable_ids_names_and_empty_vs_absent_descriptions():
    compiled = request()
    expected = (
        b'{"state":"Why?","model":"jev-1.13.0","questions":{"category":'
        b'{"type":"choice","instructions":"Choose a category.","criteria":'
        b'{"question":{"name":"Question","description":null},'
        b'"report":{"name":"Observation","description":""}}}}}'
    )
    assert compiled.body == expected
    assert compiled.body_hash == sha256(expected).hexdigest()
    assert compiled.compiler == "jev-choice"
    assert compiled.compiler_version == "1"
    assert b"label" not in compiled.body
    reordered = compile_choice(definition(reverse=True), "Why?", "jev-1.13.0")
    assert reordered.body.index(b'"report"') < reordered.body.index(b'"question"')
    assert reordered.body_hash != compiled.body_hash


def test_exact_json_precision_nested_values_and_unselected_fields_rejected():
    source = '{"n":9007199254740993,"nested":{"v":0.1234567890123456789},"unicode":"é"}'
    compiled = compile_choice(
        definition(kind="json", fields=("n", "nested", "unicode")), parse_json(source), "jev-1.13.0"
    )
    assert b"9007199254740993" in compiled.body
    assert b"0.1234567890123456789" in compiled.body
    assert parse_json(compiled.body)["state"] == parse_json(source)
    with pytest.raises(ValueError, match="exactly"):
        compile_choice(definition(kind="json", fields=("n",)), parse_json(source), "jev-1.13.0")


def test_authored_compilation_is_distinct_but_same_choice_shape():
    compiled = compile_choice(definition(), "Why?", "authored-v1", adapter="fixture")
    assert compiled.adapter == "fixture"
    assert compiled.destination == "fixture:jev-choice"
    assert parse_json(compiled.body)["model"] == "authored-v1"
    assert compiled.body_hash != request().body_hash


def test_a29_valid_required_native_fields_usage_and_alias_movement():
    normalized = validate_response(request(), (CORPUS / "valid-choice.json").read_bytes())
    assert normalized.option_id == "question"
    assert normalized.reported_model == "jev-1.13.0"
    assert parse_json(normalized.native_confidence_source) == Decimal("0.6")
    wire = valid()
    wire["model"] = "jev-1.14.0"
    assert validate_response(request("jev-latest"), dump_json(wire)).reported_model == "jev-1.14.0"
    with pytest.raises(ResponseInvalid, match="model_pin_mismatch"):
        validate_response(request(), dump_json(wire))


@pytest.mark.parametrize("line", (CORPUS / "malformed-choice.jsonl").read_text().splitlines())
def test_authored_malformed_corpus(line):
    wire = parse_json(line)
    with pytest.raises(ResponseInvalid):
        validate_response(request(), dump_json(wire["response"]))


@pytest.mark.parametrize(
    "path,value",
    [
        (("model",), None),
        (("model",), "jev-latest"),
        (("usage",), None),
        (("usage", "input_tokens"), Decimal("1.5")),
        (("usage", "output_tokens"), -1),
        (("answers", "category", "type"), "noul"),
        (("answers", "category", "choice"), "unknown"),
        (("answers", "category", "confidence"), None),
        (("answers", "category", "confidence"), True),
        (("answers", "category", "confidence"), "0.6"),
        (("answers", "category", "confidence"), Decimal("1.000001")),
        (("answers", "category", "probabilities"), {"question": Decimal("1")}),
        (("answers", "category", "probabilities"), {"question": True, "report": False}),
        (
            ("answers", "category", "probabilities"),
            {"question": Decimal("1.1"), "report": Decimal("-0.1")},
        ),
    ],
)
def test_required_fields_are_strict(path, value):
    wire = deepcopy(valid())
    node = wire
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value
    with pytest.raises(ResponseInvalid):
        validate_response(request(), dump_json(wire))


@pytest.mark.parametrize(
    "wire",
    [
        b'{"model":"jev-1.13.0","model":"jev-1.13.0"}',
        b'{"x":NaN}',
        b"\xff",
        b'{"x":"\\ud800"}',
    ],
)
def test_invalid_source_json(wire):
    with pytest.raises(ResponseInvalid):
        validate_response(request(), wire)


def test_tolerance_no_renormalization_and_tied_argmax():
    wire = valid()
    wire["answers"]["category"]["probabilities"] = {
        "question": Decimal("0.4999995"),
        "report": Decimal("0.5000005"),
    }
    normalized = validate_response(request(), dump_json(wire))
    assert parse_json(normalized.probabilities_source)["question"] == Decimal("0.4999995")
    wire["answers"]["category"]["probabilities"]["report"] = Decimal("0.500000500000000000001")
    with localcontext() as context:
        context.prec = 6
        with pytest.raises(ResponseInvalid, match="choice_not_argmax"):
            validate_response(request(), dump_json(wire))


def test_generic_fixture_absent_native_fields_does_not_relax_jev():
    answer = NormalizedAnswer(question_id="category", option_id="question")
    assert answer.probabilities_source is None
    wire = valid()
    del wire["answers"]["category"]["confidence"]
    with pytest.raises(ResponseInvalid):
        validate_response(request(), dump_json(wire))


def test_maximum_admitted_state_remains_valid_inside_generated_request():
    from deykit.contracts.json_value import DEFAULT_LIMITS

    state = "x" * (DEFAULT_LIMITS.max_bytes - 2)
    compiled = compile_choice(definition(), state, "jev-1.13.0")
    assert len(compiled.body) > DEFAULT_LIMITS.max_bytes
    normalized = validate_response(compiled, (CORPUS / "valid-choice.json").read_bytes())
    assert normalized.option_id == "question"


def test_deep_admitted_state_preserves_generated_request_wrapper_budget():
    from deykit.contracts.json_value import DEFAULT_LIMITS

    state = parse_json(
        '{"nested":'
        + "[" * (DEFAULT_LIMITS.max_depth - 1)
        + "0"
        + "]" * (DEFAULT_LIMITS.max_depth - 1)
        + "}"
    )
    compiled = compile_choice(definition(kind="json", fields=("nested",)), state, "jev-1.13.0")
    normalized = validate_response(compiled, (CORPUS / "valid-choice.json").read_bytes())
    assert normalized.option_id == "question"
