"""Offline Jev image wire contracts, independent of provider inference."""

import asyncio
import base64
from pathlib import Path

import httpx
import pytest
from PIL import Image
from test_choice import definition, valid
from test_fixtures import answer, fixture_set
from test_jev import profile

from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.images import ImagePreparation
from deykit.contracts.json_value import bytes_hash, dump_json, parse_json
from deykit.contracts.records import CompiledRequest, FixtureBinding
from deykit.images.local import LocalImages
from deykit.providers.choice import JevChoiceCompiler, compile_choice
from deykit.providers.credentials import Credentials
from deykit.providers.fixtures import FixtureTransportFactory, fixture_set_hash
from deykit.providers.http import OneShotHttp
from deykit.providers.jev import JevProvider

HEADER = "TypeSafe-Danger-Zone-Images"


def asset(tmp_path, *, size=(280, 280), format="PNG", pad=False):
    path = tmp_path / ("image." + format.lower())
    Image.new("RGB", size, (255, 0, 0)).save(path, format=format)
    preparation = (
        ImagePreparation(mode="pad", min_width=280, min_height=280) if pad else ImagePreparation()
    )
    return LocalImages(tmp_path).prepare(path.name, preparation)


def compiled(image, *, state="Why?", choice=None, provider=None):
    choice = choice or definition().model_copy(update={"selected_images": ("product",)})
    return JevChoiceCompiler().compile_images(
        choice, state, provider or profile(), (("product", image),)
    )


@pytest.mark.parametrize("format", ["PNG", "JPEG"])
def test_exact_prepared_bytes_references_and_semantic_header(tmp_path, format):
    image = asset(tmp_path, size=(2, 1), format=format, pad=True)
    request = compiled(image)
    body = parse_json(request.body)
    reference = body["state"]["product"]
    assert body["state"]["text"] == "Why?"
    assert body["assets"] == {
        reference: {
            "type": "image",
            "format": "png",
            "data_base64": base64.b64encode(image.prepared_bytes()).decode("ascii"),
        }
    }
    assert image.prepared_bytes() != image.source_bytes()
    assert parse_json(request.semantic_headers_source) == {HEADER: "true"}
    assert request.body_hash == bytes_hash(request.body)
    assert load_record(CompiledRequest, dump_record(request)) == request
    assert compiled(image) == request


def test_preserved_jpeg_and_exact_selected_json_are_not_transformed(tmp_path):
    image = asset(tmp_path, size=(1568, 280), format="JPEG")
    choice = definition(kind="json", fields=("n",)).model_copy(
        update={"selected_images": ("product",)}
    )
    request = compiled(image, state=parse_json('{"n":9007199254740993}'), choice=choice)
    body = parse_json(request.body)
    assert body["state"]["n"] == 9007199254740993
    wire_asset = next(iter(body["assets"].values()))
    assert wire_asset["format"] == "jpg"
    assert base64.b64decode(wire_asset["data_base64"]) == image.source_bytes()


@pytest.mark.parametrize("location", ["input", "instructions", "name", "description"])
def test_reference_never_replaces_existing_user_text(tmp_path, location):
    image = asset(tmp_path)
    first_reference = parse_json(compiled(image).body)["state"]["product"]
    text = "Keep this literal: " + first_reference
    choice = definition().model_copy(update={"selected_images": ("product",)})
    state = text if location == "input" else "Why?"
    question = choice.questions[0]
    if location == "instructions":
        question = question.model_copy(update={"instructions": text})
    elif location in {"name", "description"}:
        question = question.model_copy(
            update={
                "options": (
                    question.options[0].model_copy(update={location: text}),
                    question.options[1],
                )
            }
        )
    choice = choice.model_copy(update={"questions": (question,)})
    request = compiled(image, state=state, choice=choice)
    body = parse_json(request.body)
    assert body["state"]["product"] != first_reference
    assert text in request.body.decode()


@pytest.mark.parametrize("size", [(279, 280), (280, 279), (1569, 280), (280, 1569)])
def test_provider_dimension_limits_are_checked_locally(tmp_path, size):
    with pytest.raises(ValueError, match="image_dimensions_unsupported"):
        compiled(asset(tmp_path, size=size))


def test_webp_and_state_field_collisions_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="image_format_unsupported"):
        compiled(asset(tmp_path, format="WEBP"))
    choice = definition(kind="json", fields=("product",)).model_copy(
        update={"selected_images": ("product",)}
    )
    with pytest.raises(ValueError, match="image_state_name_collision"):
        compiled(asset(tmp_path), state={"product": "keep"}, choice=choice)


def test_multiple_names_for_one_asset_have_distinct_references(tmp_path):
    image = asset(tmp_path)
    choice = definition().model_copy(update={"selected_images": ("front", "back")})
    request = JevChoiceCompiler().compile_images(
        choice, "Why?", profile(), (("front", image), ("back", image))
    )
    body = parse_json(request.body)
    assert body["state"]["front"] != body["state"]["back"]
    assert len(body["assets"]) == 2
    with pytest.raises(ValueError, match="selected_image_mismatch"):
        JevChoiceCompiler().compile_images(choice, "Why?", profile(), (("front", image),))


