"""Adversarial requests must stop before any inner application effect."""

import asyncio
import json
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from deykit.api.app import create_app as _create_app
from deykit.api.config import LocalServerConfig
from deykit.api.dependencies import ApiDependencies
from deykit.api.dto.common import Count, CountText, ExactIntegerText
from deykit.api.recent import RecentProject
from deykit.api.runtime import SystemClock, new_id
from deykit.api.security import LocalBoundary
from deykit.api.session import SessionCapability
from deykit.providers.configuration import create_provider_operations
from deykit.runner.backends import ProviderBackends
from deykit.storage.demo_destination import FileDemoDestinationFactory
from deykit.storage.demo_staging import DemoStagingSource

ORIGIN = b"http://127.0.0.1:8765"
HOST = (b"host", b"127.0.0.1:8765")
BODY = b'{"schema_version":1}'


class EmptyRecentProjects:
    last_warning: str | None = None

    def list(self) -> tuple[RecentProject, ...]:
        return ()

    def remember(self, path: str, project_id: str, name: str) -> str | None:
        return None


def api_dependencies() -> ApiDependencies:
    clock = SystemClock()

    def forbidden_source(path, create):
        raise AssertionError("security-only requests must not open projects")

    return ApiDependencies(
        clock=clock,
        id_factory=new_id,
        source_factory=forbidden_source,
        recent_store=EmptyRecentProjects(),
        demo_staging_factory=DemoStagingSource,
        demo_destination_factory=FileDemoDestinationFactory(),
        provider_operations_factory=create_provider_operations,
        backends_factory=ProviderBackends,
    )


def create_app(test_config: LocalServerConfig) -> Any:
    return _create_app(test_config, api_dependencies())


def config() -> LocalServerConfig:
    return LocalServerConfig(
        "127.0.0.1:8765",
        ORIGIN.decode(),
    )


async def invoke(
    app: Any,
    *,
    method: str = "POST",
    path: str = "/api/v1/session/bootstrap",
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = BODY,
    raw_path: bytes | None = None,
    query: bytes = b"",
    events: list[dict[str, Any]] | None = None,
) -> tuple[int, bytes, dict[bytes, bytes]]:
    messages = []
    request_events = list(events or [{"type": "http.request", "body": body}])

    async def receive() -> dict[str, Any]:
        return request_events.pop(0) if request_events else {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": raw_path or path.encode(),
            "query_string": query,
            "root_path": "",
            "server": ("127.0.0.1", 8765),
            "client": ("127.0.0.1", 1234),
            "headers": headers if headers is not None else bootstrap_headers(),
        },
        receive,
        send,
    )
    if not messages:
        return 0, b"", {}
    start = next(item for item in messages if item["type"] == "http.response.start")
    return (
        start["status"],
        b"".join(item.get("body", b"") for item in messages),
        dict(start["headers"]),
    )


def bootstrap_headers() -> list[tuple[bytes, bytes]]:
    return [
        HOST,
        (b"origin", ORIGIN),
        (b"content-type", b"application/json"),
        (b"x-deykit-bootstrap", b"1"),
    ]


def run(app: Any, **kwargs: Any) -> tuple[int, bytes, dict[bytes, bytes]]:
    return asyncio.run(invoke(app, **kwargs))


@pytest.mark.parametrize(
    "host,status",
    [
        (None, 400),
        (b"evil.example:8765", 403),
        (b"localhost:8765", 403),
        (b"localhost.:8765", 403),
        (b"127.0.0.1:8766", 403),
        (b"127.1:8765", 403),
        (b"2130706433:8765", 403),
        (b"[::1]:8765", 403),
        (b"127.0.0.1", 403),
        (b"127.0.0.1:08765", 403),
        (b"user@127.0.0.1:8765", 400),
        (b"127.0.0.1:8765,evil", 400),
        (b"127.0.0.1:0", 400),
        (b"127.0.0.1:65536", 400),
        (b"127.0.0.1:\n8765", 400),
    ],
)
def test_host_before_body_or_inner(host: bytes | None, status: int) -> None:
    called = []

    async def inner(*args: Any) -> None:
        called.append(True)

    headers = [h for h in bootstrap_headers() if h[0] != b"host"]
    if host is not None:
        headers.append((b"host", host))
    result = run(
        LocalBoundary(inner, config(), SessionCapability.create()),
        headers=headers,
        body=b"not json secret",
    )
    assert result[0] == status
    assert not called
    assert b"secret" not in result[1]
    assert result[2][b"x-content-type-options"] == b"nosniff"


