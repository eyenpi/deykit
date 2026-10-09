"""Bound and exactly preflight envelopes before Pydantic/HTTP JSON decoding."""

from starlette.types import Receive

from deykit.contracts.json_value import JsonLimits, parse_json

from .errors import TransportFailure


class BodyDisconnected(Exception):
    """No complete body was admitted; the router must never run."""


async def read_bounded_json(receive: Receive, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            raise BodyDisconnected
        if message["type"] != "http.request":
            raise TransportFailure(400, "http_invalid", "invalid_body_event")
        body = message.get("body", b"")
        size += len(body)
        if size > limit:
            raise TransportFailure(413, "payload_too_large", "body_limit")
        chunks.append(body)
        if not message.get("more_body", False):
            break
    source = b"".join(chunks)
    parse_json(source, JsonLimits(max_bytes=limit, max_depth=256, max_nodes=1_000_000))
    return source
