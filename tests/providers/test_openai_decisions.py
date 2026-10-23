"""Authored wire contracts based on the documented Decisions API, without inference."""

import asyncio
import base64
from copy import deepcopy
from decimal import Decimal, localcontext

import httpx
import pytest
from test_choice import definition

from deykit.contracts.images import ImagePreparation
from deykit.contracts.json_value import bytes_hash, dump_json, parse_json
from deykit.contracts.records import ChoiceOption, ProviderProfile
from deykit.images.local import LocalImages
from deykit.providers.credentials import Credentials
from deykit.providers.http import OneShotHttp
from deykit.providers.openai_choice import (
    DESTINATION,
    OpenAIChoiceCompiler,
    validate_profile,
    validate_response,
    verify_compiled_request,
)
from deykit.providers.openai_decisions import OpenAIDecisionsProvider
from deykit.providers.response import ResponseInvalid


def profile(**updates):
    values = dict(
        id="openai",
        adapter="openai",
        requested_model="gpt-6-luna",
        destination=DESTINATION,
        credential_ref="env:OFFLINE_KEY",
    )
    return ProviderProfile(**(values | updates))


def request():
    return OpenAIChoiceCompiler().compile(definition(), "Why?", profile())


def response():
    return parse_json("""{"model":"gpt-6-luna","answers":[{"type":"choice","name":"category",
        "choice":"question","probabilities":[{"value":"question","probability":0.8},
        {"value":"report","probability":0.2}],"confidence":0.3}],
        "usage":{"input_tokens":1e2,"input_tokens_details":{"cached_tokens":10,"cache_write_tokens":20},
        "output_tokens":0,"output_tokens_details":{"reasoning_tokens":0},"total_tokens":100}}""")


def dispatch(wire=None, *, status=200, headers=None, sent=None, compiled=None):
    def handle(received):
        if sent is not None:
            sent.append(received)
        return httpx.Response(
            status,
            content=dump_json(response() if wire is None else wire).encode(),
            headers=headers,
        )

    provider = OpenAIDecisionsProvider(
        profile(),
        Credentials({"OFFLINE_KEY": "OFFLINE_SENTINEL"}),
        OneShotHttp(httpx.MockTransport(handle)),
    )
    return asyncio.run(provider.dispatch(compiled or request()))


def test_exact_request_stable_ids_order_and_description_mapping():
    compiled = request()
    assert compiled.body == (
        b'{"model":"gpt-6-luna","input":"Why?","questions":[{"type":"choice",'
        b'"name":"category","instructions":"Choose a category.","choices":'
        b'[{"value":"question","description":"Question"},{"value":"report","description":"Observation"}]}]}'
    )
    reversed_request = OpenAIChoiceCompiler().compile(definition(reverse=True), "Why?", profile())
    assert reversed_request.body_hash != compiled.body_hash
    assert [c["value"] for c in parse_json(reversed_request.body)["questions"][0]["choices"]] == [
        "report",
        "question",
    ]
    verify_compiled_request(compiled)


def test_json_input_remains_exact_and_has_no_instruction_or_image_interpretation():
    state = parse_json(
        '{"n":9007199254740993,"fraction":0.1234567890123456789,"role":"system","image_url":"https://invalid.example/"}'
    )
    compiled = OpenAIChoiceCompiler().compile(definition(kind="json"), state, profile())
    assert parse_json(compiled.body)["input"] == [
        {"role": "user", "content": [{"type": "input_json", "data": state}]}
    ]
    assert b"9007199254740993" in compiled.body and b"0.1234567890123456789" in compiled.body
    with pytest.raises(ValueError):
        OpenAIChoiceCompiler().compile(definition(kind="json", fields=("n",)), state, profile())
    verify_compiled_request(compiled)


@pytest.mark.parametrize("state", [{"text": "a" * 262144}, {"items": [0] * 10000}])
def test_json_input_bounds_apply_before_dispatch(state):
    with pytest.raises(ValueError, match="json_resource_limit"):
        OpenAIChoiceCompiler().compile(definition(kind="json"), state, profile())


