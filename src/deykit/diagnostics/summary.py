"""Group semantic answers by original case without inflating the sample count."""

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from deykit.contracts.json_value import JsonValue
from deykit.contracts.model_admission import ModelInvalid, admit_model
from deykit.contracts.records import CaseResult, ChoiceDefinition
from deykit.diagnostics.orders import DiagnosticInvalid
from deykit.metrics.summary import CaseAssessment, Rate


@dataclass(frozen=True)
class OrderAccuracy:
    accuracy: Rate
    accuracy_exclusions: tuple[tuple[str, int], ...]
    accuracy_label_provenance: tuple[tuple[str, int], ...]
    common_accuracy: Rate
    flips_from_original: Rate

    def source(self) -> dict[str, JsonValue]:
        return {
            "accuracy": self.accuracy.source(),
            "accuracy_exclusions": dict(self.accuracy_exclusions),
            "accuracy_label_provenance": dict(self.accuracy_label_provenance),
            "common_accuracy": self.common_accuracy.source(),
            "flips_from_original": self.flips_from_original.source(),
        }


@dataclass(frozen=True)
class CaseFlips:
    case_id: str
    flipped_from_original: tuple[bool | None, ...]
    flip_rate: Rate

    def source(self) -> dict[str, JsonValue]:
        return {
            "case_id": self.case_id,
            "flipped_from_original": list(self.flipped_from_original),
            "flip_rate": self.flip_rate.source(),
        }


@dataclass(frozen=True)
class OrderAnalysis:
    orders: tuple[OrderAccuracy, ...]
    accuracy_gap: Rate
    common_accuracy_gap: Rate
    cases: tuple[CaseFlips, ...]

    def source(self) -> dict[str, JsonValue]:
        return {
            "orders": [order.source() for order in self.orders],
            "accuracy_gap": self.accuracy_gap.source(),
            "common_accuracy_gap": self.common_accuracy_gap.source(),
            "cases": [case.source() for case in self.cases],
        }


@dataclass(frozen=True)
class CaseSensitivity:
    case_id: str
    option_ids: tuple[str | None, ...]
    statuses: tuple[str, ...]
    observed_disagreement: bool
    fully_observed: bool

    def source(self) -> dict[str, JsonValue]:
        return {
            "case_id": self.case_id,
            "option_ids": list(self.option_ids),
            "statuses": list(self.statuses),
            "observed_disagreement": self.observed_disagreement,
            "fully_observed": self.fully_observed,
        }


@dataclass(frozen=True)
class OrderSummary:
    independent_case_count: int
    order_count: int
    expanded_result_count: int
    fully_observed_case_count: int
    disagreement: Rate
    cases: tuple[CaseSensitivity, ...]
    order_analysis: OrderAnalysis | None = None
    evidence_mode: Literal["fixture", "live"] | None = None

    def source(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "independent_case_count": self.independent_case_count,
            "order_count": self.order_count,
            "expanded_result_count": self.expanded_result_count,
            "fully_observed_case_count": self.fully_observed_case_count,
            "disagreement": self.disagreement.source(),
            "cases": [case.source() for case in self.cases],
            "interpretation": "observed_request_order_sensitivity",
        }
        if self.order_analysis is not None:
            value["order_analysis"] = self.order_analysis.source()
        if self.evidence_mode is not None:
            value["evidence_mode"] = self.evidence_mode
        return value


def summarize_orders(
    definition: ChoiceDefinition,
    case_ids: tuple[str, ...],
    results_by_order: tuple[tuple[CaseResult, ...], ...],
) -> OrderSummary:
    """Compare only stable semantic choices; unavailable responses stay explicit."""
    try:
        definition = admit_model(ChoiceDefinition, definition, "invalid_diagnostic_definition")
        if (
            type(case_ids) is not tuple
            or not case_ids
            or any(type(case_id) is not str for case_id in case_ids)
            or len(case_ids) != len(set(case_ids))
            or type(results_by_order) is not tuple
            or not 1 <= len(results_by_order) <= 4
            or any(type(results) is not tuple for results in results_by_order)
        ):
            raise DiagnosticInvalid("invalid_diagnostic_groups")
        validated = tuple(
            tuple(
                admit_model(CaseResult, result, "invalid_diagnostic_result") for result in results
            )
            for results in results_by_order
        )
    except ModelInvalid as error:
        raise DiagnosticInvalid(str(error)) from None
    question = definition.questions[0]
    options = {option.id for option in question.options}
    for results in validated:
        if tuple(result.case_id for result in results) != case_ids:
            raise DiagnosticInvalid("diagnostic_case_membership_mismatch")
        for result in results:
            if result.answer is not None and (
                result.answer.question_id != question.id or result.answer.option_id not in options
            ):
                raise DiagnosticInvalid("diagnostic_answer_identity_mismatch")
    cases: list[CaseSensitivity] = []
    comparable = 0
    for index, case_id in enumerate(case_ids):
        results = tuple(order[index] for order in validated)
        if len({result.input_hash for result in results}) != 1:
            raise DiagnosticInvalid("diagnostic_input_identity_mismatch")
        answers = tuple(result.answer.option_id if result.answer else None for result in results)
        present = tuple(answer for answer in answers if answer is not None)
        comparable += len(present) >= 2
        cases.append(
            CaseSensitivity(
                case_id,
                answers,
                tuple(result.status for result in results),
                len(set(present)) > 1,
                len(present) == len(results),
            )
        )
    return OrderSummary(
        len(case_ids),
        len(validated),
        len(case_ids) * len(validated),
        sum(case.fully_observed for case in cases),
        Rate.counts(
            sum(case.observed_disagreement for case in cases), comparable, "no_comparable_cases"
        ),
        tuple(cases),
    )


