"""Bounds for owned comparison outcomes, separate from individual user inputs."""

from typing import Annotated

from pydantic import AfterValidator, StringConstraints

from deykit.contracts.json_value import JsonLimits, parse_json

COMPARISON_OUTCOMES_LIMITS = JsonLimits(max_bytes=4 * 1024 * 1024, max_nodes=200_000)


def validate_comparison_source(source: str) -> str:
    parse_json(source, COMPARISON_OUTCOMES_LIMITS)
    return source


ComparisonOutcomesSource = Annotated[
    str, StringConstraints(strict=True), AfterValidator(validate_comparison_source)
]
