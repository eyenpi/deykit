from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from deykit.providers.choice import JEV_DESTINATION, MODELS_DESTINATION
from deykit.providers.http import HttpFailure, OneShotHttp, retry_after


def test_exact_bytes_and_one_call_no_redirect(monkeypatch):
    calls = []
    monkeypatch.setenv("HTTPS_PROXY", "http://attacker.invalid")

    def handle(request):
        calls.append(request)
        assert request.content == b'{"n":9007199254740993}'
        return httpx.Response(307, headers={"location": "https://attacker.invalid/"})

    result = OneShotHttp(httpx.MockTransport(handle)).send(
        "POST",
        JEV_DESTINATION,
        b'{"n":9007199254740993}',
        "SENTINEL",
        60,
    )
    assert result.status == 307
    assert len(calls) == 1


@pytest.mark.parametrize(
    "destination",
    [
        "http://api.typesafe.ai/v1/systemone",
        "https://api.typesafe.ai.attacker.invalid/v1/systemone",
        "https://user:pass@api.typesafe.ai/v1/systemone",
        JEV_DESTINATION + "?key=SENTINEL",
        JEV_DESTINATION + "/",
        "https://api.typesafe.ai:443/v1/systemone",
    ],
)
def test_unapproved_destinations_make_zero_calls(destination):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200)

    with pytest.raises(ValueError):
        OneShotHttp(httpx.MockTransport(handle)).send("POST", destination, b"{}", "TEST", 60)
    assert calls == []


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ReadError, httpx.ConnectError])
def test_transport_errors_are_unknown_and_never_retried(failure):
    calls = []

    def handle(request):
        calls.append(request)
        raise failure("SENTINEL Authorization: Bearer SECRET")

    with pytest.raises(HttpFailure) as raised:
        OneShotHttp(httpx.MockTransport(handle)).send("POST", JEV_DESTINATION, b"{}", "TEST", 60)
    assert len(calls) == 1
    assert "SENTINEL" not in str(raised.value)
    assert "SECRET" not in str(raised.value)
    assert "unknown" in str(raised.value)


def test_retry_after_seconds_and_http_date():
    now = datetime(2026, 10, 5, 12, tzinfo=UTC)
    assert retry_after("3", now) == Decimal(3)
    assert retry_after("Mon, 05 Oct 2026 12:00:09 GMT", now) == Decimal(9)
    assert retry_after("Mon, 05 Oct 2026 11:00:00 GMT", now) == Decimal(0)
    for invalid in (None, "NaN", "Infinity", "-1", "invalid"):
        assert retry_after(invalid, now) is None


def test_models_only_get_and_bounded_body():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, content=b"123456")

    with pytest.raises(HttpFailure, match="response_too_large"):
        OneShotHttp(httpx.MockTransport(handle), max_response_bytes=5).send(
            "GET",
            MODELS_DESTINATION,
            None,
            "TEST",
            60,
        )
    assert [r.method for r in calls] == ["GET"]
