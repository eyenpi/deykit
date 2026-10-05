"""Safe provider boundary values; never stringify untrusted exceptions."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from deykit.contracts.redaction import Sanitizer as Sanitizer

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