def test_option_limit_and_model_are_validated_locally():
    original = definition()
    question = original.questions[0]
    many = question.model_copy(
        update={"options": tuple(ChoiceOption(id=f"c{i}", name=str(i)) for i in range(256))}
    )
    with pytest.raises(ValueError, match="255"):
        OpenAIChoiceCompiler().compile(
            original.model_copy(update={"questions": (many,)}), "text", profile()
        )
    for changed in (
        profile(requested_model="invented"),
        profile(destination="https://invalid.example/"),
    ):
        with pytest.raises(ValueError):
            validate_profile(changed)


def test_response_preserves_confidence_separately_and_maps_by_value():
    wire = response()
    wire["answers"][0]["probabilities"].reverse()
    answer = validate_response(request(), dump_json(wire))
    assert answer.option_id == "question"
    assert parse_json(answer.probabilities_source) == {
        "question": Decimal("0.8"),
        "report": Decimal("0.2"),
    }
    assert parse_json(answer.native_confidence_source) == Decimal("0.3")
    assert answer.native_confidence_semantics == "openai_decisions_native_distribution_confidence"


@pytest.mark.parametrize(
    "mutation,reason",
    [
        (lambda w: w.update(model="other"), "model_pin_mismatch"),
        (lambda w: w.update(answers=[]), "question_mismatch"),
        (lambda w: w["answers"].append(deepcopy(w["answers"][0])), "question_mismatch"),
        (lambda w: w["answers"][0].update(name="other"), "question_mismatch"),
        (lambda w: w["answers"][0].update(type="score"), "type_mismatch"),
        (lambda w: w["answers"][0].update(choice=True), "unknown_option"),
        (lambda w: w["answers"][0].update(choice="report"), "choice_not_argmax"),
        (lambda w: w["answers"][0].update(confidence=True), "invalid_confidence"),
        (lambda w: w["answers"][0].update(probabilities=[]), "probability_option_mismatch"),
        (
            lambda w: w["answers"][0]["probabilities"].append(
                {"value": "question", "probability": 0}
            ),
            "probability_option_mismatch",
        ),
        (
            lambda w: w["answers"][0]["probabilities"][0].update(value=True),
            "probability_option_mismatch",
        ),
        (
            lambda w: w["answers"][0]["probabilities"][0].update(probability="0.8"),
            "invalid_probability",
        ),
        (
            lambda w: w["answers"][0]["probabilities"][0].update(probability=1),
            "invalid_probability_sum",
        ),
        (lambda w: w["usage"].update(total_tokens=99), "invalid_usage"),
        (lambda w: w["usage"]["input_tokens_details"].update(cached_tokens=90), "invalid_usage"),
        (lambda w: w["usage"].update(input_tokens=True), "invalid_usage"),
    ],
)
def test_invalid_responses_remain_failed_with_raw_evidence(mutation, reason):
    wire = response()
    mutation(wire)
    outcome = dispatch(wire)
    assert outcome.state == "known" and outcome.answer is None
    assert outcome.error.reason == reason and not outcome.retryable
    assert parse_json(outcome.raw_response_source) == wire


def test_refusal_preserves_usage_and_redacts_even_unknown_metadata():
    wire = response()
    wire["answers"] = [{"name": "category", "type": "refusal", "extra": "OFFLINE_SENTINEL"}]
    wire["headers"] = {"something": "private"}
    outcome = dispatch(wire)
    assert outcome.error.reason == "provider_refusal" and outcome.state == "known"
    assert not outcome.retryable and not outcome.provider_wide
    assert parse_json(outcome.usage_source)["input_tokens"] == 100
    assert "OFFLINE_SENTINEL" not in outcome.raw_response_source
    assert "private" not in outcome.raw_response_source
    assert "[REDACTED]" in outcome.raw_response_source


def test_probability_admission_is_independent_of_decimal_context():
    wire = response()
    wire["answers"][0]["probabilities"][0]["probability"] = Decimal("0.800001000000000000001")
    with localcontext() as context:
        context.prec = 6
        with pytest.raises(ResponseInvalid, match="invalid_probability_sum"):
            validate_response(request(), dump_json(wire))


