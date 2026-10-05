"""Reported usage is explicit; unknown totals and cost never become zero."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from deykit.contracts.json_value import JsonError, JsonValue, parse_json
from deykit.metrics.summary import MetricsInvalid


@dataclass(frozen=True)
class UsageSummary:
    mode: Literal["live", "fixture"]
    dispatched_attempt_count: int
    reported_attempt_count: int
    reported_input_tokens: int | None
    reported_output_tokens: int | None
    total_input_tokens: int | None
    total_output_tokens: int | None
    source_kind: str | None
    reported_at: str | None
    reason: str | None

    def source(self) -> dict[str, JsonValue]:
        return {
            "mode": self.mode,
            "dispatched_attempt_count": self.dispatched_attempt_count,
            "reported_attempt_count": self.reported_attempt_count,
            "reported_input_tokens": self.reported_input_tokens,
            "reported_output_tokens": self.reported_output_tokens,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "source_kind": self.source_kind,
            "reported_at": self.reported_at,
            "reason": self.reason,
            "cost": None,
            "cost_reason": "pricing_source_unavailable",
        }


def _tokens(value: JsonValue) -> int:
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or value < 0
        or value != value.to_integral_value()
    ):
        raise MetricsInvalid("invalid_reported_usage")
    return int(value)


def reported_usage(
    mode: Literal["live", "fixture"],
    usage_sources: tuple[str | None, ...],
    *,
    reported_at: str | None = None,
) -> UsageSummary:
    if mode not in ("live", "fixture") or type(usage_sources) is not tuple:
        raise MetricsInvalid("invalid_usage_source")
    if mode == "fixture":
        return UsageSummary(mode, 0, 0, None, None, None, None, None, None, "fixture_no_usage")
    inputs = outputs = reported = 0
    for source in usage_sources:
        if source is None:
            continue
        if type(source) is not str:
            raise MetricsInvalid("invalid_usage_source")
        try:
            value = parse_json(source)
        except JsonError:
            raise MetricsInvalid("invalid_reported_usage") from None
        if not isinstance(value, dict):
            raise MetricsInvalid("invalid_reported_usage")
        inputs += _tokens(value.get("input_tokens"))
        outputs += _tokens(value.get("output_tokens"))
        reported += 1
    complete = bool(usage_sources) and reported == len(usage_sources)
    return UsageSummary(
        mode=mode,
        dispatched_attempt_count=len(usage_sources),
        reported_attempt_count=reported,
        reported_input_tokens=inputs if reported else None,
        reported_output_tokens=outputs if reported else None,
        total_input_tokens=inputs if complete else None,
        total_output_tokens=outputs if complete else None,
        source_kind="provider_reported" if reported else None,
        reported_at=reported_at if reported else None,
        reason=None if complete else "partial_reported_usage" if reported else "usage_not_reported",
    )