def summarize_order_analysis(
    summary: OrderSummary, assessments: tuple[tuple[CaseAssessment, ...], ...]
) -> OrderAnalysis:
    """Compare evaluated answers on their own and on a shared eligible cohort."""
    if len(assessments) != summary.order_count:
        raise DiagnosticInvalid("diagnostic_assessment_mismatch")
    for order_index, assessment in enumerate(assessments):
        if len(assessment) != len(summary.cases):
            raise DiagnosticInvalid("diagnostic_assessment_mismatch")
        for case, assessed in zip(summary.cases, assessment, strict=True):
            if (
                assessed.case_id != case.case_id
                or assessed.status != case.statuses[order_index]
                or assessed.answer_option_id != case.option_ids[order_index]
            ):
                raise DiagnosticInvalid("diagnostic_assessment_mismatch")

    common = tuple(
        index
        for index in range(len(summary.cases))
        if all(assessment[index].set_correct is not None for assessment in assessments)
    )
    case_flips = []
    for case in summary.cases:
        original = case.option_ids[0]
        flips = (None,) + tuple(
            None if original is None or answer is None else answer != original
            for answer in case.option_ids[1:]
        )
        comparable = tuple(value for value in flips if value is not None)
        case_flips.append(
            CaseFlips(
                case.case_id,
                flips,
                Rate.counts(sum(comparable), len(comparable), "no_comparable_orders"),
            )
        )

    orders = []
    for order_index, assessment in enumerate(assessments):
        exclusions: Counter[str] = Counter()
        for assessed_case in assessment:
            if assessed_case.set_correct is None:
                exclusions.update(assessed_case.exclusion_reasons)
        common_correct = sum(assessment[index].set_correct is True for index in common)
        eligible = tuple(case for case in assessment if case.set_correct is not None)
        provenance = Counter(
            case.label_provenance for case in eligible if case.label_provenance is not None
        )
        if sum(provenance.values()) != len(eligible):
            raise DiagnosticInvalid("diagnostic_label_provenance_missing")
        comparable_flips = tuple(
            case.flipped_from_original[order_index]
            for case in case_flips
            if case.flipped_from_original[order_index] is not None
        )
        orders.append(
            OrderAccuracy(
                Rate.counts(
                    sum(case.set_correct is True for case in eligible),
                    len(eligible),
                    "no_eligible_labels",
                ),
                tuple(sorted(exclusions.items())),
                tuple(sorted(provenance.items())),
                Rate.counts(common_correct, len(common), "no_comparable_labeled_cases"),
                Rate.counts(
                    sum(value is True for value in comparable_flips),
                    len(comparable_flips),
                    "original_order" if order_index == 0 else "no_comparable_cases",
                ),
            )
        )

    if len(orders) < 2:
        gap = Rate.counts(0, 0, "fewer_than_two_orders")
        common_gap = gap
    else:
        available = tuple(value for order in orders if (value := order.accuracy.exact) is not None)
        gap = (
            Rate.fraction(max(available) - min(available), "order_accuracy_unavailable")
            if len(available) == len(orders)
            else Rate.counts(0, 0, "order_accuracy_unavailable")
        )
        if not common:
            common_gap = Rate.counts(0, 0, "no_comparable_labeled_cases")
        else:
            correct_counts = tuple(order.common_accuracy.numerator for order in orders)
            common_gap = Rate.counts(
                max(correct_counts) - min(correct_counts),
                len(common),
                "no_comparable_labeled_cases",
            )
    return OrderAnalysis(tuple(orders), gap, common_gap, tuple(case_flips))