@pytest.mark.parametrize(
    "status,state,retry,wide",
    [
        (400, "known", False, False),
        (401, "known", False, True),
        (403, "known", False, True),
        (404, "known", False, True),
        (413, "known", False, False),
        (422, "known", False, True),
        (429, "known", True, False),
        (500, "unknown", False, True),
        (307, "unknown", False, True),
    ],
)
def test_http_failures_are_bounded_and_do_not_leak_bodies(status, state, retry, wide):
    sent = []
    outcome = dispatch(
        {"error": "OFFLINE_SENTINEL"}, status=status, sent=sent, headers={"Retry-After": "2"}
    )
    assert len(sent) == 1
    assert outcome.state == state and outcome.retryable is retry and outcome.provider_wide is wide
    assert outcome.raw_response_source is None
    if retry:
        assert outcome.retry_after_seconds == 2


@pytest.mark.parametrize(
    "body", [b'{"answers":', b'{"model":"gpt-6-luna","model":"gpt-6-luna"}', b"NaN", b"\xff"]
)
def test_invalid_json_never_becomes_an_answer(body):
    provider = OpenAIDecisionsProvider(
        profile(),
        Credentials({"OFFLINE_KEY": "OFFLINE_SENTINEL"}),
        OneShotHttp(httpx.MockTransport(lambda req: httpx.Response(200, content=body))),
    )
    outcome = asyncio.run(provider.dispatch(request()))
    assert outcome.state == "known" and outcome.error.reason == "invalid_json"
    assert outcome.answer is None
    evidence = parse_json(outcome.raw_response_source)["deykit_unparsed_response"]
    assert evidence["encoding"] == "utf8_text" and evidence["truncated"] is False
    assert evidence["body"] == body.decode("utf-8", "replace")
    assert evidence["invalid_utf8_replaced"] is (body == b"\xff")


def test_disconnect_is_unknown_and_not_retryable():
    def handle(req):
        raise httpx.ReadError("OFFLINE_SENTINEL")

    provider = OpenAIDecisionsProvider(
        profile(),
        Credentials({"OFFLINE_KEY": "OFFLINE_SENTINEL"}),
        OneShotHttp(httpx.MockTransport(handle)),
    )
    outcome = asyncio.run(provider.dispatch(request()))
    assert outcome.state == "unknown" and not outcome.retryable
    assert outcome.error.reason == "disconnect"
    assert "OFFLINE_SENTINEL" not in repr(outcome)


def test_frozen_request_admission_precedes_credential_access():
    class ForbiddenCredentials:
        def resolve(self, reference):
            pytest.fail("Invalid request reached credential resolution")

    provider = OpenAIDecisionsProvider(profile(), ForbiddenCredentials())
    original = request()
    for change in (
        {"destination": "https://invalid.example/"},
        {"body_hash": "0" * 64},
        {"semantic_headers_source": '{"Authorization":"unsafe"}'},
        {"compiler_version": "future"},
    ):
        outcome = asyncio.run(provider.dispatch(original.model_copy(update=change)))
        assert (
            outcome.state == "not_sent" and outcome.error.reason == "invalid_request_configuration"
        )


@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP"])
def test_managed_images_use_prepared_inline_bytes_and_named_order(tmp_path, format):
    from PIL import Image

    Image.new("RGB", (20, 10), (255, 0, 0)).save(tmp_path / "product", format=format)
    asset = LocalImages(tmp_path).prepare("product", ImagePreparation())
    compiler = OpenAIChoiceCompiler()
    choice = definition().model_copy(update={"selected_images": ("front", "back")})
    compiled = compiler.compile_images(
        choice, "Why?", profile(), (("front", asset), ("back", asset))
    )
    parts = parse_json(compiled.body)["input"][0]["content"]
    assert compiled.body_kind == "image_json" and compiled.semantic_headers_source == "{}"
    assert parts[1] == {"type": "input_text", "text": "Image: front"}
    assert parts[3] == {"type": "input_text", "text": "Image: back"}
    assert base64.b64decode(parts[2]["image_url"].split(",")[1]) == asset.prepared_bytes()
    assert str(tmp_path) not in compiled.body.decode()
    verify_compiled_request(compiled)
    root = parse_json(compiled.body)
    root["input"][0]["content"][2]["image_url"] = "https://invalid.example/image.png"
    body = dump_json(root).encode()
    outcome = dispatch(
        compiled=compiled.model_copy(update={"body": body, "body_hash": bytes_hash(body)})
    )
    assert outcome.state == "not_sent"


