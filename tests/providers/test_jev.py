import asyncio
from pathlib import Path

import httpx
import pytest
from test_choice import definition

from deykit.contracts.json_value import parse_json
from deykit.contracts.records import ProviderProfile
from deykit.providers.choice import JEV_DESTINATION, compile_choice
from deykit.providers.credentials import Credentials
from deykit.providers.http import OneShotHttp
from deykit.providers.jev import JevProvider, validate_profile

VALID = (Path(__file__).parent / "corpus" / "valid-choice.json").read_bytes()


def profile():
    return ProviderProfile(
        id="local",
        adapter="jev",
        requested_model="jev-1.13.0",
        destination=JEV_DESTINATION,
        credential_ref="env:OFFLINE_KEY",
    )


def dispatch(provider):
    return asyncio.run(provider.dispatch(compile_choice(definition(), "Why?", "jev-1.13.0")))


def test_a18_a30_configure_status_and_missing_credential_send_no_inference():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, content=VALID)

    saved = validate_profile(profile())
    provider = JevProvider(saved, Credentials({}), OneShotHttp(httpx.MockTransport(handle)))
    assert provider.preflight().reason == "credential_unavailable"
    assert dispatch(provider).state == "not_sent"
    assert calls == []


@pytest.mark.parametrize(
    "status,state,code,retryable,wide",
    [
        (401, "known", "provider_auth", False, True),
        (403, "known", "provider_auth", False, True),
        (422, "known", "provider_rejected", False, True),
        (429, "known", "provider_rejected", True, False),
        (529, "known", "provider_rejected", True, False),
        (500, "unknown", "provider_rejected", False, True),
        (307, "unknown", "provider_rejected", False, True),
    ],
)
def test_a21_status_mapping_one_dispatch_no_hidden_retry(status, state, code, retryable, wide):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            status,
            content=b"SECRET_SENTINEL",
            headers={
                "Authorization": "Bearer SECRET_SENTINEL",
                "Retry-After": "3",
            },
        )

    provider = JevProvider(
        profile(),
        Credentials({"OFFLINE_KEY": "SECRET_SENTINEL"}),
        OneShotHttp(httpx.MockTransport(handle)),
    )
    outcome = dispatch(provider)
    assert len(calls) == 1
    assert (outcome.state, outcome.error.code, outcome.retryable, outcome.provider_wide) == (
        state,
        code,
        retryable,
        wide,
    )
    assert outcome.retry_after_seconds == (3.0 if retryable else None)
    assert "SECRET_SENTINEL" not in outcome.model_dump_json()
    assert "Authorization" not in outcome.model_dump_json()


def test_a42_success_raw_response_and_usage_are_sanitized():
    def handle(request):
        return httpx.Response(
            200,
            content=VALID[:-2]
            + (b',"debug":"SECRET_SENTINEL","headers":{"Authorization":"Bearer SECRET_SENTINEL"}}'),
        )

    provider = JevProvider(
        profile(),
        Credentials({"OFFLINE_KEY": "SECRET_SENTINEL"}),
        OneShotHttp(httpx.MockTransport(handle)),
    )
    outcome = dispatch(provider)
    assert outcome.answer.option_id == "question"
    assert parse_json(outcome.usage_source) == {"input_tokens": 101, "output_tokens": 12}
    assert "SECRET_SENTINEL" not in outcome.model_dump_json()
    assert "Authorization" not in outcome.model_dump_json()


def test_invalid_200_response_retains_only_safe_evidence():
    def handle(request):
        return httpx.Response(200, content=b'{"model":"SECRET_SENTINEL"}')

    provider = JevProvider(
        profile(),
        Credentials({"OFFLINE_KEY": "SECRET_SENTINEL"}),
        OneShotHttp(httpx.MockTransport(handle)),
    )
    outcome = dispatch(provider)
    assert outcome.error.code == "response_invalid"
    assert outcome.state == "known"
    assert not outcome.retryable
    assert "SECRET_SENTINEL" not in outcome.model_dump_json()


def test_model_listing_exactly_one_get_zero_inference():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "jev-latest",
                        "description": "SECRET_SENTINEL",
                        "release_date": "2026-10-01",
                    }
                ]
            },
        )

    provider = JevProvider(
        profile(),
        Credentials({"OFFLINE_KEY": "SECRET_SENTINEL"}),
        OneShotHttp(httpx.MockTransport(handle)),
    )
    assert calls == []
    assert provider.models()[0]["name"] == "jev-latest"
    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert calls[0].url.path == "/v1/models"


def test_profile_cannot_select_unofficial_destination():
    with pytest.raises(ValueError):
        validate_profile(profile().model_copy(update={"destination": "https://other.invalid"}))


@pytest.mark.parametrize("mutation", ["model", "hash", "extra", "question", "options"])
def test_modified_persisted_request_is_rejected_before_dispatch(mutation):
    from deykit.contracts.json_value import bytes_hash, dump_json

    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, content=VALID)

    compiled = compile_choice(definition(), "Why?", "jev-1.13.0")
    body = parse_json(compiled.body)
    if mutation == "model":
        body["model"] = "jev-latest"
    elif mutation == "extra":
        body["labels"] = ["question"]
    elif mutation == "question":
        body["questions"]["category"]["type"] = "noul"
    elif mutation == "options":
        body["questions"]["category"]["criteria"] = {}
    new_bytes = dump_json(body).encode()
    compiled = compiled.model_copy(
        update={
            "body": new_bytes,
            "body_hash": "0" * 64 if mutation == "hash" else bytes_hash(new_bytes),
        }
    )
    provider = JevProvider(
        profile(),
        Credentials({"OFFLINE_KEY": "SECRET_SENTINEL"}),
        OneShotHttp(httpx.MockTransport(handle)),
    )
    outcome = asyncio.run(provider.dispatch(compiled))
    assert outcome.state == "not_sent"
    assert calls == []


def test_sanitized_evidence_expansion_above_source_limit_is_safe_error():
    def handle(request):
        return httpx.Response(200, json={"echo": "key " * 100_000})

    provider = JevProvider(
        profile(), Credentials({"OFFLINE_KEY": "key"}), OneShotHttp(httpx.MockTransport(handle))
    )
    outcome = dispatch(provider)
    assert outcome.error.code == "response_invalid"
    assert outcome.raw_response_source is None
    assert "key" not in outcome.model_dump_json()