@pytest.mark.parametrize(
    "extra",
    [
        [HOST],
        [(b"origin", ORIGIN)],
        [(b"x-deykit-bootstrap", b"1")],
        [(b"sec-fetch-site", b"cross-site")],
        [(b"sec-fetch-site", b"same-site")],
        [(b"sec-fetch-site", b"none")],
        [(b"sec-fetch-mode", b"navigate")],
        [(b"sec-fetch-mode", b"no-cors")],
        [(b"sec-fetch-dest", b"iframe")],
        [(b"sec-fetch-site", b"same-origin")] * 2,
    ],
)
def test_duplicate_or_metadata_denied(extra: list[tuple[bytes, bytes]]) -> None:
    result = run(create_app(config()), headers=bootstrap_headers() + extra)
    assert result[0] == (400 if extra == [HOST] else 403)
    assert not any(k.startswith(b"access-control-allow-") for k in result[2])


@pytest.mark.parametrize(
    "origin",
    [
        None,
        b"null",
        b"http://127.0.0.1:9999",
        b"https://127.0.0.1:8765",
        b"http://evil.example",
        ORIGIN + b" " + ORIGIN,
    ],
)
def test_origin_denied(origin: bytes | None) -> None:
    headers = [h for h in bootstrap_headers() if h[0] != b"origin"]
    if origin is not None:
        headers.append((b"origin", origin))
    assert run(create_app(config()), headers=headers)[0] == 403


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b'{"schema_version":true}',
        b'{"schema_version":1.0}',
        b'{"schema_version":2}',
        b'{"schema_version":1,"schema_version":1}',
        b'{"schema_version":1,"secret":"SENTINEL"}',
        b'{"schema_version":1,"x":NaN}',
        b'{"schema_version":1,"x":"\\ud800"}',
        b'{"schema_version":1,"x":"\xff"}',
        b"",
        b"null",
    ],
)
def test_exact_envelope_and_fixed_error(body: bytes) -> None:
    status, response, _ = run(create_app(config()), body=body)
    assert status == 422
    data = json.loads(response)
    assert data["schema_version"] == 1
    assert data["error"]["code"] == "validation_error"
    assert b"SENTINEL" not in response and b'"input"' not in response


def test_bootstrap_reuse_rotation_protected_missing_origin_get() -> None:
    app = create_app(config())
    first = json.loads(run(app)[1])["data"]["capability"]
    assert first == json.loads(run(app)[1])["data"]["capability"]
    second = json.loads(run(create_app(config()))[1])["data"]["capability"]
    assert first != second
    headers = [HOST, (b"x-deykit-capability", first.encode())]
    # Correct capability admits the recent-project preference route.
    assert run(app, method="GET", path="/api/v1/projects/recent", headers=headers)[0] == 200
    assert run(app, method="GET", path="/api/v1/projects/recent", headers=[HOST])[0] == 403
    assert run(app, method="HEAD", path="/api/v1/projects/recent", headers=[HOST])[1] == b""
    assert (
        run(create_app(config()), method="GET", path="/api/v1/projects/recent", headers=headers)[0]
        == 403
    )
    assert run(app, method="GET", path="/api/v1/projects/recent", headers=headers * 2)[0] == 400
    assert (
        run(
            app,
            method="GET",
            path="/api/v1/projects/recent",
            headers=headers + [(b"x-deykit-capability", first.encode())],
        )[0]
        == 403
    )
    assert (
        run(
            app,
            method="GET",
            path="/api/v1/projects/recent",
            headers=headers + [(b"origin", b"null")],
        )[0]
        == 403
    )


@pytest.mark.parametrize(
    "headers,status",
    [
        ([(b"content-length", b"4097")], 413),
        ([(b"content-length", b"2"), (b"content-length", b"2")], 400),
        ([(b"content-length", b"-1")], 400),
        ([(b"content-encoding", b"gzip")], 415),
        ([(b"if-match", b"etag")], 422),
        ([(b"idempotency-key", b"save")], 422),
    ],
)
def test_body_headers(headers: list[tuple[bytes, bytes]], status: int) -> None:
    assert run(create_app(config()), headers=bootstrap_headers() + headers)[0] == status


def test_actual_chunk_limit_disconnect_and_content_type() -> None:
    assert run(create_app(config()), body=b" " * 4097)[0] == 413
    assert (
        run(
            create_app(config()),
            events=[
                {"type": "http.request", "body": BODY, "more_body": True},
                {"type": "http.disconnect"},
            ],
        )[0]
        == 0
    )
    headers = [h for h in bootstrap_headers() if h[0] != b"content-type"]
    assert run(create_app(config()), headers=headers)[0] == 415
    assert run(create_app(config()), headers=headers + [(b"content-type", b"text/plain")])[0] == 415
    assert (
        run(
            create_app(config()),
            headers=headers + [(b"content-type", b"application/json; charset=utf-8")],
        )[0]
        == 200
    )


