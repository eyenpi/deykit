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
        (400, "known", "provider_rejected", False, False),
        (413, "known", "provider_rejected", False, False),
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
            content=VALID.rstrip()[:-1]
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
    assert asyncio.run(provider.models())[0]["name"] == "jev-latest"
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


@pytest.mark.parametrize("question_id", ["headers", "authorization", "secret", "ordinary"])
@pytest.mark.parametrize(
    "option_id", ["secret", "api_key", "Authorization", "password", "ordinary"]
)
def test_typed_stable_ids_are_not_redacted_as_credential_field_names(question_id, option_id):
    from deykit.contracts.records import ChoiceDefinition, ChoiceOption, ChoiceQuestion

    choice = ChoiceDefinition(
        input_kind="text",
        questions=(
            ChoiceQuestion(
                id=question_id,
                instructions="Choose.",
                options=(
                    ChoiceOption(id=option_id, name="Selected"),
                    ChoiceOption(id="normal", name="Normal"),
                ),
            ),
        ),
    )

    def handle(request):
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "answers": {
                    question_id: {
                        "type": "choice",
                        "choice": option_id,
                        "probabilities": {option_id: 1, "normal": 0},
                        "confidence": 1,
                    }
                },
                "metadata": {"secret": "SECRET_SENTINEL", "echo": "SECRET_SENTINEL"},
            },
        )

    provider = JevProvider(
        profile(),
        Credentials({"OFFLINE_KEY": "SECRET_SENTINEL"}),
        OneShotHttp(httpx.MockTransport(handle)),
    )
    outcome = asyncio.run(provider.dispatch(compile_choice(choice, "Hello", "jev-1.13.0")))
    assert outcome.answer.option_id == option_id
    assert outcome.answer.question_id == question_id
    assert parse_json(outcome.answer.probabilities_source) == {option_id: 1, "normal": 0}
    assert "SECRET_SENTINEL" not in outcome.model_dump_json()


def test_actual_credential_occurrence_in_stable_id_cannot_escape_safe_result():
    from deykit.contracts.records import ChoiceDefinition, ChoiceOption, ChoiceQuestion

    choice = ChoiceDefinition(
        input_kind="text",
        questions=(
            ChoiceQuestion(
                id="category",
                instructions="Choose.",
                options=(
                    ChoiceOption(id="SECRET_SENTINEL", name="Selected"),
                    ChoiceOption(id="normal", name="Normal"),
                ),
            ),
        ),
    )

    def handle(request):
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "answers": {
                    "category": {
                        "type": "choice",
                        "choice": "SECRET_SENTINEL",
                        "probabilities": {"SECRET_SENTINEL": 1, "normal": 0},
                        "confidence": 1,
                    }
                },
            },
        )

    provider = JevProvider(
        profile(),
        Credentials({"OFFLINE_KEY": "SECRET_SENTINEL"}),
        OneShotHttp(httpx.MockTransport(handle)),
    )
    outcome = asyncio.run(provider.dispatch(compile_choice(choice, "Hello", "jev-1.13.0")))
    assert outcome.error.code == "response_invalid"
    assert "SECRET_SENTINEL" not in outcome.model_dump_json()


@pytest.mark.parametrize(
    "status,wide,retryable",
    [
        (401, True, False),
        (403, True, False),
        (422, True, False),
        (429, False, True),
        (529, False, True),
    ],
)
@pytest.mark.parametrize("body_failure", ["oversize", "disconnect", "timeout"])
def test_definitive_error_headers_are_preserved_without_reading_body(
    status, wide, retryable, body_failure
):
    class Body(httpx.AsyncByteStream):
        reads = 0
        closed = False

        async def __aiter__(self):
            self.reads += 1
            if body_failure == "disconnect":
                raise httpx.ReadError("SECRET_SENTINEL")
            if body_failure == "timeout":
                raise httpx.ReadTimeout("SECRET_SENTINEL")
            yield b"x" * 2_097_152

        async def aclose(self):
            self.closed = True

    body = Body()
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, headers={"retry-after": "3"}, stream=body)

    provider = JevProvider(
        profile(),
        Credentials({"OFFLINE_KEY": "SECRET_SENTINEL"}),
        OneShotHttp(httpx.MockTransport(handle)),
    )
    outcome = dispatch(provider)
    assert outcome.state == "known"
    assert outcome.provider_wide is wide
    assert outcome.retryable is retryable
    assert outcome.retry_after_seconds == (3 if retryable else None)
    assert len(calls) == 1
    assert body.reads == 0
    assert body.closed


def test_aggregate_deadline_outcome_is_unknown_and_not_retryable(monkeypatch):
    class Body(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            clock[0] += 60
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            yield VALID

        async def aclose(self):
            self.closed = True

    body, clock, calls = Body(), [1000.0], []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, stream=body)

    provider = JevProvider(
        profile(),
        Credentials({"OFFLINE_KEY": "SECRET_SENTINEL"}),
        OneShotHttp(httpx.MockTransport(handle)),
    )

    async def scenario():
        with monkeypatch.context() as patch:
            patch.setattr(asyncio.get_running_loop(), "time", lambda: clock[0])
            return await provider.dispatch(
                compile_choice(definition(), "Hi", "jev-1.13.0"), timeout_seconds=60
            )

    outcome = asyncio.run(scenario())
    assert outcome.state == "unknown"
    assert outcome.error.reason == "timeout"
    assert not outcome.retryable
    assert len(calls) == 1
    assert body.closed
