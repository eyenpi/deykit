"""Current choice response primitives for provider adapters."""

from decimal import Decimal

from deykit.domain.choice_response import ResponseInvalid as ResponseInvalid
from deykit.domain.choice_response import (
    object_value_v1,
    probability_v1,
    usage_count_v1,
    validate_distribution_v1,
)

TOLERANCE = Decimal("0.000001")
object_value = object_value_v1
probability = probability_v1
usage_count = usage_count_v1


def validate_distribution(values: dict[str, Decimal], choice: str) -> None:
    validate_distribution_v1(values, choice, tolerance=TOLERANCE)