@pytest.mark.parametrize(
    "path",
    [
        b"/api%2fv1/session/bootstrap",
        b"/api/v1/../x",
        b"/api/v1//x",
        b"/api/v1/%252e%252e",
        b"/api/v1/a\\b",
        b"/api/v1/\x00",
    ],
)
def test_raw_path_denial(path: bytes) -> None:
    assert run(create_app(config()), raw_path=path)[0] == 403


@pytest.mark.parametrize("query", [b"token=secret", b"capability=x", b"x=1&x=2", b"x=1"])
def test_bootstrap_no_query(query: bytes) -> None:
    assert run(create_app(config()), query=query)[0] == 422


def test_headless_root_csp_and_no_api_html_fallback() -> None:
    status, body, headers = run(create_app(config()), method="GET", path="/", headers=[HOST])
    assert status == 404 and b"<html" not in body
    assert b"unsafe-eval" not in headers[b"content-security-policy"]
    assert b"frame-ancestors 'none'" in headers[b"content-security-policy"]
    assert run(create_app(config()), method="POST", path="/api/v1/session/bootstrap/")[0] == 403
    assert run(create_app(config()), method="TRACE")[0] == 405
    assert run(create_app(config()), method="OPTIONS")[0] == 403


@pytest.mark.parametrize(
    "path,status", [("/", 404), ("/index.html", 403), ("/assets", 404), ("/assets/app.js", 403)]
)
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_removed_ui_paths_serve_no_html(path: str, status: int, method: str) -> None:
    actual, body, headers = run(create_app(config()), method=method, path=path, headers=[HOST])
    assert actual == status
    assert b"<html" not in body
    assert headers[b"content-type"].startswith(b"application/json")
    if method == "HEAD":
        assert body == b""


def test_exact_display_primitives() -> None:
    assert TypeAdapter(ExactIntegerText).validate_python("-9007199254740993")
    for invalid in ("-0", "+1", "01", "1.0", 1):
        with pytest.raises(ValidationError):
            TypeAdapter(ExactIntegerText).validate_python(invalid)
    for invalid in ("-1", "01", 1):
        with pytest.raises(ValidationError):
            TypeAdapter(CountText).validate_python(invalid)
    for invalid in (True, -1, 9007199254740992, 1.0):
        with pytest.raises(ValidationError):
            TypeAdapter(Count).validate_python(invalid)


def test_unexpected_error_does_not_reflect_exception() -> None:
    async def failing(*args: Any) -> None:
        raise RuntimeError("SENTINEL secret input and private path")

    status, response, _ = run(LocalBoundary(failing, config(), SessionCapability.create()))
    assert status == 500
    assert b"SENTINEL" not in response
    assert json.loads(response)["error"]["correlation_id"]


def test_shutdown_revokes_bootstrap_and_capability() -> None:
    from deykit.api.app import create_inner_app

    session = SessionCapability.create()
    inner = create_inner_app(config(), session, api_dependencies())
    boundary = LocalBoundary(inner, config(), session)

    async def exercise() -> None:
        async with inner.router.lifespan_context(inner):
            assert (await invoke(boundary))[0] == 200
        assert (await invoke(boundary))[0] == 503

    asyncio.run(exercise())
    assert not session.active


def test_bad_capability_never_reads_large_body() -> None:
    consumed = []

    async def receive() -> dict[str, Any]:
        consumed.append(True)
        raise AssertionError("body must not be read")

    async def exercise() -> None:
        responses = []

        async def send(message: dict[str, Any]) -> None:
            responses.append(message)

        app = create_app(config())
        await app(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/projects/register",
                "raw_path": b"/api/v1/projects/register",
                "query_string": b"",
                "headers": [HOST, (b"origin", ORIGIN), (b"content-length", b"999999999")],
                "scheme": "http",
                "http_version": "1.1",
            },
            receive,
            send,
        )
        assert responses[0]["status"] == 403

    asyncio.run(exercise())
    assert not consumed


@pytest.mark.parametrize(
    "name,value",
    [
        (b"sec-fetch-mode", b"webtransport"),
        (b"sec-fetch-dest", b"json"),
        (b"sec-fetch-dest", b"text"),
    ],
)
def test_current_recognized_metadata_denied(name: bytes, value: bytes) -> None:
    assert run(create_app(config()), headers=bootstrap_headers() + [(name, value)])[0] == 403


def test_unknown_fetch_metadata_is_not_authentication() -> None:
    headers = bootstrap_headers() + [
        (b"sec-fetch-site", b"future-site"),
        (b"sec-fetch-mode", b"future-mode"),
        (b"sec-fetch-dest", b"future-destination"),
    ]
    assert run(create_app(config()), headers=headers)[0] == 200
    assert run(create_app(config()), headers=[h for h in headers if h[0] != b"origin"])[0] == 403
