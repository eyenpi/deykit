"""Safe provider boundary values; never stringify untrusted exceptions."""

import logging
import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"authorization|proxy.authorization|api.?key|access.?token|password|secret|cookie|headers",
    re.IGNORECASE,
)
_BEARER = re.compile(r"\bBearer\s+[^\s\"',;\]}]+", re.IGNORECASE)


class Sanitizer:
    """Redact known credential values and credential-bearing structured fields."""

    def __init__(self, secrets: Sequence[str] = ()) -> None:
        self._secrets = tuple(sorted({s for s in secrets if s}, key=len, reverse=True))

    def __repr__(self) -> str:
        return "Sanitizer(<redacted>)"

    def text(self, value: str) -> str:
        for secret in self._secrets:
            value = value.replace(secret, "[REDACTED]")
        return _BEARER.sub("Bearer [REDACTED]", value)

    def value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, Mapping):
            return {
                self.text(str(key)): "[REDACTED]"
                if _SENSITIVE_KEY.search(str(key))
                else self.value(item)
                for key, item in value.items()
            }
        if isinstance(value, (tuple, list)):
            return [self.value(item) for item in value]
        if value is None or isinstance(value, (bool, int, float, Decimal)):
            return value
        # Arbitrary objects may have credential-bearing repr/str implementations.
        return "[REDACTED]"


# HTTP core debug traces include complete response headers, which can echo a key.
# A context-local filter suppresses library transport records only for our request;
# other callers/threads and application logs retain their original configuration.

_authenticated_transport: ContextVar[bool] = ContextVar(
    "deykit_authenticated_transport", default=False
)


class _AuthenticatedTransportFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _authenticated_transport.get()


_transport_filter = _AuthenticatedTransportFilter()
_TRANSPORT_LOGGERS = (
    "httpx",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
)


@contextmanager
def quiet_authenticated_transport() -> Iterator[None]:
    for name in _TRANSPORT_LOGGERS:
        logging.getLogger(name).addFilter(_transport_filter)
    token = _authenticated_transport.set(True)
    try:
        yield
    finally:
        _authenticated_transport.reset(token)
