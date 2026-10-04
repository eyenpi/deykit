import asyncio
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

    result = asyncio.run(
        OneShotHttp(httpx.MockTransport(handle)).send(
            "POST",
            JEV_DESTINATION,
            b'{"n":9007199254740993}',
            "SENTINEL",
            60,
        )
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
        asyncio.run(
            OneShotHttp(httpx.MockTransport(handle)).send("POST", destination, b"{}", "TEST", 60)
        )
    assert calls == []


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ReadError, httpx.ConnectError])
def test_transport_errors_are_unknown_and_never_retried(failure):
    calls = []

    def handle(request):
        calls.append(request)
        raise failure("SENTINEL Authorization: Bearer SECRET")

    with pytest.raises(HttpFailure) as raised:
        asyncio.run(
            OneShotHttp(httpx.MockTransport(handle)).send(
                "POST", JEV_DESTINATION, b"{}", "TEST", 60
            )
        )
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
        asyncio.run(
            OneShotHttp(httpx.MockTransport(handle), max_response_bytes=5).send(
                "GET",
                MODELS_DESTINATION,
                None,
                "TEST",
                60,
            )
        )
    assert [r.method for r in calls] == ["GET"]


def test_a42_real_httpcore_debug_logs_cannot_echo_response_headers(caplog):
    import logging

    class Stream:
        async def read(self, max_bytes, timeout=None):
            return (
                b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n"
                b"Authorization: Bearer SECRET_SENTINEL\r\n\r\n{}"
            )

        async def write(self, buffer, timeout=None):
            pass

        async def aclose(self):
            pass

        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            return self

        def get_extra_info(self, info):
            return None

    class Backend:
        async def connect_tcp(self, *args, **kwargs):
            return Stream()

    # Exercise real HTTPX/httpcore parsing and logging with a network-free byte stream.
    transport = httpx.AsyncHTTPTransport(retries=0, trust_env=False)
    transport._pool._network_backend = Backend()
    with caplog.at_level(logging.DEBUG):
        result = asyncio.run(
            OneShotHttp(transport).send("POST", JEV_DESTINATION, b"{}", "SECRET_SENTINEL", 60)
        )
        logging.getLogger("httpcore.http11").debug("unrelated caller remains visible")
    assert result.status == 200
    assert "SECRET_SENTINEL" not in caplog.text
    assert "Authorization" not in caplog.text
    assert "unrelated caller remains visible" in caplog.text


def test_aggregate_deadline_expires_across_individually_timely_httpcore_reads(monkeypatch):
    class Stream:
        reads = 0
        closed = False
        phase_bounds = []

        async def read(self, max_bytes, timeout=None):
            self.reads += 1
            self.phase_bounds.append(timeout)
            clock[0] += 30
            # Advance a controlled event-loop clock, then let due timers run.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            if self.reads == 1:
                return b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\na"
            return b"b" if self.reads == 2 else b"c"

        async def write(self, buffer, timeout=None):
            pass

        async def aclose(self):
            self.closed = True

        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            return self

        def get_extra_info(self, info):
            return None

    class Backend:
        connections = 0

        async def connect_tcp(self, *args, **kwargs):
            self.connections += 1
            return stream

    stream, backend, clock = Stream(), Backend(), [1000.0]
    transport = httpx.AsyncHTTPTransport(retries=0, trust_env=False)
    transport._pool._network_backend = backend

    async def scenario():
        loop = asyncio.get_running_loop()
        with monkeypatch.context() as patch:
            patch.setattr(loop, "time", lambda: clock[0])
            with pytest.raises(HttpFailure, match="timeout"):
                await OneShotHttp(transport).send("POST", JEV_DESTINATION, b"{}", "TEST", 60)

    asyncio.run(scenario())
    assert backend.connections == 1
    assert stream.reads == 2
    assert clock[0] == 1060
    assert stream.phase_bounds == [60, 60]
    assert stream.closed


@pytest.mark.parametrize("phase", ["connect", "headers", "body"])
def test_aggregate_deadline_covers_every_network_phase_and_closes_client(monkeypatch, phase):
    async def elapsed():
        clock[0] += 61
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    class Stream:
        closed = False
        reads = 0

        async def read(self, max_bytes, timeout=None):
            self.reads += 1
            if self.reads == 1:
                if phase == "headers":
                    await elapsed()
                return b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n"
            if phase == "body":
                await elapsed()
            return b"{}"

        async def write(self, buffer, timeout=None):
            pass

        async def aclose(self):
            self.closed = True

        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            return self

        def get_extra_info(self, info):
            return None

    class Backend:
        calls = 0

        async def connect_tcp(self, *args, **kwargs):
            self.calls += 1
            if phase == "connect":
                await elapsed()
            return stream

    class Transport(httpx.AsyncHTTPTransport):
        closed = False

        async def __aexit__(self, *args):
            self.closed = True
            await super().__aexit__(*args)

    stream, backend, clock = Stream(), Backend(), [1000.0]
    transport = Transport(retries=0, trust_env=False)
    transport._pool._network_backend = backend

    async def scenario():
        with monkeypatch.context() as patch:
            patch.setattr(asyncio.get_running_loop(), "time", lambda: clock[0])
            with pytest.raises(HttpFailure, match="timeout"):
                await OneShotHttp(transport).send("POST", JEV_DESTINATION, b"{}", "TEST", 60)

    asyncio.run(scenario())
    assert backend.calls == 1
    assert transport.closed
    assert stream.closed is (phase != "connect")


def test_external_cancellation_closes_response_and_client_without_retry():
    class Body(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            reading.set()
            await asyncio.Event().wait()
            yield b"unreachable"

        async def aclose(self):
            self.closed = True

    class Transport(httpx.AsyncBaseTransport):
        closed = False
        calls = 0

        async def handle_async_request(self, request):
            self.calls += 1
            return httpx.Response(200, stream=body)

        async def aclose(self):
            self.closed = True

    body, transport = Body(), Transport()

    async def scenario():
        nonlocal reading
        reading = asyncio.Event()
        task = asyncio.create_task(
            OneShotHttp(transport).send(
                "POST",
                JEV_DESTINATION,
                b"{}",
                "TEST",
                60,
            )
        )
        await reading.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    reading = None
    asyncio.run(scenario())
    assert body.closed and transport.closed
    assert transport.calls == 1
