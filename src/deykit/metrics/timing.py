"""Nearest-rank latency from recorded fresh live dispatch durations only."""

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from deykit.contracts.json_value import JsonValue
from deykit.metrics.summary import MetricsInvalid


@dataclass(frozen=True)
class LatencySummary:
    mode: Literal["live", "fixture"]
    sample_count: int
    p50_seconds: str | None
    p95_seconds: str | None
    reason: str | None

    def source(self) -> dict[str, JsonValue]:
        return {
            "mode": self.mode,
            "sample_count": self.sample_count,
            "p50_seconds": self.p50_seconds,
            "p95_seconds": self.p95_seconds,
            "reason": self.reason,
            "method": "nearest_rank",
        }


def live_latency(
    mode: Literal["live", "fixture"], durations_seconds: tuple[Decimal | float | int, ...]
) -> LatencySummary:
    if mode not in ("live", "fixture") or type(durations_seconds) is not tuple:
        raise MetricsInvalid("invalid_latency_source")
    if mode == "fixture":
        return LatencySummary(mode, 0, None, None, "fixture_has_no_live_latency")
    durations: list[Decimal] = []
    for value in durations_seconds:
        if type(value) is bool or type(value) not in (Decimal, float, int):
            raise MetricsInvalid("invalid_latency_source")
        if type(value) is float and not math.isfinite(value):
            raise MetricsInvalid("invalid_latency_source")
        decimal = Decimal(str(value))
        if not decimal.is_finite() or decimal < 0:
            raise MetricsInvalid("invalid_latency_source")
        durations.append(decimal)
    if not durations:
        return LatencySummary(mode, 0, None, None, "no_recorded_live_durations")
    durations.sort()
    count = len(durations)

    def nearest(percent: int) -> str:
        index = (percent * count + 99) // 100 - 1
        return format(durations[index], "f")

    return LatencySummary(mode, count, nearest(50), nearest(95), None)
