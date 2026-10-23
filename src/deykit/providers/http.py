"""One-shot HTTP boundary. Retry scheduling belongs exclusively to the runner."""

import asyncio
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Literal

import httpx

from deykit.contracts.errors import ServiceError
from deykit.contracts.records import DispatchOutcome
from deykit.providers.choice import JEV_DESTINATION, MODELS_DESTINATION
from deykit.providers.jev_images import IMAGE_HEADERS_SOURCE
from deykit.providers.openai_choice import DESTINATION as OPENAI_DESTINATION
from deykit.providers.safety import quiet_authenticated_transport


@dataclass(frozen=True)
class HttpReply:
    status: int
    body: bytes
    retry_after_seconds: Decimal | None = None


class HttpFailure(Exception):
    def __init__(self, kind: Literal["timeout", "disconnect", "response_too_large"]) -> None:
        self.kind = kind
        super().__init__(f"Provider transport failed: {kind}; execution outcome is unknown.")


def retry_after(value: str | None, now: datetime) -> Decimal | None:
    if value is None:
        return None
    try:
        seconds = Decimal(value)
        if seconds.is_finite() and seconds >= 0:
            return seconds
        return None
    except InvalidOperation:
        pass
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            return None
        return max(Decimal(0), Decimal(str((date - now).total_seconds())))
    except (ValueError, TypeError, OverflowError):
        return None


class OneShotHttp:
    """A fresh client per attempt, strict destination and bounded response bytes.

    Supplying a transport is for controlled tests; production constructs AsyncHTTPTransport
    with zero retries. No client injection permits enabling authenticated redirects.
    """

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_response_bytes: int = 1_048_576,
    ) -> None:
        if max_response_bytes <= 0:
            raise ValueError("Response byte limit must be positive.")
        self._transport = transport
        self._now = now
        self._max_response_bytes = max_response_bytes

    async def send(
        self,
        method: Literal["GET", "POST"],
        destination: str,
        body: bytes | None,
        credential: str,
        timeout_seconds: float,
        *,
        semantic_headers_source: str = "{}",
    ) -> HttpReply:
        allowed = (method == "POST" and destination in {JEV_DESTINATION, OPENAI_DESTINATION}) or (
            method == "GET" and destination == MODELS_DESTINATION and body is None
        )
        if not allowed:
            raise ValueError("Provider destination or method is not permitted.")
        if semantic_headers_source not in {"{}", IMAGE_HEADERS_SOURCE} or (
            (method != "POST" or destination != JEV_DESTINATION) and semantic_headers_source != "{}"
        ):
            raise ValueError("Provider semantic headers are not permitted.")
        from deykit.contracts.json_value import parse_json

        semantic_headers = parse_json(semantic_headers_source)
        assert isinstance(semantic_headers, dict)
        if not 0 < timeout_seconds <= 600:
            raise ValueError("Request timeout must be positive and at most 600 seconds.")
        if (
            not credential
            or not credential.isascii()
            or any(ord(c) < 33 or ord(c) > 126 for c in credential)
        ):
            raise ValueError("Credential cannot form a valid authorization value.")
        transport = self._transport or httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        reply: HttpReply | None = None
        try:
            # HTTPX phase timeouts are inactivity bounds; this scope additionally
            # bounds the whole exchange, including many individually timely chunks.
            with quiet_authenticated_transport():
                async with (
                    asyncio.timeout_at(deadline),
                    httpx.AsyncClient(
                        transport=transport,
                        follow_redirects=False,
                        trust_env=False,
                        timeout=timeout_seconds,
                    ) as client,
                ):
                    async with client.stream(
                        method,
                        destination,
                        content=body,
                        headers={
                            "Authorization": "Bearer " + credential,
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                            **{key: str(value) for key, value in semantic_headers.items()},
                        },
                    ) as response:
                        delay = retry_after(response.headers.get("retry-after"), self._now())
                        if response.status_code != 200:
                            # No error payload is needed for status classification. Preserve
                            # a definitive rejection even when its body/close fails later.
                            reply = HttpReply(response.status_code, b"", delay)
                        else:
                            chunks: list[bytes] = []
                            size = 0
                            async for chunk in response.aiter_bytes():
                                size += len(chunk)
                                if size > self._max_response_bytes:
                                    raise HttpFailure("response_too_large")
                                chunks.append(chunk)
                            reply = HttpReply(response.status_code, b"".join(chunks), delay)
            if reply.status == 200 and asyncio.get_running_loop().time() >= deadline:
                raise HttpFailure("timeout")
            return reply
        except (TimeoutError, httpx.TimeoutException):
            if reply is not None and reply.status != 200:
                return reply
            raise HttpFailure("timeout") from None
        except (httpx.HTTPError, OSError):
            if reply is not None and reply.status != 200:
                return reply
            raise HttpFailure("disconnect") from None


def dispatch_failure(reply: HttpReply) -> DispatchOutcome | None:
    status = reply.status
    if status == 200:
        return None
    if status in {401, 403}:
        return DispatchOutcome(
            state="known", error=ServiceError(code="provider_auth"), provider_wide=True
        )
    if status in {400, 413}:
        return DispatchOutcome(
            state="known",
            error=ServiceError(
                code="provider_rejected",
                reason="invalid_payload" if status == 400 else "payload_too_large",
            ),
        )
    if status == 422:
        return DispatchOutcome(
            state="known",
            error=ServiceError(code="provider_rejected", reason="invalid_payload"),
            provider_wide=True,
        )
    if status in {429, 529}:
        delay = float(reply.retry_after_seconds) if reply.retry_after_seconds is not None else None
        # A finite Decimal can overflow float. An unrepresentable delay means stop
        # scheduling rather than silently shorten the provider's backoff instruction.
        if delay is not None and not math.isfinite(delay):
            return DispatchOutcome(
                state="known",
                error=ServiceError(code="provider_rejected", reason="retry_delay_out_of_range"),
                provider_wide=True,
            )
        return DispatchOutcome(
            state="known",
            error=ServiceError(
                code="provider_rejected", reason="rate_limit" if status == 429 else "overloaded"
            ),
            retryable=True,
            retry_after_seconds=delay,
        )
    return DispatchOutcome(
        state="unknown",
        error=ServiceError(code="provider_rejected", reason="unexpected_http_status"),
        provider_wide=True,
    )
