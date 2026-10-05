"""Pure credential-field and known-secret redaction for explicit evidence views."""

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, cast

from deykit.contracts.json_value import JsonValue

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


def safe_choice_response(value: JsonValue, sanitizer: Sanitizer) -> JsonValue:
    """Preserve typed question/option ID maps while sanitizing response metadata."""
    result = cast(JsonValue, sanitizer.value(value))
    if not isinstance(value, dict) or not isinstance(result, dict):
        return result
    original_answers = value.get("answers")
    if not isinstance(original_answers, dict):
        return result
    answers: dict[str, JsonValue] = {}
    for question_id, item in original_answers.items():
        safe_item = cast(JsonValue, sanitizer.value(item))
        probabilities = item.get("probabilities") if isinstance(item, dict) else None
        if isinstance(safe_item, dict) and isinstance(probabilities, dict):
            safe_item["probabilities"] = {
                sanitizer.text(option_id): cast(JsonValue, sanitizer.value(probability))
                for option_id, probability in probabilities.items()
            }
        answers[sanitizer.text(question_id)] = safe_item
    result["answers"] = answers
    return result
