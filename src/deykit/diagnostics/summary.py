"""Group semantic answers by original case without inflating the sample count."""

from dataclasses import dataclass

from deykit.contracts.json_value import JsonValue
from deykit.contracts.model_admission import ModelInvalid, admit_model
from deykit.contracts.records import CaseResult, ChoiceDefinition
from deykit.diagnostics.orders import DiagnosticInvalid
from deykit.metrics.summary import Rate


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

    def source(self) -> dict[str, JsonValue]:
        return {
            "independent_case_count": self.independent_case_count,
            "order_count": self.order_count,
            "expanded_result_count": self.expanded_result_count,
            "fully_observed_case_count": self.fully_observed_case_count,
            "disagreement": self.disagreement.source(),
            "cases": [case.source() for case in self.cases],
            "interpretation": "observed_request_order_sensitivity",
        }


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
