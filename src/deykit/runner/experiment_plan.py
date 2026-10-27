"""Expand configured experiment members and explicitly scoped diagnostics."""

from dataclasses import dataclass
from typing import Literal

from deykit.contracts.experiments import (
    ExperimentCohort,
    ExperimentDecision,
    ExperimentOrder,
    ExperimentRequest,
    ExperimentVariant,
)
from deykit.contracts.records import ChoiceDefinition
from deykit.diagnostics.orders import choice_orders


@dataclass(frozen=True)
class ExperimentMember:
    decision: ExperimentDecision
    cohort: ExperimentCohort
    variant: ExperimentVariant
    purpose: Literal["main", "repeat", "choice_order"]
    diagnostic: str | None = None
    option_order: tuple[str, ...] | None = None


def diagnostic_base_index(request: ExperimentRequest, name: str) -> int:
    diagnostic = next(item for item in request.diagnostics if item.name == name)
    variant_index = next(
        index
        for index, variant in enumerate(request.variants)
        if variant.name == diagnostic.variant
    )
    return request.combination_indices().index(
        (diagnostic.decision_index, diagnostic.cohort_index, variant_index)
    )


def expand_experiment(
    request: ExperimentRequest, definitions: tuple[ChoiceDefinition, ...]
) -> tuple[ExperimentMember, ...]:
    if len(definitions) != len(request.decisions):
        raise ValueError("experiment_definition_count_mismatch")
    members = [
        ExperimentMember(decision, cohort, variant, "main")
        for decision, cohort, variant in request.combinations()
    ]
    variants = {variant.name: variant for variant in request.variants}
    for diagnostic in request.diagnostics:
        decision = request.decisions[diagnostic.decision_index]
        cohort = request.cohorts[diagnostic.cohort_index].model_copy(
            update={"case_ids": diagnostic.case_ids}
        )
        variant = variants[diagnostic.variant]
        if isinstance(diagnostic, ExperimentOrder):
            definition = definitions[diagnostic.decision_index]
            orders = choice_orders(
                tuple(option.id for option in definition.questions[0].options),
                orders=diagnostic.orders,
                seed=diagnostic.seed,
            )
            members.extend(
                ExperimentMember(decision, cohort, variant, "choice_order", diagnostic.name, order)
                for order in orders
            )
        else:
            members.extend(
                ExperimentMember(decision, cohort, variant, "repeat", diagnostic.name)
                for _ in range(diagnostic.count)
            )
    if len(members) > 10_000:
        raise ValueError("too_many_experiment_members")
    return tuple(members)
