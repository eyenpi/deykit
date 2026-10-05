"""Pure credential-field and known-secret redaction for explicit evidence views."""

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"authorization|proxy.authorization|api.?key|access.?token|password|secret|cookie|headers",
    re.IGNORECASE,
)
_BEARER = re.compile(r"\bBearer\s+[^\s\"',;\]}]+", re.IGNORECASE)


class Sanitizer:
    """Redact credential fields, Bearer tokens, and optional known values."""

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
