"""Authored fixture bindings are exact request evidence, never live observations."""

import asyncio

import pytest
from pydantic import ValidationError

from deykit.contracts.errors import ServiceError
from deykit.contracts.records import (
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    CompiledRequest,
    FixtureBinding,
    FixtureSet,
    NormalizedAnswer,
    ProviderProfile,
)
from deykit.providers.choice import compile_choice
from deykit.providers.fixtures import (
    FixtureInvalid,
    FixtureTransportFactory,
    fixture_set_hash,
)

MODEL = "authored-test-v1"
STAMP = "2026-10-05T12:00:00Z"


def choice(*, instructions="Choose", order=("yes", "no")):
    return ChoiceDefinition(
        input_kind="json",
        selected_fields=("text",),
        questions=(
            ChoiceQuestion(
                id="q",
                instructions=instructions,
                options=tuple(ChoiceOption(id=option, name=option) for option in order),
            ),
        ),
    )


def request(*, instructions="Choose", order=("yes", "no"), text="hello"):
    return compile_choice(
        choice(instructions=instructions, order=order), {"text": text}, MODEL, adapter="fixture"
    )


def answer(option="yes", *, probabilities=None, confidence=None):
    return NormalizedAnswer(
        question_id="q",
        option_id=option,
        probabilities_source=probabilities,
        native_confidence_source=confidence,
        native_confidence_semantics="authored_fixture_confidence" if confidence else None,
        reported_model=MODEL,
    )


def fixture_set(*bindings):
    values = dict(
        id="set",
        decision_id="d",
        dataset_id="data",
        name="Authored examples",
        model_identity=MODEL,
        bindings=tuple(bindings),
        created_at=STAMP,
    )
    incomplete = FixtureSet(**values, content_hash="0" * 64)
    return FixtureSet(**values, content_hash=fixture_set_hash(incomplete))


def dispatch(factory, case_id, compiled):
    return asyncio.run(factory.for_case(case_id).dispatch(compiled, timeout_seconds=1.0))


def test_identical_wire_request_can_have_different_case_answers():
    compiled = request()
    fixtures = fixture_set(
        FixtureBinding(id="one", case_id="case-one", request=compiled, answer=answer("yes")),
        FixtureBinding(id="two", case_id="case-two", request=compiled, answer=answer("no")),
    )
    factory = FixtureTransportFactory(fixtures)
    assert dispatch(factory, "case-one", compiled).answer.option_id == "yes"
    assert dispatch(factory, "case-two", compiled).answer.option_id == "no"
    missing = dispatch(factory, "case-three", compiled)
    assert missing.state == "not_sent"
    assert missing.error.code == "missing_fixture"


def test_question_order_model_and_input_edits_are_missing_fixtures():
    compiled = request()
    factory = FixtureTransportFactory(
        fixture_set(FixtureBinding(id="bound", case_id="case", request=compiled, answer=answer()))
    )
    for edited in (
        request(instructions="Changed"),
        request(order=("no", "yes")),
        request(text="different"),
        request().model_copy(update={"compiler_version": "2"}),
        compile_choice(choice(), {"text": "hello"}, "authored-other", adapter="fixture"),
    ):
        assert edited.body_hash != compiled.body_hash or edited.compiler_version != (
            compiled.compiler_version
        )
        result = dispatch(factory, "case", edited)
        assert result.state == "not_sent" and result.error.code == "missing_fixture"


def test_optional_generic_fields_and_explicit_authored_error():
    compiled = request()
    fixtures = fixture_set(
        FixtureBinding(id="plain", case_id="plain", request=compiled, answer=answer()),
        FixtureBinding(
            id="probabilities",
            case_id="probabilities",
            request=compiled,
            answer=answer(probabilities='{"yes":0.8,"no":0.2}', confidence="0.7"),
        ),
        FixtureBinding(
            id="response-error",
            case_id="response-error",
            request=compiled,
            error=ServiceError(code="response_invalid", reason="authored_response_error"),
        ),
    )
    factory = FixtureTransportFactory(fixtures)
    plain = dispatch(factory, "plain", compiled)
    assert plain.answer.probabilities_source is None
    assert plain.answer.native_confidence_source is None
    probabilistic = dispatch(factory, "probabilities", compiled)
    assert probabilistic.answer.probabilities_source == '{"yes":0.8,"no":0.2}'
    assert probabilistic.answer.native_confidence_semantics == "authored_fixture_confidence"
    errored = dispatch(factory, "response-error", compiled)
    assert errored.state == "known" and errored.error.code == "response_invalid"


