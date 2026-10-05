"""Pure exact-ratio connected-component splitting with a versioned deterministic heuristic."""

from decimal import Decimal
from fractions import Fraction
from typing import Literal

from deykit.contracts.json_value import JsonDocument, parse_json, semantic_hash
from deykit.contracts.records import CaseRecord

Split = Literal["development", "calibration", "test"]
SPLITS: tuple[Split, ...] = ("development", "calibration", "test")
ALGORITHM = "connected-greedy-squared-v1"
DEFAULT_RATIOS = '{"development":0.8,"test":0.2}'


def ratios(source: str) -> tuple[Fraction, ...]:
    if not isinstance(source, str):
        raise ValueError("invalid_split_ratios")
    value = parse_json(source)
    if not isinstance(value, dict) or not value or set(value) - set(SPLITS):
        raise ValueError("invalid_split_ratios")
    result: list[Fraction] = []
    for split in SPLITS:
        number = value.get(split, Decimal(0))
        if not isinstance(number, Decimal) or number < 0 or number > 1:
            raise ValueError("invalid_split_ratios")
        result.append(Fraction(number))
    if sum(result) != 1:
        raise ValueError("split_ratios_must_sum_to_one")
    return tuple(result)


def connected_groups(cases: tuple[CaseRecord, ...]) -> tuple[tuple[str, ...], ...]:
    parents: dict[str, str] = {}

    def root(key: str) -> str:
        parents.setdefault(key, key)
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key

    def union(left: str, right: str) -> None:
        a, b = root(left), root(right)
        if a != b:
            parents[max(a, b)] = min(a, b)

    if len({case.id for case in cases}) != len(cases):
        raise ValueError("duplicate_case_id")
    for case in cases:
        key = "case:" + case.id
        root(key)
        if case.group_id is not None:
            union(key, "group:" + case.group_id)
        union(key, "input:" + JsonDocument(case.input_source).content_hash)
        for ancestor in case.derived_from:
            union(key, "case:" + ancestor)
    groups: dict[str, list[str]] = {}
    for case in cases:
        groups.setdefault(root("case:" + case.id), []).append(case.id)
    return tuple(sorted(tuple(sorted(group)) for group in groups.values()))


def assign(
    cases: tuple[CaseRecord, ...], seed: int, ratios_source: str = DEFAULT_RATIOS
) -> tuple[tuple[str, Split], ...]:
    if type(seed) is not int:
        raise ValueError("invalid_split_seed")
    weights = ratios(ratios_source)
    counts = [0, 0, 0]
    total = len(cases)
    assignments: list[tuple[str, Split]] = []
    groups = sorted(
        connected_groups(cases),
        key=lambda group: (-len(group), semantic_hash([seed, list(group)]), group),
    )
    for group in groups:
        size = len(group)
        # Minimize the increase in squared count error; exact rational arithmetic avoids
        # platform/context rounding. Zero-ratio destinations never receive a group.
        chosen = min(
            (i for i in range(3) if weights[i] > 0),
            key=lambda i: (
                2 * size * (counts[i] - total * weights[i]) + size * size,
                semantic_hash([seed, list(group), SPLITS[i]]),
                i,
            ),
        )
        counts[chosen] += size
        assignments.extend((case, SPLITS[chosen]) for case in group)
    return tuple(sorted(assignments))


def validate_assignments(
    cases: tuple[CaseRecord, ...], assignments: tuple[tuple[str, Split], ...]
) -> None:
    if not isinstance(assignments, tuple) or any(
        not isinstance(pair, tuple)
        or len(pair) != 2
        or any(not isinstance(value, str) for value in pair)
        for pair in assignments
    ):
        raise ValueError("invalid_split_assignments")
    if any(split not in SPLITS for _, split in assignments):
        raise ValueError("invalid_split")
    if len({case for case, _ in assignments}) != len(assignments):
        raise ValueError("duplicate_split_assignment")
    mapping = dict(assignments)
    if set(mapping) != {case.id for case in cases}:
        raise ValueError("split_requires_all_current_cases")
    if any(len({mapping[key] for key in group}) != 1 for group in connected_groups(cases)):
        raise ValueError("conflicting_group_assignments")
