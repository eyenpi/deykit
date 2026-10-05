"""Frozen full-development majority baseline with explicit overlap disclosure."""

from dataclasses import dataclass

from deykit.contracts.json_value import JsonDocument, JsonError, JsonValue
from deykit.contracts.model_admission import ModelInvalid, admit_model
from deykit.contracts.records import ChoiceDefinition, DatasetSnapshot, LabelRecord, LabelSnapshot
from deykit.domain.definitions import label_applicability, select_input
from deykit.metrics.summary import MetricsInvalid, Rate


@dataclass(frozen=True)
class MajorityBaseline:
    option_id: str | None
    fit_support: int
    fit_excluded_acceptable_sets: int
    fit_dataset_snapshot_id: str
    fit_label_snapshot_id: str
    evaluation_dataset_snapshot_id: str
    evaluation_label_snapshot_id: str
    evaluation_splits: tuple[str, ...]
    overlap_case_ids: tuple[str, ...]
    selected_count: int
    paired_count: int
    scored_count: int
    accuracy: Rate
    unavailable_reason: str | None = None

    def source(self) -> dict[str, JsonValue]:
        return {
            "option_id": self.option_id,
            "fit_support": self.fit_support,
            "fit_excluded_acceptable_sets": self.fit_excluded_acceptable_sets,
            "fit_dataset_snapshot_id": self.fit_dataset_snapshot_id,
            "fit_label_snapshot_id": self.fit_label_snapshot_id,
            "evaluation_dataset_snapshot_id": self.evaluation_dataset_snapshot_id,
            "evaluation_label_snapshot_id": self.evaluation_label_snapshot_id,
            "evaluation_splits": list(self.evaluation_splits),
            "overlap_case_ids": list(self.overlap_case_ids),
            "selected_count": self.selected_count,
            "paired_count": self.paired_count,
            "scoring_population": "provider_valid_applicable_labels",
            "scored_count": self.scored_count,
            "accuracy": self.accuracy.source(),
            "unavailable_reason": self.unavailable_reason,
        }


def _indexed_labels(
    snapshot: LabelSnapshot, dataset: DatasetSnapshot, question_id: str
) -> dict[str, LabelRecord]:
    if snapshot.dataset_snapshot_id != dataset.id:
        raise MetricsInvalid("label_dataset_snapshot_mismatch")
    indexed: dict[str, LabelRecord] = {}
    seen: set[tuple[str, str]] = set()
    for label in snapshot.labels:
        if label.dataset_id != dataset.dataset_id or label.decision_id != snapshot.decision_id:
            raise MetricsInvalid("frozen_label_context_mismatch")
        key = (label.case_id, label.question_id)
        if key in seen:
            raise MetricsInvalid("duplicate_frozen_label")
        seen.add(key)
        if label.question_id == question_id:
            indexed[label.case_id] = label
    return indexed