def test_image_request_limit_rejects_before_decoding(tmp_path, monkeypatch):
    from PIL import Image

    Image.new("RGB", (1024, 1024)).save(tmp_path / "large.png", compress_level=0)
    asset = LocalImages(tmp_path).prepare("large.png", ImagePreparation())
    choice = definition().model_copy(update={"selected_images": ("a", "b", "c")})
    inspected = []
    from deykit.providers import openai_images

    original = openai_images._inspect

    def inspect(*args):
        inspected.append(True)
        return original(*args)

    monkeypatch.setattr(openai_images, "_inspect", inspect)
    with pytest.raises(ValueError, match="json_resource_limit"):
        OpenAIChoiceCompiler().compile_images(
            choice, "text", profile(), tuple((name, asset) for name in ("a", "b", "c"))
        )
    assert len(inspected) == 1


def test_unparsed_evidence_is_sanitized_bounded_and_explicit_about_truncation():
    for body in (
        b'{"broken":"OFFLINE_SENTINEL Bearer private',
        b"x" * 1_048_576,
        b"\x00" * 1_048_576,
    ):
        provider = OpenAIDecisionsProvider(
            profile(),
            Credentials({"OFFLINE_KEY": "OFFLINE_SENTINEL"}),
            OneShotHttp(
                httpx.MockTransport(
                    lambda req, response_body=body: httpx.Response(200, content=response_body)
                )
            ),
        )
        outcome = asyncio.run(provider.dispatch(request()))
        assert outcome.error.reason == "invalid_json"
        evidence = parse_json(outcome.raw_response_source)["deykit_unparsed_response"]
        captured = evidence["body"].encode("utf-8")
        assert b"OFFLINE_SENTINEL" not in captured and b"private" not in captured
        assert evidence["capture_byte_count"] == len(captured)
        assert evidence["truncated"] is (len(body) == 1_048_576)
        if evidence["truncated"]:
            assert evidence["capture_source_byte_count"] == len(body)
            assert evidence["capture_source_hash"] == bytes_hash(body)
            assert captured == body[: len(captured)]
        else:
            assert evidence["capture_source_hash"] == bytes_hash(captured)


def test_malformed_unicode_replacement_is_explicit_without_losing_valid_pairs():
    from deykit.providers.openai_decisions import _unparsed_evidence
    from deykit.providers.safety import Sanitizer

    raw = _unparsed_evidence(rb'{"broken":"\ud83d\ude00 \ud800', Sanitizer())
    evidence = parse_json(raw)["deykit_unparsed_response"]
    assert evidence["body"] == '{"broken":"😀 ?'
    assert evidence["normalized_json_escapes"] and evidence["lone_surrogates_replaced"]
    assert not evidence["invalid_utf8_replaced"] and not evidence["changed_by_redaction"]


@pytest.mark.parametrize(
    "body",
    [
        rb'{"message":"\u004fFFLINE_SENTINEL","message":"duplicate"}',
        rb'{"message":"\u004fFFLINE_SENTINEL',
        rb'{"message":"OFFLINE_\u0053ENTINEL',
        rb'{"message":"\u0042earer private',
    ],
)
def test_malformed_evidence_redacts_json_escaped_credentials(body):
    provider = OpenAIDecisionsProvider(
        profile(),
        Credentials({"OFFLINE_KEY": "OFFLINE_SENTINEL"}),
        OneShotHttp(httpx.MockTransport(lambda req: httpx.Response(200, content=body))),
    )
    outcome = asyncio.run(provider.dispatch(request()))
    evidence = parse_json(outcome.raw_response_source)["deykit_unparsed_response"]
    captured = evidence["body"]
    assert "[REDACTED]" in captured
    assert "SENTINEL" not in captured and "private" not in captured
