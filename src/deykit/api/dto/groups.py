"""Public result records for shared diagnostic and regression-check groups."""

from typing import Literal

from deykit.contracts.base import FrozenModel

from .common import CountText
from .execution import GroupProgressDTO


class DiagnosticViewDTO(FrozenModel):
    group: GroupProgressDTO
    summary: dict[str, object] | None
    exit_code: Literal[0, 3, 4]


class CheckViewDTO(FrozenModel):
    group: GroupProgressDTO
    cases: tuple[dict[str, object], ...]
    expectation_failures: CountText
    baseline_unavailable: Literal["frozen_regression_selection"]
    exit_code: Literal[0, 3, 4, 5]