@pytest.mark.parametrize(
    "bad_answer,reason",
    [
        (
            NormalizedAnswer(question_id="wrong", option_id="yes", reported_model=MODEL),
            "fixture_question_mismatch",
        ),
        (
            NormalizedAnswer(question_id="q", option_id="unknown", reported_model=MODEL),
            "fixture_unknown_option",
        ),
        (
            NormalizedAnswer(question_id="q", option_id="yes", reported_model="authored-other"),
            "fixture_model_mismatch",
        ),
        (answer(probabilities='{"yes":0.8}'), "fixture_probability_options"),
        (answer(probabilities='{"yes":0.7,"no":0.2}'), "fixture_probability_sum"),
        (answer(probabilities='{"yes":0.2,"no":0.8}'), "fixture_choice_not_argmax"),
        (answer(confidence="1.5"), "invalid_authored_confidence"),
    ],
)
def test_malformed_generic_answers_reject_before_transport(bad_answer, reason):
    compiled = request()
    fixtures = fixture_set(
        FixtureBinding(id="bad", case_id="case", request=compiled, answer=bad_answer)
    )
    with pytest.raises(FixtureInvalid, match=reason):
        FixtureTransportFactory(fixtures)


def test_nonfinite_authored_distribution_rejects_at_record_boundary():
    with pytest.raises(ValidationError):
        answer(probabilities='{"yes":NaN,"no":0.2}')


def test_invalid_compiled_request_and_duplicate_binding_reject():
    compiled = request()
    bad = CompiledRequest.model_construct(
        adapter="fixture",
        compiler="jev-choice",
        compiler_version="1",
        requested_model=MODEL,
        destination="fixture:jev-choice",
        body=b"{}",
        body_hash=compiled.body_hash,
    )
    binding = FixtureBinding(id="one", case_id="case", request=compiled, answer=answer())
    factory = FixtureTransportFactory(fixture_set(binding))
    invalid = dispatch(factory, "case", bad)
    assert invalid.state == "not_sent" and invalid.error.code == "preflight_failed"
    with pytest.raises(ValidationError, match="request_body_hash_mismatch"):
        FixtureBinding(id="bad", case_id="case", request=bad, answer=answer())
    with pytest.raises(ValidationError, match="duplicate_fixture_request_binding"):
        fixture_set(
            binding, FixtureBinding(id="two", case_id="case", request=compiled, answer=answer())
        )


def test_profile_identity_and_malformed_constructed_models_are_rejected_safely():
    compiled = request()
    fixtures = fixture_set(
        FixtureBinding(id="bound", case_id="case", request=compiled, answer=answer())
    )
    profile = ProviderProfile(
        id="fixture-profile",
        adapter="fixture",
        requested_model=MODEL,
        destination="fixture:jev-choice",
    )
    assert dispatch(FixtureTransportFactory(fixtures, profile), "case", compiled).answer is not None
    for mismatched in (
        profile.model_copy(update={"adapter": "jev"}),
        profile.model_copy(update={"destination": "https://example.test"}),
        profile.model_copy(update={"requested_model": "authored-other"}),
        profile.model_copy(update={"credential_ref": "secret"}),
        profile.model_copy(update={"schema_version": True}),
    ):
        with pytest.raises(FixtureInvalid, match="fixture_profile_identity"):
            FixtureTransportFactory(fixtures, mismatched)

    malformed = FixtureSet.model_construct(
        id="set", decision_id="d", dataset_id="data", bindings=(object(),)
    )
    with pytest.raises(FixtureInvalid, match="invalid_fixture_set"):
        FixtureTransportFactory(malformed)
    constructed_request = CompiledRequest.model_construct(
        adapter="fixture",
        compiler="jev-choice",
        compiler_version="1",
        requested_model=MODEL,
        destination="fixture:jev-choice",
        body=compiled.body,
        body_hash=compiled.body_hash,
        schema_version=True,
    )
    result = dispatch(FixtureTransportFactory(fixtures), "case", constructed_request)
    assert result.state == "not_sent" and result.error.code == "preflight_failed"
