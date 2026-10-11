"""Raw ASGI boundary outside routing, body validation, errors and asset serving."""

import re
from urllib.parse import parse_qsl

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .body import BodyDisconnected, read_bounded_json
from .config import LocalServerConfig
from .errors import TransportFailure, error_response
from .session import SessionCapability

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "cross-origin-resource-policy": "same-origin",
    "cache-control": "no-store",
    "content-security-policy": "default-src 'none'; script-src 'self'; style-src 'self'; "
    "img-src 'self'; font-src 'self'; connect-src 'self'; base-uri 'none'; "
    "object-src 'none'; frame-ancestors 'none'; form-action 'none'",
}
Headers = list[tuple[bytes, bytes]]


def values(headers: Headers, name: bytes) -> list[bytes]:
    return [value for key, value in headers if key.lower() == name]


def singleton(headers: Headers, name: bytes) -> bytes | None:
    found = values(headers, name)
    if len(found) > 1:
        raise TransportFailure(403, "local_access_denied", "duplicate_header")
    return found[0] if found else None


class LocalBoundary:
    def __init__(self, app: ASGIApp, config: LocalServerConfig, session: SessionCapability) -> None:
        self.app, self.config, self.session = app, config, session

    def check_authority(self, headers: Headers) -> None:
        found = values(headers, b"host")
        if len(found) != 1:
            raise TransportFailure(400, "http_invalid", "invalid_host")
        host = found[0]
        match = re.fullmatch(
            rb"(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9.])?|"
            rb"\[[0-9A-Fa-f:]+\])(?::([0-9]{1,5}))?",
            host,
        )
        if match is None or (match[1] is not None and not 1 <= int(match[1]) <= 65535):
            raise TransportFailure(400, "http_invalid", "invalid_host")
        if host != self.config.authority.encode("ascii"):
            raise TransportFailure(403, "local_access_denied", "unapproved_host")

    def check_origin(self, headers: Headers, required: bool) -> None:
        origin = singleton(headers, b"origin")
        if (origin is None and required) or (
            origin is not None and origin != self.config.origin.encode("ascii")
        ):
            raise TransportFailure(403, "local_access_denied", "unapproved_origin")

    @staticmethod
    def check_fetch_metadata(headers: Headers, *, api: bool = True) -> None:
        site = singleton(headers, b"sec-fetch-site")
        mode = singleton(headers, b"sec-fetch-mode")
        dest = singleton(headers, b"sec-fetch-dest")
        if site in {b"cross-site", b"same-site"} or (api and site == b"none"):
            raise TransportFailure(403, "local_access_denied", "fetch_metadata")
        if api and (
            mode in {b"navigate", b"no-cors", b"websocket", b"webtransport"}
            or dest
            in {
                b"audio",
                b"audioworklet",
                b"document",
                b"embed",
                b"font",
                b"frame",
                b"iframe",
                b"image",
                b"manifest",
                b"json",
                b"text",
                b"object",
                b"paintworklet",
                b"report",
                b"script",
                b"serviceworker",
                b"sharedworker",
                b"style",
                b"track",
                b"video",
                b"worker",
                b"xslt",
                b"webidentity",
            }
        ):
            raise TransportFailure(403, "local_access_denied", "fetch_metadata")

    @staticmethod
    def query_keys(path: str, method: str | None = None) -> set[str]:
        registrations = r"/api/v1/projects/[^/]+"
        method_rules = (
            (rf"{registrations}/runs", {"GET": {"decision_id", "status", "cursor", "limit"}}),
            (rf"{registrations}/runs/preview", {"POST": {"include_request"}}),
            (
                rf"{registrations}/runs/[^/]+/resume-preview",
                {"POST": {"retry_unknown", "max_attempts"}},
            ),
            (
                rf"{registrations}/runs/[^/]+/results",
                {"GET": {"evaluation_id", "status", "split", "tag", "cursor", "limit"}},
            ),
            (
                rf"{registrations}/runs/[^/]+/results/[^/]+",
                {
                    "GET": {
                        "evaluation_id",
                        "include_input",
                        "include_request",
                        "include_response",
                        "include_attempts",
                    }
                },
            ),
            (rf"{registrations}/runs/[^/]+/evaluations", {"GET": {"cursor", "limit"}}),
            (rf"{registrations}/runs/[^/]+/annotations", {"GET": {"case_id", "cursor", "limit"}}),
            (
                rf"{registrations}/diagnostics/[^/]+/resume-preview",
                {"POST": {"retry_unknown"}},
            ),
            (rf"{registrations}/checks/[^/]+/resume-preview", {"POST": {"retry_unknown"}}),
            (rf"{registrations}/comparisons", {"GET": {"cursor", "limit"}}),
            (rf"{registrations}/reports", {"GET": {"cursor", "limit"}}),
            (rf"{registrations}/reports/[^/]+/download", {"GET": {"format"}}),
        )
        for pattern, methods in method_rules:
            if re.fullmatch(pattern, path):
                if method is None:
                    return set().union(*methods.values())
                return methods.get(method.upper(), set())

        rules = (
            (rf"{registrations}/decisions", {"include_archived", "cursor", "limit"}),
            (rf"{registrations}/decisions/[^/]+/revisions", {"cursor", "limit"}),
            (rf"{registrations}/decisions/[^/]+/diff", {"before", "after"}),
            (rf"{registrations}/datasets", {"include_archived", "cursor", "limit"}),
            (
                rf"{registrations}/datasets/[^/]+/cases",
                {"cursor", "limit", "tag", "group_id", "split"},
            ),
            (
                rf"{registrations}/decisions/[^/]+/datasets/[^/]+/labels",
                {"status", "cursor", "limit"},
            ),
            (
                rf"{registrations}/decisions/[^/]+/datasets/[^/]+/labels/[^/]+(?:/history)?",
                {"question_id"},
            ),
            (rf"{registrations}/providers", {"cursor", "limit"}),
            (rf"{registrations}/fixtures", {"cursor", "limit"}),
            (rf"{registrations}/fixtures/[^/]+", {"include_requests"}),
            (rf"{registrations}/providers/[^/]+/models", {"timeout_seconds"}),
        )
        for pattern, keys in rules:
            if re.fullmatch(pattern, path):
                return keys
        return set()

    @staticmethod
    def _scope(scope: Scope, headers: Headers) -> bytes:
        raw = scope.get("raw_path")
        query = scope.get("query_string", b"")
        if not isinstance(raw, bytes) or len(raw) + len(query) > 8192 or len(query) > 8192:
            raise TransportFailure(414, "http_invalid", "request_target_limit")
        if len(headers) > 128 or sum(len(k) + len(v) + 4 for k, v in headers) > 65536:
            raise TransportFailure(431, "http_invalid", "header_limit")
        if any(
            re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+", k) is None
            or any(c < 32 and c != 9 or c == 127 for c in v)
            for k, v in headers
        ):
            raise TransportFailure(400, "http_invalid", "invalid_header")
        if any(len(k) > 8192 or len(v) > 8192 for k, v in headers):
            raise TransportFailure(431, "http_invalid", "header_limit")
        if (
            re.fullmatch(rb"/[A-Za-z0-9/_-]*", raw) is None
            or b"//" in raw
            or raw.decode("ascii") != scope["path"]
        ):
            # Packaged fingerprinted assets have dots; admit only exact known names below.
            name = scope["path"].removeprefix("/")
            if not (
                raw == scope["path"].encode("ascii", errors="replace")
                and name in scope["deykit.asset_names"]
            ):
                raise TransportFailure(403, "local_access_denied", "invalid_path")
        return raw

    @staticmethod
    def _body_headers(headers: Headers, limit: int) -> int | None:
        lengths = values(headers, b"content-length")
        transfer = values(headers, b"transfer-encoding")
        if (
            len(lengths) > 1
            or len(transfer) > 1
            or (lengths and transfer)
            or (transfer and transfer[0].lower() != b"chunked")
        ):
            raise TransportFailure(400, "http_invalid", "invalid_body_framing")
        declared = None
        if lengths:
            if re.fullmatch(rb"[0-9]{1,20}", lengths[0]) is None:
                raise TransportFailure(400, "http_invalid", "invalid_content_length")
            declared = int(lengths[0])
            if declared > limit:
                raise TransportFailure(413, "payload_too_large", "body_limit")
        encodings = values(headers, b"content-encoding")
        if len(encodings) > 1 or (encodings and encodings[0].lower() != b"identity"):
            raise TransportFailure(415, "unsupported_media_type", "content_encoding")
        types = values(headers, b"content-type")
        if (
            len(types) != 1
            or re.fullmatch(
                rb'application/json(?:\s*;\s*charset\s*=\s*(?:utf-8|"utf-8"))?',
                types[0],
                flags=re.IGNORECASE,
            )
            is None
        ):
            raise TransportFailure(415, "unsupported_media_type", "content_type")
        return declared

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            return
        started = False
        finished = False

        async def guarded_send(message: Message) -> None:
            nonlocal started, finished
            if message["type"] == "http.response.start":
                started = True
                headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower().decode("latin1") not in SECURITY_HEADERS
                    and not k.lower().startswith(b"access-control-allow-")
                ]
                headers.extend((k.encode(), v.encode()) for k, v in SECURITY_HEADERS.items())
                message = {**message, "headers": headers}
            if scope["method"] == "HEAD" and message["type"] == "http.response.body":
                message = {**message, "body": b""}
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                finished = True
            await send(message)

        try:
            headers = scope["headers"]
            scope = {**scope, "deykit.asset_names": self.config.ui_assets.assets}
            raw = self._scope(scope, headers)
            self.check_authority(headers)
            method = scope["method"]
            api = scope["path"].startswith("/api/") or scope["path"] == "/api"
            self.check_origin(headers, required=api and method not in {"GET", "HEAD"})
            self.check_fetch_metadata(headers, api=api)
            if method == "OPTIONS":
                raise TransportFailure(403, "local_access_denied", "preflight_denied")
            if method not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}:
                raise TransportFailure(405, "method_not_allowed", "unsupported_method")
            bootstrap = method == "POST" and raw == b"/api/v1/session/bootstrap"
            if bootstrap:
                if singleton(headers, b"x-deykit-bootstrap") != b"1":
                    raise TransportFailure(403, "local_access_denied", "bootstrap_required")
            elif api:
                capability = singleton(headers, b"x-deykit-capability")
                if capability is None or not self.session.verify(capability):
                    raise TransportFailure(403, "local_access_denied", "capability_required")
            if api:
                if values(headers, b"if-match") or values(headers, b"idempotency-key"):
                    raise TransportFailure(422, "validation_error", "unsupported_transport_header")
                try:
                    query = parse_qsl(
                        scope.get("query_string", b"").decode("ascii"),
                        keep_blank_values=True,
                        strict_parsing=True,
                    )
                except (UnicodeError, ValueError):
                    raise TransportFailure(422, "validation_error", "invalid_query") from None
                keys = [key for key, _ in query]
                if (
                    len(keys) != len(set(keys))
                    or any(
                        key.lower()
                        in {
                            "token",
                            "capability",
                            "api_key",
                            "apikey",
                            "secret",
                            "password",
                            "authorization",
                            "credential",
                            "credential_value",
                            "x-deykit-capability",
                        }
                        for key in keys
                    )
                    or (bootstrap and keys)
                    or not set(keys).issubset(self.query_keys(scope["path"], method))
                ):
                    raise TransportFailure(422, "validation_error", "invalid_query")
                if method not in {"GET", "HEAD"}:
                    limit = 4096 if bootstrap else (16777216)
                    declared = self._body_headers(headers, limit)
                    body = await read_bounded_json(receive, limit)
                    if declared is not None and len(body) != declared:
                        raise TransportFailure(400, "http_invalid", "invalid_content_length")
                    original_receive = receive
                    consumed = False

                    async def buffered_receive() -> Message:
                        nonlocal consumed
                        if not consumed:
                            consumed = True
                            return {"type": "http.request", "body": body, "more_body": False}
                        return await original_receive()

                    receive = buffered_receive
            await self.app(scope, receive, guarded_send)
        except BodyDisconnected:
            return
        except Exception as error:
            if started and finished:
                # Starlette rethrows after its safe500 handler; consume it without logging input.
                return
            if started:
                raise
            await error_response(error)(scope, receive, guarded_send)
