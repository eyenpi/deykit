"""Versioned deterministic distinct option orders, independent of Python's RNG."""

from hashlib import sha256

from deykit.contracts.identities import validate_resource_id

ORDER_ALGORITHM = "deykit-choice-order-v1"


class DiagnosticInvalid(ValueError):
    """A safe diagnostic reason, never a repr of supplied values."""


def _next_order(order: tuple[int, ...]) -> tuple[int, ...]:
    values = list(order)
    pivot = len(values) - 2
    while pivot >= 0 and values[pivot] >= values[pivot + 1]:
        pivot -= 1
    if pivot < 0:
        return tuple(reversed(values))
    successor = len(values) - 1
    while values[successor] <= values[pivot]:
        successor -= 1
    values[pivot], values[successor] = values[successor], values[pivot]
    values[pivot + 1 :] = reversed(values[pivot + 1 :])
    return tuple(values)


def choice_orders(
    option_ids: tuple[str, ...], *, orders: int = 4, seed: int = 0
) -> tuple[tuple[str, ...], ...]:
    """Return original order plus up to three distinct seeded alternatives.

    Seeded Fisher-Yates choices use SHA-256 of ASCII algorithm/seed/probe/position.
    This is an exploratory deterministic probe, not a claim of uniform sampling.
    After bounded collision probes, lexicographic successors guarantee progress.
    The factorial cap needs only its saturated value: 2! is 2; n! >= 4 for n >= 3.
    """
    if (
        type(option_ids) is not tuple
        or len(option_ids) < 2
        or len(option_ids) > 10_000
        or type(orders) is not int
        or not 1 <= orders <= 4
        or type(seed) is not int
        or not -(2**63) <= seed < 2**63
    ):
        raise DiagnosticInvalid("invalid_order_expansion")
    try:
        for option_id in option_ids:
            if type(option_id) is not str:
                raise ValueError
            validate_resource_id(option_id)
    except ValueError:
        raise DiagnosticInvalid("invalid_order_option_id") from None
    if len(option_ids) != len(set(option_ids)):
        raise DiagnosticInvalid("duplicate_order_option_id")
    target = min(orders, 2 if len(option_ids) == 2 else 4)
    original = tuple(range(len(option_ids)))
    selected = [original]
    for probe in range(32):
        if len(selected) == target:
            break
        shuffled = list(original)
        for position in range(len(shuffled) - 1, 0, -1):
            digest = sha256(f"{ORDER_ALGORITHM}/{seed}/{probe}/{position}".encode("ascii")).digest()
            chosen = int.from_bytes(digest, "big") % (position + 1)
            shuffled[position], shuffled[chosen] = shuffled[chosen], shuffled[position]
        candidate = tuple(shuffled)
        if candidate not in selected:
            selected.append(candidate)
    candidate = original
    while len(selected) < target:
        candidate = _next_order(candidate)
        if candidate not in selected:
            selected.append(candidate)
    return tuple(tuple(option_ids[index] for index in order) for order in selected)
