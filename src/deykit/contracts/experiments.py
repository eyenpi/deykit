"""Experiment inputs and exact, bounded dollar reservation amounts."""

import re
from itertools import product
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from deykit.contracts.base import FrozenModel
from deykit.contracts.identities import ResourceId
from deykit.contracts.records import ExecutionSettings

_AMOUNT = re.compile(r"(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,9})?\Z")
_SCALE = 1_000_000_000


def amount_units(value: str) -> int:
    if type(value) is not str or not _AMOUNT.fullmatch(value):
        raise ValueError("invalid_estimated_usd")
    whole, _, fraction = value.partition(".")
    return int(whole) * _SCALE + int(fraction.ljust(9, "0") or "0")


def amount_text(units: int) -> str:
    if units == 0:
        return "0"
    whole, fraction = divmod(units, _SCALE)
    if not fraction:
        return str(whole)
    digits = f"{fraction:09d}".rstrip("0")
    return f"{whole}.{digits.ljust(2, '0')}"


class ExperimentDecision(FrozenModel):
    decision_id: ResourceId
    revision_id: ResourceId
    modality: Literal["text", "image"]


class ExperimentCohort(FrozenModel):
    dataset_id: ResourceId
    split: Literal["all", "development", "calibration", "test"] = "all"
    case_ids: tuple[ResourceId, ...] = ()

    @model_validator(mode="after")
    def unique_cases(self) -> Self:
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("duplicate_selected_case")
        return self


class ExperimentVariant(FrozenModel):
    name: ResourceId
    provider_id: ResourceId | None = None
    fixture_set_id: ResourceId | None = None
    reservation_usd: str | None = None

    @field_validator("reservation_usd")
    @classmethod
    def validate_reservation(cls, value: str | None) -> str | None:
        if value is not None:
            amount_units(value)
        return value


class ExperimentSelection(FrozenModel):
    decision_index: Annotated[int, Field(ge=0)]
    cohort_index: Annotated[int, Field(ge=0)]
    variant: ResourceId


class ExperimentRepeat(FrozenModel):
    kind: Literal["repeat"] = "repeat"
    name: ResourceId
    decision_index: Annotated[int, Field(ge=0)]
    cohort_index: Annotated[int, Field(ge=0)]
    variant: ResourceId
    case_ids: Annotated[tuple[ResourceId, ...], Field(min_length=1, max_length=10_000)]
    count: Annotated[int, Field(ge=1, le=10)] = 1


class ExperimentOrder(FrozenModel):
    kind: Literal["choice_order"] = "choice_order"
    name: ResourceId
    decision_index: Annotated[int, Field(ge=0)]
    cohort_index: Annotated[int, Field(ge=0)]
    variant: ResourceId
    case_ids: Annotated[tuple[ResourceId, ...], Field(min_length=1, max_length=10_000)]
    orders: Annotated[int, Field(ge=1, le=4)] = 4
    seed: Annotated[int, Field(ge=-(2**63), lt=2**63)] = 0


class ExperimentRequest(FrozenModel):
    mode: Literal["fixture", "live"]
    decisions: Annotated[tuple[ExperimentDecision, ...], Field(min_length=1, max_length=100)]
    cohorts: Annotated[tuple[ExperimentCohort, ...], Field(min_length=1, max_length=100)]
    variants: Annotated[tuple[ExperimentVariant, ...], Field(min_length=1, max_length=100)]
    include: (
        Annotated[tuple[ExperimentSelection, ...], Field(min_length=1, max_length=10_000)] | None
    ) = None
    settings: ExecutionSettings
    budget_usd: str | None = None
    reuse_group_id: ResourceId | None = None
    diagnostics: Annotated[
        tuple[ExperimentRepeat | ExperimentOrder, ...], Field(max_length=100)
    ] = ()

    @field_validator("budget_usd")
    @classmethod
    def validate_budget(cls, value: str | None) -> str | None:
        if value is not None:
            amount_units(value)
        return value

    @model_validator(mode="after")
    def validate_members(self) -> Self:
        if self.reuse_group_id is not None and self.diagnostics:
            raise ValueError("reused_experiment_cannot_include_fresh_diagnostics")
        if (
            self.include is None
            and len(self.decisions) * len(self.cohorts) * len(self.variants) > 10_000
        ):
            raise ValueError("too_many_experiment_members")
        if len({variant.name for variant in self.variants}) != len(self.variants):
            raise ValueError("duplicate_experiment_variant")
        if len({diagnostic.name for diagnostic in self.diagnostics}) != len(self.diagnostics):
            raise ValueError("duplicate_experiment_diagnostic")
        names = {variant.name for variant in self.variants}
        if self.include is not None:
            selected = {
                (item.decision_index, item.cohort_index, item.variant) for item in self.include
            }
            if (
                len(selected) != len(self.include)
                or {item.decision_index for item in self.include} != set(range(len(self.decisions)))
                or any(
                    item.decision_index >= len(self.decisions)
                    or item.cohort_index >= len(self.cohorts)
                    or item.variant not in names
                    for item in self.include
                )
            ):
                raise ValueError("invalid_experiment_selection")
        for diagnostic in self.diagnostics:
            if (
                diagnostic.decision_index >= len(self.decisions)
                or diagnostic.cohort_index >= len(self.cohorts)
                or diagnostic.variant not in names
                or len(set(diagnostic.case_ids)) != len(diagnostic.case_ids)
                or (
                    self.include is not None
                    and (diagnostic.decision_index, diagnostic.cohort_index, diagnostic.variant)
                    not in selected
                )
            ):
                raise ValueError("invalid_experiment_diagnostic_scope")
        for variant in self.variants:
            if self.mode == "fixture" and (
                variant.fixture_set_id is None or variant.provider_id is not None
            ):
                raise ValueError("fixture_set_required")
            if self.mode == "live" and (
                variant.provider_id is None or variant.fixture_set_id is not None
            ):
                raise ValueError("live_profile_required")
        return self

    def combinations(
        self,
    ) -> tuple[tuple[ExperimentDecision, ExperimentCohort, ExperimentVariant], ...]:
        return tuple(
            (self.decisions[decision], self.cohorts[cohort], self.variants[variant])
            for decision, cohort, variant in self.combination_indices()
        )

    def combination_indices(self) -> tuple[tuple[int, int, int], ...]:
        if self.include is None:
            return tuple(
                product(
                    range(len(self.decisions)), range(len(self.cohorts)), range(len(self.variants))
                )
            )
        variants = {variant.name: index for index, variant in enumerate(self.variants)}
        return tuple(
            sorted(
                (item.decision_index, item.cohort_index, variants[item.variant])
                for item in self.include
            )
        )
