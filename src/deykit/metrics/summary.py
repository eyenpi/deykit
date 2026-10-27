"""Exact set correctness and ordered single-label class arithmetic."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction
from typing import Literal

from deykit.contracts.json_value import JsonValue
from deykit.contracts.model_admission import ModelInvalid, admit_model
from deykit.contracts.records import (
    CaseResult,
    ChoiceDefinition,
    DatasetSnapshot,
    LabelRecord,
    LabelSnapshot,
    ResultSnapshot,
)
from deykit.domain.case_identity import case_input_hash
from deykit.domain.definitions import label_applicability


class MetricsInvalid(ValueError):
    """Safe cross-record incompatibility reason; never embeds user source."""


@dataclass(frozen=True)
class Rate:
    numerator: int
    denominator: int
    reason: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.numerator) is not int
            or type(self.denominator) is not int
            or self.numerator < 0
            or self.denominator < 0
            or self.numerator > self.denominator
            or (self.denominator == 0 and (type(self.reason) is not str or not self.reason))
            or (self.denominator > 0 and self.reason is not None)
        ):
            raise MetricsInvalid("invalid_metric_counts")

    @classmethod
    def counts(cls, numerator: int, denominator: int, reason: str) -> Rate:
        if type(reason) is not str or not reason:
            raise MetricsInvalid("invalid_metric_counts")
        return cls(numerator, denominator, None if denominator else reason)

    @classmethod
    def fraction(cls, value: Fraction | None, reason: str) -> Rate:
        if (
            (value is not None and type(value) is not Fraction)
            or type(reason) is not str
            or not reason
        ):
            raise MetricsInvalid("invalid_metric_counts")
        return cls(value.numerator, value.denominator) if value is not None else cls(0, 0, reason)

    @property
    def exact(self) -> Fraction | None:
        return Fraction(self.numerator, self.denominator) if self.denominator else None

    def source(self) -> dict[str, JsonValue]:
        if self.denominator:
            with localcontext() as context:
                context.prec = 80
                decimal = (Decimal(self.numerator) / Decimal(self.denominator)).quantize(
                    Decimal("0.000001"), rounding=ROUND_HALF_UP
                )
            display: str | None = format(decimal, "f")
        else:
            display = None
        return {
            "numerator": self.numerator,
            "denominator": self.denominator,
            "value": display,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CaseAssessment:
    case_id: str
    status: str
    answer_option_id: str | None
    expected_option_ids: tuple[str, ...]
    label_provenance: str | None
    legacy_question_ids: tuple[str, ...]
    legacy_expected_option_ids: tuple[tuple[str, ...], ...]
    legacy_exclusion_reasons: tuple[tuple[str, ...], ...]
    exclusion_reasons: tuple[str, ...]
    set_correct: bool | None
    single_label_class: bool

    def source(self) -> dict[str, JsonValue]:
        return {
            "case_id": self.case_id,
            "status": self.status,
            "answer_option_id": self.answer_option_id,
            "expected_option_ids": list(self.expected_option_ids),
            "label_provenance": self.label_provenance,
            "legacy_question_ids": list(self.legacy_question_ids),
            "legacy_expected_option_ids": [list(ids) for ids in self.legacy_expected_option_ids],
            "legacy_exclusion_reasons": [
                list(reasons) for reasons in self.legacy_exclusion_reasons
            ],
            "exclusion_reasons": list(self.exclusion_reasons),
            "set_correct": self.set_correct,
            "single_label_class": self.single_label_class,
        }


@dataclass(frozen=True)
class ClassMetric:
    option_id: str
    support: int
    predicted: int
    true_positive: int
    precision: Rate
    recall: Rate
    f1: Rate

    def source(self) -> dict[str, JsonValue]:
        return {
            "option_id": self.option_id,
            "support": self.support,
            "predicted": self.predicted,
            "true_positive": self.true_positive,
            "precision": self.precision.source(),
            "recall": self.recall.source(),
            "f1": self.f1.source(),
        }


Status = Literal["pending", "input_invalid", "response_error", "unknown", "valid"]
STATUSES: tuple[Status, ...] = (
    "pending",
    "input_invalid",
    "response_error",
    "unknown",
    "valid",
)


@dataclass(frozen=True)
class EvaluationSummary:
    selected_count: int
    status_counts: tuple[tuple[str, int], ...]
    coverage: Rate
    set_accuracy: Rate
    eligible_set_count: int
    correct_set_count: int
    single_label_count: int
    unlabelled_valid_count: int
    exclusion_counts: tuple[tuple[str, int], ...]
    option_ids: tuple[str, ...]
    confusion_matrix: tuple[tuple[int, ...], ...]
    classes: tuple[ClassMetric, ...]
    macro_f1: Rate
    macro_f1_class_count: int
    native_confidence_present_count: int
    native_confidence_mean: Rate
    cases: tuple[CaseAssessment, ...]

    def source(self, *, include_cases: bool = False) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "selected_count": self.selected_count,
            "status_counts": dict(self.status_counts),
            "coverage": self.coverage.source(),
            "set_accuracy": self.set_accuracy.source(),
            "eligible_set_count": self.eligible_set_count,
            "correct_set_count": self.correct_set_count,
            "single_label_count": self.single_label_count,
            "unlabelled_valid_count": self.unlabelled_valid_count,
            "exclusion_counts": dict(self.exclusion_counts),
            "option_ids": list(self.option_ids),
            "confusion_matrix": [list(row) for row in self.confusion_matrix],
            "classes": [item.source() for item in self.classes],
            "macro_f1": self.macro_f1.source(),
            "macro_f1_class_count": self.macro_f1_class_count,
            "native_confidence_present_count": self.native_confidence_present_count,
            "native_confidence_mean": self.native_confidence_mean.source(),
        }
        if include_cases:
            value["cases"] = [item.source() for item in self.cases]
        return value


def _label_index(
    labels: LabelSnapshot, dataset: DatasetSnapshot, question_id: str
) -> tuple[dict[str, LabelRecord], dict[str, tuple[LabelRecord, ...]]]:
    indexed: dict[str, LabelRecord] = {}
    legacy: dict[str, list[LabelRecord]] = {}
    seen: set[tuple[str, str]] = set()
    for label in labels.labels:
        if label.dataset_id != dataset.dataset_id or label.decision_id != labels.decision_id:
            raise MetricsInvalid("frozen_label_context_mismatch")
        key = (label.case_id, label.question_id)
        if key in seen:
            raise MetricsInvalid("duplicate_frozen_label")
        seen.add(key)
        if label.question_id == question_id:
            indexed[label.case_id] = label
        else:
            legacy.setdefault(label.case_id, []).append(label)
    return indexed, {
        case: tuple(sorted(items, key=lambda item: item.question_id))
        for case, items in legacy.items()
    }


def _assess_case(
    definition: ChoiceDefinition,
    options: set[str],
    result: CaseResult,
    label: LabelRecord | None,
    legacy_labels: tuple[LabelRecord, ...],
) -> CaseAssessment:
    question = definition.questions[0]
    legacy_reasons = tuple(
        ("incompatible_question_label", *label_applicability(old, definition, result.input_hash))
        for old in legacy_labels
    )
    answer = result.answer if result.status == "valid" else None
    answer_id = answer.option_id if answer is not None else None
    expected = label.acceptable_option_ids if label is not None else ()
    exclusion: list[str] = []
    if answer is None:
        exclusion.append("no_valid_answer")
    if label is None:
        exclusion.append("incompatible_question_label" if legacy_labels else "unlabelled")
        for old_reasons in legacy_reasons:
            for old_reason in old_reasons:
                if old_reason not in exclusion:
                    exclusion.append(old_reason)
    else:
        exclusion.extend(label_applicability(label, definition, result.input_hash))
    if answer is not None and (answer.question_id != question.id or answer_id not in options):
        exclusion.append("incompatible_answer")
    set_correct: bool | None = None
    single = False
    if not exclusion:
        if answer is None:
            raise MetricsInvalid("missing_eligible_answer")
        set_correct = answer_id in expected
        if len(expected) == 1:
            single = True
        else:
            exclusion.append("acceptable_set_excluded_from_class_metrics")
    return CaseAssessment(
        case_id=result.case_id,
        status=result.status,
        answer_option_id=answer_id,
        expected_option_ids=expected,
        label_provenance=label.provenance if label is not None else None,
        legacy_question_ids=tuple(item.question_id for item in legacy_labels),
        legacy_expected_option_ids=tuple(item.acceptable_option_ids for item in legacy_labels),
        legacy_exclusion_reasons=legacy_reasons,
        exclusion_reasons=tuple(exclusion),
        set_correct=set_correct,
        single_label_class=single,
    )


def assess_admitted_cases(
    definition: ChoiceDefinition,
    dataset: DatasetSnapshot,
    labels: LabelSnapshot,
    results: ResultSnapshot,
    selected_case_ids: tuple[str, ...],
) -> tuple[CaseAssessment, ...]:
    """Assess records already admitted at a frozen-evidence boundary."""
    if labels.dataset_snapshot_id != dataset.id:
        raise MetricsInvalid("label_dataset_snapshot_mismatch")
    question = definition.questions[0]
    options = {option.id for option in question.options}
    cases = {case.id: case for case in dataset.cases}
    if len(cases) != len(dataset.cases):
        raise MetricsInvalid("duplicate_frozen_case")
    if (
        type(selected_case_ids) is not tuple
        or len(set(selected_case_ids)) != len(selected_case_ids)
        or tuple(result.case_id for result in results.results) != selected_case_ids
    ):
        raise MetricsInvalid("selected_results_mismatch")
    if len({result.case_id for result in results.results}) != len(results.results):
        raise MetricsInvalid("duplicate_result_case")
    indexed, legacy = _label_index(labels, dataset, question.id)
    if any(label.case_id not in cases for label in labels.labels):
        raise MetricsInvalid("frozen_label_case_mismatch")
    assessments: list[CaseAssessment] = []
    for result in results.results:
        case = cases.get(result.case_id)
        if case is None or case_input_hash(case) != result.input_hash:
            raise MetricsInvalid("result_input_mismatch")
        assessments.append(
            _assess_case(
                definition,
                options,
                result,
                indexed.get(result.case_id),
                legacy.get(result.case_id, ()),
            )
        )
    return tuple(assessments)


def assess_results(
    definition: ChoiceDefinition,
    dataset: DatasetSnapshot,
    labels: LabelSnapshot,
    results: ResultSnapshot,
    selected_case_ids: tuple[str, ...],
) -> EvaluationSummary:
    """Use only supplied immutable records; no current labels or provider calls."""
    try:
        definition = admit_model(ChoiceDefinition, definition, "invalid_definition")
        dataset = admit_model(DatasetSnapshot, dataset, "invalid_dataset_snapshot")
        labels = admit_model(LabelSnapshot, labels, "invalid_label_snapshot")
        results = admit_model(ResultSnapshot, results, "invalid_result_snapshot")
    except ModelInvalid as error:
        raise MetricsInvalid(str(error)) from None
    assessments = assess_admitted_cases(definition, dataset, labels, results, selected_case_ids)
    option_ids = tuple(option.id for option in definition.questions[0].options)
    status_counts = {status: 0 for status in STATUSES}
    reasons: dict[str, int] = {}
    matrix = [[0 for _ in option_ids] for _ in option_ids]
    positions = {option_id: index for index, option_id in enumerate(option_ids)}
    eligible = correct = singles = unlabelled_valid = native_confidence = 0

    for result, assessed in zip(results.results, assessments, strict=True):
        status_counts[result.status] += 1
        answer = result.answer if result.status == "valid" else None
        if answer is not None and "unlabelled" in assessed.exclusion_reasons:
            unlabelled_valid += 1
        if answer is not None and answer.native_confidence_source is not None:
            native_confidence += 1
        if assessed.set_correct is not None:
            eligible += 1
            correct += int(assessed.set_correct)
            if assessed.single_label_class:
                if answer is None:
                    raise MetricsInvalid("missing_eligible_answer")
                singles += 1
                matrix[positions[assessed.expected_option_ids[0]]][positions[answer.option_id]] += 1
        for reason in assessed.exclusion_reasons:
            reasons[reason] = reasons.get(reason, 0) + 1

    classes: list[ClassMetric] = []
    defined_f1: list[Fraction] = []
    for index, option_id in enumerate(option_ids):
        support = sum(matrix[index])
        predicted = sum(row[index] for row in matrix)
        tp = matrix[index][index]
        fp, fn = predicted - tp, support - tp
        f1 = Rate.counts(2 * tp, 2 * tp + fp + fn, "no_class_evidence")
        if f1.exact is not None:
            defined_f1.append(f1.exact)
        classes.append(
            ClassMetric(
                option_id,
                support,
                predicted,
                tp,
                Rate.counts(tp, predicted, "no_predictions"),
                Rate.counts(tp, support, "no_expected_cases"),
                f1,
            )
        )
    macro = sum(defined_f1, Fraction(0)) / len(defined_f1) if defined_f1 else None
    return EvaluationSummary(
        selected_count=len(results.results),
        status_counts=tuple(status_counts.items()),
        coverage=Rate.counts(status_counts["valid"], len(results.results), "no_selected_cases"),
        set_accuracy=Rate.counts(correct, eligible, "no_eligible_labels"),
        eligible_set_count=eligible,
        correct_set_count=correct,
        single_label_count=singles,
        unlabelled_valid_count=unlabelled_valid,
        exclusion_counts=tuple(sorted(reasons.items())),
        option_ids=option_ids,
        confusion_matrix=tuple(tuple(row) for row in matrix),
        classes=tuple(classes),
        macro_f1=Rate.fraction(macro, "no_class_evidence"),
        macro_f1_class_count=len(defined_f1),
        native_confidence_present_count=native_confidence,
        native_confidence_mean=Rate(
            0,
            0,
            "native_confidence_not_calibrated"
            if native_confidence
            else "native_confidence_unavailable",
        ),
        cases=tuple(assessments),
    )