def majority_baseline(
    definition: ChoiceDefinition,
    fit_dataset: DatasetSnapshot,
    fit_labels: LabelSnapshot,
    evaluation_dataset: DatasetSnapshot,
    evaluation_labels: LabelSnapshot,
    selected_case_ids: tuple[str, ...],
    paired_case_ids: tuple[str, ...],
) -> MajorityBaseline:
    """Fit only the separately frozen full development source, never current mutable data."""
    try:
        definition = admit_model(ChoiceDefinition, definition, "invalid_definition")
        fit_dataset = admit_model(DatasetSnapshot, fit_dataset, "invalid_dataset_snapshot")
        fit_labels = admit_model(LabelSnapshot, fit_labels, "invalid_label_snapshot")
        evaluation_dataset = admit_model(
            DatasetSnapshot, evaluation_dataset, "invalid_dataset_snapshot"
        )
        evaluation_labels = admit_model(LabelSnapshot, evaluation_labels, "invalid_label_snapshot")
    except ModelInvalid as error:
        raise MetricsInvalid(str(error)) from None
    if fit_labels.decision_id != evaluation_labels.decision_id:
        raise MetricsInvalid("baseline_decision_mismatch")
    if fit_dataset.dataset_id != evaluation_dataset.dataset_id:
        raise MetricsInvalid("baseline_dataset_mismatch")
    if type(selected_case_ids) is not tuple or len(set(selected_case_ids)) != len(
        selected_case_ids
    ):
        raise MetricsInvalid("invalid_baseline_selection")
    if (
        type(paired_case_ids) is not tuple
        or len(set(paired_case_ids)) != len(paired_case_ids)
        or not set(paired_case_ids).issubset(selected_case_ids)
    ):
        raise MetricsInvalid("invalid_baseline_pairing")
    question = definition.questions[0]
    option_ids = tuple(option.id for option in question.options)
    fit_index = _indexed_labels(fit_labels, fit_dataset, question.id)
    evaluation_index = _indexed_labels(evaluation_labels, evaluation_dataset, question.id)
    fit_case_index = {case.id: case for case in fit_dataset.cases}
    evaluation_case_index = {case.id: case for case in evaluation_dataset.cases}
    if (
        len(fit_case_index) != len(fit_dataset.cases)
        or len(evaluation_case_index) != len(evaluation_dataset.cases)
        or any(case_id not in evaluation_case_index for case_id in selected_case_ids)
    ):
        raise MetricsInvalid("baseline_case_mismatch")
    if any(label.case_id not in fit_case_index for label in fit_labels.labels) or any(
        label.case_id not in evaluation_case_index for label in evaluation_labels.labels
    ):
        raise MetricsInvalid("baseline_label_case_mismatch")
    counts = {option_id: 0 for option_id in option_ids}
    fit_ids: set[str] = set()
    excluded_sets = 0
    for case in fit_dataset.cases:
        label = fit_index.get(case.id)
        if case.split != "development" or label is None:
            continue
        input_hash = JsonDocument(case.input_source).content_hash
        if label_applicability(label, definition, input_hash):
            continue
        try:
            select_input(definition, JsonDocument(case.input_source))
        except JsonError:
            continue
        if len(label.acceptable_option_ids) != 1:
            excluded_sets += 1
            continue
        counts[label.acceptable_option_ids[0]] += 1
        fit_ids.add(case.id)
    fit_support = sum(counts.values())
    winner = max(option_ids, key=lambda option: counts[option]) if fit_support else None
    scored = correct = 0
    for case_id in paired_case_ids:
        case = evaluation_case_index[case_id]
        label = evaluation_index.get(case_id)
        if label is None:
            raise MetricsInvalid("baseline_pairing_mismatch")
        input_hash = JsonDocument(case.input_source).content_hash
        if label_applicability(label, definition, input_hash):
            raise MetricsInvalid("baseline_pairing_mismatch")
        try:
            select_input(definition, JsonDocument(case.input_source))
        except JsonError:
            raise MetricsInvalid("baseline_pairing_mismatch") from None
        if winner is not None:
            scored += 1
            correct += int(winner in label.acceptable_option_ids)
    return MajorityBaseline(
        option_id=winner,
        fit_support=fit_support,
        fit_excluded_acceptable_sets=excluded_sets,
        fit_dataset_snapshot_id=fit_dataset.id,
        fit_label_snapshot_id=fit_labels.id,
        evaluation_dataset_snapshot_id=evaluation_dataset.id,
        evaluation_label_snapshot_id=evaluation_labels.id,
        evaluation_splits=tuple(
            sorted({evaluation_case_index[key].split for key in selected_case_ids})
        ),
        overlap_case_ids=tuple(sorted(fit_ids.intersection(paired_case_ids))),
        selected_count=len(selected_case_ids),
        paired_count=len(paired_case_ids),
        scored_count=scored,
        accuracy=Rate.counts(
            correct,
            scored,
            "no_eligible_evaluation_labels" if fit_support else "no_eligible_development_labels",
        ),
        unavailable_reason="no_eligible_development_labels" if winner is None else None,
    )


def unavailable_regression_baseline(
    fit_dataset: DatasetSnapshot,
    fit_labels: LabelSnapshot,
    dataset: DatasetSnapshot,
    labels: LabelSnapshot,
    selected_count: int,
    paired_count: int,
) -> MajorityBaseline:
    """Explicitly unavailable fitting evidence; never fit current or selected regressions."""
    if fit_dataset.cases or fit_labels.labels:
        raise MetricsInvalid("regression_baseline_must_be_empty")
    return MajorityBaseline(
        option_id=None,
        fit_support=0,
        fit_excluded_acceptable_sets=0,
        fit_dataset_snapshot_id=fit_dataset.id,
        fit_label_snapshot_id=fit_labels.id,
        evaluation_dataset_snapshot_id=dataset.id,
        evaluation_label_snapshot_id=labels.id,
        evaluation_splits=tuple(sorted({case.split for case in dataset.cases})),
        overlap_case_ids=(),
        selected_count=selected_count,
        paired_count=paired_count,
        scored_count=0,
        accuracy=Rate.counts(0, 0, "frozen_regression_selection"),
        unavailable_reason="frozen_regression_selection",
    )