def test_aggregate_image_request_is_bounded(tmp_path):
    path = tmp_path / "small.png"
    Image.new("RGB", (2, 1)).save(path)
    image = LocalImages(tmp_path).prepare(
        path.name, ImagePreparation(mode="pad", min_width=1024, min_height=1024)
    )
    choice = definition().model_copy(update={"selected_images": ("front", "back", "side")})
    with pytest.raises(ValueError, match="json_resource_limit"):
        JevChoiceCompiler().compile_images(
            choice, "Why?", profile(), tuple((name, image) for name in choice.selected_images)
        )


def test_transport_sends_frozen_header_and_body_and_keeps_strict_responses(tmp_path):
    request = compiled(asset(tmp_path))
    calls = []
    response = valid()

    def handle(sent):
        calls.append(sent)
        assert sent.content == request.body
        assert sent.headers[HEADER] == "true"
        assert sent.headers["authorization"] == "Bearer OFFLINE_SENTINEL"
        return httpx.Response(200, content=dump_json(response))

    provider = JevProvider(
        profile(),
        Credentials({"OFFLINE_KEY": "OFFLINE_SENTINEL"}),
        OneShotHttp(httpx.MockTransport(handle)),
    )
    outcome = asyncio.run(provider.dispatch(request))
    assert outcome.answer.option_id == "question"
    response["answers"]["category"]["probabilities"] = {"question": 1, "report": 1}
    outcome = asyncio.run(provider.dispatch(request))
    assert outcome.error.reason == "invalid_probability_sum"
    assert outcome.state == "known" and not outcome.retryable
    assert len(calls) == 2
    assert "OFFLINE_SENTINEL" not in dump_record(request).decode()


@pytest.mark.parametrize(
    "mutation", ["header", "extra_header", "unreferenced", "collision", "bytes", "format"]
)
def test_tampered_image_requests_fail_before_credentials_or_transport(tmp_path, mutation):
    request = compiled(asset(tmp_path))
    body = parse_json(request.body)
    reference = body["state"]["product"]
    headers = request.semantic_headers_source
    if mutation == "header":
        headers = "{}"
    elif mutation == "extra_header":
        headers = dump_json({HEADER: "true", "Authorization": "forbidden"})
    elif mutation == "unreferenced":
        del body["state"]["product"]
    elif mutation == "collision":
        body["state"]["text"] = "accidental " + reference
    elif mutation == "bytes":
        body["assets"][reference]["data_base64"] = "AAAA"
    elif mutation == "format":
        body["assets"][reference]["format"] = "jpg"
    wire = dump_json(body).encode()
    tampered = request.model_copy(
        update={"body": wire, "body_hash": bytes_hash(wire), "semantic_headers_source": headers}
    )
    provider = JevProvider(profile(), Credentials({}))
    outcome = asyncio.run(provider.dispatch(tampered))
    assert outcome.state == "not_sent"
    assert outcome.error.reason == "invalid_request_configuration"


def test_old_text_records_keep_their_bytes_and_do_not_enable_images():
    request = compile_choice(definition(), "Why?", "jev-1.13.0")
    assert "semantic_headers_source" not in parse_json(dump_record(request))
    assert load_record(CompiledRequest, dump_record(request)) == request
    calls = []

    def handle(sent):
        calls.append(sent)
        assert HEADER not in sent.headers
        return httpx.Response(200, content=dump_json(valid()))

    provider = JevProvider(
        profile(),
        Credentials({"OFFLINE_KEY": "OFFLINE_SENTINEL"}),
        OneShotHttp(httpx.MockTransport(handle)),
    )
    assert asyncio.run(provider.dispatch(request)).answer.option_id == "question"
    assert len(calls) == 1


def test_fixture_identity_includes_semantic_headers(tmp_path):
    provider = profile().model_copy(
        update={
            "adapter": "fixture",
            "destination": "fixture:jev-choice",
            "requested_model": "authored-test-v1",
            "credential_ref": None,
        }
    )
    request = compiled(asset(tmp_path), provider=provider)
    response = answer().model_copy(update={"question_id": "category", "option_id": "question"})
    fixtures = fixture_set(
        FixtureBinding(id="binding", case_id="case", request=request, answer=response)
    )
    transport = FixtureTransportFactory(fixtures).for_case("case")
    assert asyncio.run(transport.dispatch(request, timeout_seconds=1)).answer == response
    changed = request.model_copy(update={"semantic_headers_source": "{}"})
    assert asyncio.run(transport.dispatch(changed, timeout_seconds=1)).state == "not_sent"
    changed_fixture = fixtures.model_copy(
        update={"bindings": (fixtures.bindings[0].model_copy(update={"request": changed}),)}
    )
    assert fixture_set_hash(changed_fixture) != fixture_set_hash(fixtures)


@pytest.mark.parametrize(
    "line", (Path(__file__).parent / "corpus" / "malformed-choice.jsonl").read_text().splitlines()
)
def test_images_do_not_relax_the_malformed_response_corpus(tmp_path, line):
    from deykit.providers.choice import ResponseInvalid, validate_response

    with pytest.raises(ResponseInvalid):
        validate_response(compiled(asset(tmp_path)), dump_json(parse_json(line)["response"]))
