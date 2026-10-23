"""Exact numeric admission shared by choice provider wire formats."""

from decimal import Decimal, localcontext

from deykit.contracts.json_value import JsonValue

TOLERANCE = Decimal("0.000001")


class ResponseInvalid(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Provider response failed validation: {reason}.")


def object_value(value: JsonValue, reason: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ResponseInvalid(reason)
    return value


def probability(value: JsonValue, reason: str) -> Decimal:
    if type(value) is int:
        value = Decimal(value)
    if not isinstance(value, Decimal) or not value.is_finite() or not 0 <= value <= 1:
        raise ResponseInvalid(reason)
    return value


def usage_count(value: JsonValue) -> int:
    if type(value) is int:
        value = Decimal(value)
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or value < 0
        or value != value.to_integral_value()
    ):
        raise ResponseInvalid("invalid_usage")
    return int(value)


def validate_distribution(values: dict[str, Decimal], choice: str) -> None:
    # Exceeds the exact codec's bounds; ambient precision must not change admission.
    with localcontext() as context:
        context.prec = 30_000
        if abs(sum(values.values(), Decimal(0)) - 1) > TOLERANCE:
            raise ResponseInvalid("invalid_probability_sum")
        if max(values.values()) - values[choice] > TOLERANCE:
            raise ResponseInvalid("choice_not_argmax")
