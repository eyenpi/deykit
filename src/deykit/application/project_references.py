"""Pure application-level admission of references between captured project records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, cast

from deykit.application.annotations import annotation_hash
from deykit.application.comparisons import admit_comparison_from_records
from deykit.application.errors import ServiceFailure
from deykit.application.labels import admit_label_record
from deykit.application.reports import admit_report_from_records
from deykit.application.splits import admit_dataset_snapshot
from deykit.contracts.base import Record
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ErrorCode, ServiceError
from deykit.contracts.evidence import evidence_hash
from deykit.contracts.execution_groups import (
    CheckSnapshot,
    DiagnosticSnapshot,
    ExecutionGroup,
    ExecutionGroupSegment,
    RegressionRemoval,
)
from deykit.contracts.images import ImageAsset
from deykit.contracts.json_value import JsonDocument, JsonError
from deykit.contracts.ports import Collection, ResourceKey, StoredRecord
from deykit.contracts.records import (
    AttemptEvent,
    AttemptRecord,
    CaseRecord,
    ComparisonRecord,
    DatasetRecord,
    DatasetSnapshot,
    DecisionDraft,
    DecisionRecord,
    DecisionRevision,
    EvaluationRecord,
    FixtureSet,
    LabelChange,
    LabelRecord,
    LabelSnapshot,
    PreparedCase,
    ProjectRecord,
    ProviderProfile,
    RegressionRecord,
    ReportRecord,
    ResultAnnotation,
    ResultSnapshot,
    RunControl,
    RunEvent,
    RunManifest,
    RunSegment,
)
from deykit.domain.case_identity import case_input_hash
from deykit.domain.definitions import definition_hash
from deykit.domain.label_identity import label_id
from deykit.providers.fixtures import validate_fixture_set
from deykit.reports.admission import ReportAdmissionError, admit_report_metadata


@dataclass(frozen=True)
class ReferenceValidation:
    warnings: tuple[ServiceError, ...] = ()


_MODELS: dict[Collection, type[Record]] = {
    "project": ProjectRecord,
    "decisions": DecisionRecord,
    "drafts": DecisionDraft,
    "revisions": DecisionRevision,
    "datasets": DatasetRecord,
    "cases": CaseRecord,
    "image_assets": ImageAsset,
    "labels": LabelRecord,
    "label_history": LabelChange,
    "dataset_snapshots": DatasetSnapshot,
    "label_snapshots": LabelSnapshot,
    "providers": ProviderProfile,
    "fixtures": FixtureSet,
    "runs": RunManifest,
    "prepared_cases": PreparedCase,
    "run_controls": RunControl,
    "segments": RunSegment,
    "run_events": RunEvent,
    "attempts": AttemptRecord,
    "attempt_events": AttemptEvent,
    "result_snapshots": ResultSnapshot,
    "evaluations": EvaluationRecord,
    "annotations": ResultAnnotation,
    "comparisons": ComparisonRecord,
    "execution_groups": ExecutionGroup,
    "group_segments": ExecutionGroupSegment,
    "diagnostic_snapshots": DiagnosticSnapshot,
    "check_snapshots": CheckSnapshot,
    "regression_removals": RegressionRemoval,
    "regressions": RegressionRecord,
    "reports": ReportRecord,
}
_SCOPE_FIELDS: dict[Collection, tuple[str, ...]] = {
    "revisions": ("decision_id",),
    "cases": ("dataset_id",),
    "labels": ("decision_id", "dataset_id"),
    "label_history": ("decision_id", "dataset_id"),
    "prepared_cases": ("run_id",),
    "run_controls": ("run_id",),
    "segments": ("run_id",),
    "run_events": ("run_id",),
    "attempts": ("run_id",),
    "attempt_events": ("attempt_id",),
    "group_segments": ("group_id",),
    "regression_removals": ("decision_id",),
}


def _ordered(records: tuple[StoredRecord, ...]) -> tuple[StoredRecord, ...]:
    return tuple(
        sorted(
            records,
            key=lambda item: (
                item.key.collection,
                item.key.scope,
                item.key.resource_id,
            ),
        )
    )


def _failure(reason: str, record: StoredRecord, code: ErrorCode = "incompatible_data") -> NoReturn:
    raise ServiceFailure(
        ServiceError(code=code, reason=reason, resource_id=record.key.resource_id)
    ) from None


class _CapturedProject:
    def __init__(self, records: tuple[StoredRecord, ...]) -> None:
        self.records = _ordered(records)
        self.index: dict[ResourceKey, StoredRecord] = {}
        self.values: dict[ResourceKey, Record] = {}
        self.by_collection: dict[Collection, list[StoredRecord]] = {
            collection: [] for collection in _MODELS
        }
        for stored in self.records:
            if stored.key in self.index:
                _failure("project_reference_duplicate", stored)
            self.index[stored.key] = stored
            self.by_collection[stored.key.collection].append(stored)
            try:
                value = load_record(_MODELS[stored.key.collection], stored.body)
            except JsonError:
                _failure("invalid_project_record", stored, "validation_error")
            if getattr(value, "decision_id" if stored.key.collection == "drafts" else "id") != (
                stored.key.resource_id
            ):
                _failure("project_reference_wrong_owner", stored)
            scope = tuple(
                getattr(value, field) for field in _SCOPE_FIELDS.get(stored.key.collection, ())
            )
            if stored.key.scope != scope:
                _failure("project_reference_wrong_owner", stored)
            self.values[stored.key] = value
        for stored, value in self.all("labels"):
            if isinstance(value, LabelRecord):
                admit_label_record(stored)
        for stored, value in self.all("label_history"):
            if isinstance(value, LabelChange) and value.label is not None:
                if value.label.id != label_id(value.case_id, value.question_id):
                    _failure("label_identity_mismatch", stored)
                if (
                    value.label.decision_id,
                    value.label.dataset_id,
                    value.label.case_id,
                    value.label.question_id,
                ) != (value.decision_id, value.dataset_id, value.case_id, value.question_id):
                    _failure("label_identity_mismatch", stored)
        for stored, value in self.all("label_snapshots"):
            if not isinstance(value, LabelSnapshot):
                continue
            identities: set[tuple[str, str]] = set()
            for label in value.labels:
                identity = (label.case_id, label.question_id)
                if identity in identities or label.id != label_id(*identity):
                    _failure("label_identity_mismatch", stored)
                identities.add(identity)

    def all(self, collection: Collection) -> tuple[tuple[StoredRecord, Record], ...]:
        return tuple((stored, self.values[stored.key]) for stored in self.by_collection[collection])

    def get(
        self,
        referring: StoredRecord,
        collection: Collection,
        resource_id: str,
        scope: tuple[str, ...] = (),
    ) -> tuple[StoredRecord, Record]:
        exact_key = ResourceKey(collection, resource_id, scope)
        stored = self.index.get(exact_key)
        if stored is not None:
            return stored, self.values[exact_key]
        alternatives = tuple(
            item for item in self.by_collection[collection] if item.key.resource_id == resource_id
        )
        reason = "project_reference_wrong_owner" if alternatives else "project_reference_missing"
        _failure(reason, referring)

    def unique_by_id(
        self, referring: StoredRecord, collection: Collection, resource_id: str
    ) -> tuple[StoredRecord, Record]:
        matches = tuple(
            item for item in self.by_collection[collection] if item.key.resource_id == resource_id
        )
        if len(matches) != 1:
            reason = (
                "project_reference_ambiguous" if len(matches) > 1 else "project_reference_missing"
            )
            _failure(reason, referring)
        stored = matches[0]
        return stored, self.values[stored.key]


def validate_project_references(
    records: tuple[StoredRecord, ...],
) -> ReferenceValidation:
    """Validate explicit hard links in every captured record without source capabilities."""
    captured = _CapturedProject(records)
    projects = captured.by_collection["project"]
    if len(projects) != 1:
        if projects:
            _failure("project_reference_duplicate", projects[0])
        raise ServiceFailure(ServiceError(code="validation_error", reason="project_record_missing"))

    _validate_hard_references(captured)
    warnings = _validate_run_histories(captured)
    _validate_decisions(captured)
    _validate_datasets_and_labels(captured)
    _validate_fixtures_and_runs(captured)
    _validate_run_children(captured)
    _validate_evaluations_and_comparisons(captured)
    _validate_groups(captured)
    _validate_regressions_reports(captured, warnings)
    return ReferenceValidation(
        tuple(
            warning
            for _stored, warning in sorted(
                warnings,
                key=lambda item: (
                    item[0].key.collection,
                    item[0].key.scope,
                    item[0].key.resource_id,
                    item[1].reason or "",
                ),
            )
        )
    )


def _validate_run_histories(
    captured: _CapturedProject,
) -> list[tuple[StoredRecord, ServiceError]]:
    from deykit.runner.history import history_from_records

    warnings: list[tuple[StoredRecord, ServiceError]] = []
    child_collections: tuple[Collection, ...] = (
        "prepared_cases",
        "run_controls",
        "segments",
        "run_events",
        "attempts",
        "result_snapshots",
        "evaluations",
        "annotations",
    )
    children_by_run = {
        run_id
        for collection in child_collections
        for stored, value in captured.all(collection)
        if (run_id := getattr(value, "run_id", None)) is not None
    }
    children_by_run.update(
        member.run_id
        for _stored, group in captured.all("execution_groups")
        if isinstance(group, ExecutionGroup)
        for member in group.members
    )
    for stored, value in captured.all("runs"):
        if not isinstance(value, RunManifest):
            continue
        is_executable = (
            value.decision_id is not None
            and value.dataset_id is not None
            and value.provider is not None
            and value.baseline_dataset_snapshot_id is not None
            and value.baseline_label_snapshot_id is not None
        )
        if not is_executable:
            if value.id in children_by_run:
                _failure("legacy_run_not_executable", stored)
            warnings.append(
                (
                    stored,
                    ServiceError(
                        code="incompatible_data",
                        reason="legacy_run_not_executable",
                        resource_id=value.id,
                    ),
                )
            )
            continue
        history_from_records(captured.records, value.id, verify_group=False)
    return warnings


def _validate_hard_references(captured: _CapturedProject) -> None:
    """Resolve every declared hard link before hashes or legacy classification."""
    for stored, value in captured.all("project"):
        if isinstance(value, ProjectRecord) and value.default_provider_id is not None:
            captured.get(stored, "providers", value.default_provider_id)
    for stored, value in captured.all("drafts"):
        if isinstance(value, DecisionDraft):
            captured.get(stored, "decisions", value.decision_id)
            if value.base_revision_id is not None:
                captured.get(stored, "revisions", value.base_revision_id, (value.decision_id,))
    for stored, value in captured.all("decisions"):
        if isinstance(value, DecisionRecord):
            captured.get(stored, "drafts", value.id)
            if value.latest_revision_id is not None:
                captured.get(stored, "revisions", value.latest_revision_id, (value.id,))
    for stored, value in captured.all("revisions"):
        if isinstance(value, DecisionRevision):
            captured.get(stored, "decisions", value.decision_id)
    for stored, value in captured.all("cases"):
        if isinstance(value, CaseRecord):
            captured.get(stored, "datasets", value.dataset_id)
            for image in value.images:
                _, asset = captured.get(stored, "image_assets", image.asset_id)
                if (
                    not isinstance(asset, ImageAsset)
                    or asset.source.content_hash != image.source_hash
                ):
                    _failure("image_asset_changed", stored)
    for stored, value in captured.all("labels"):
        if isinstance(value, LabelRecord):
            captured.get(stored, "decisions", value.decision_id)
            captured.get(stored, "datasets", value.dataset_id)
            captured.get(stored, "cases", value.case_id, (value.dataset_id,))
    for stored, value in captured.all("label_history"):
        if isinstance(value, LabelChange):
            captured.get(stored, "decisions", value.decision_id)
            captured.get(stored, "datasets", value.dataset_id)
            if value.label is not None and (
                value.label.decision_id != value.decision_id
                or value.label.dataset_id != value.dataset_id
                or value.label.case_id != value.case_id
                or value.label.question_id != value.question_id
            ):
                _failure("label_identity_mismatch", stored)
    for stored, value in captured.all("dataset_snapshots"):
        if isinstance(value, DatasetSnapshot):
            captured.get(stored, "datasets", value.dataset_id)
            for case in value.cases:
                for image in case.images:
                    _, asset = captured.get(stored, "image_assets", image.asset_id)
                    if (
                        not isinstance(asset, ImageAsset)
                        or asset.source.content_hash != image.source_hash
                    ):
                        _failure("image_asset_changed", stored)
    for stored, value in captured.all("label_snapshots"):
        if isinstance(value, LabelSnapshot):
            captured.get(stored, "decisions", value.decision_id)
            _, dataset_value = captured.get(stored, "dataset_snapshots", value.dataset_snapshot_id)
            if isinstance(dataset_value, DatasetSnapshot) and any(
                label.dataset_id != dataset_value.dataset_id
                or label.decision_id != value.decision_id
                or label.case_id not in {case.id for case in dataset_value.cases}
                for label in value.labels
            ):
                _failure("label_snapshot_identity_mismatch", stored)
    for stored, value in captured.all("fixtures"):
        if isinstance(value, FixtureSet):
            captured.get(stored, "decisions", value.decision_id)
            captured.get(stored, "datasets", value.dataset_id)
    for stored, value in captured.all("runs"):
        if not isinstance(value, RunManifest):
            continue
        if value.decision_id is not None:
            captured.get(stored, "decisions", value.decision_id)
            captured.get(stored, "revisions", value.decision_revision_id, (value.decision_id,))
        else:
            captured.unique_by_id(stored, "revisions", value.decision_revision_id)
        if value.dataset_id is not None:
            captured.get(stored, "datasets", value.dataset_id)
        _, dataset_value = captured.get(stored, "dataset_snapshots", value.dataset_snapshot_id)
        _, label_value = captured.get(stored, "label_snapshots", value.label_snapshot_id)
        if (
            isinstance(dataset_value, DatasetSnapshot)
            and value.dataset_id is not None
            and dataset_value.dataset_id != value.dataset_id
        ) or (
            isinstance(label_value, LabelSnapshot)
            and (
                label_value.dataset_snapshot_id != value.dataset_snapshot_id
                or (value.decision_id is not None and label_value.decision_id != value.decision_id)
            )
        ):
            _failure("project_reference_wrong_owner", stored)
        if value.baseline_dataset_snapshot_id is not None:
            baseline_stored, baseline_value = captured.get(
                stored, "dataset_snapshots", value.baseline_dataset_snapshot_id
            )
            if (
                isinstance(baseline_value, DatasetSnapshot)
                and value.dataset_id is not None
                and (baseline_value.dataset_id != value.dataset_id)
            ):
                _failure("project_reference_wrong_owner", baseline_stored)
        if value.baseline_label_snapshot_id is not None:
            baseline_label_stored, baseline_label = captured.get(
                stored, "label_snapshots", value.baseline_label_snapshot_id
            )
            if isinstance(baseline_label, LabelSnapshot) and (
                baseline_label.dataset_snapshot_id != value.baseline_dataset_snapshot_id
                or (
                    value.decision_id is not None
                    and baseline_label.decision_id != value.decision_id
                )
            ):
                _failure("project_reference_wrong_owner", baseline_label_stored)
        if value.fixture_set_id is not None:
            captured.get(stored, "fixtures", value.fixture_set_id)
        if value.execution_group_id is not None:
            captured.get(stored, "execution_groups", value.execution_group_id)
        for regression_id in value.regression_ids:
            captured.get(stored, "regressions", regression_id)
    collections: tuple[Collection, ...] = (
        "prepared_cases",
        "run_controls",
        "segments",
        "run_events",
        "attempts",
    )
    for collection in collections:
        for stored, value in captured.all(collection):
            run_child = cast(
                PreparedCase | RunControl | RunSegment | RunEvent | AttemptRecord, value
            )
            captured.get(stored, "runs", run_child.run_id)
    for stored, value in captured.all("prepared_cases"):
        if not isinstance(value, PreparedCase):
            continue
        run_value = captured.values[ResourceKey("runs", value.run_id)]
        if isinstance(run_value, RunManifest) and value.case_id not in run_value.case_ids:
            _failure("project_reference_wrong_owner", stored)
    for stored, value in captured.all("run_events"):
        if not isinstance(value, RunEvent):
            continue
        if value.segment_id is not None:
            captured.get(stored, "segments", value.segment_id, (value.run_id,))
        if value.attempt_id is not None:
            captured.get(stored, "attempts", value.attempt_id, (value.run_id,))
    for stored, value in captured.all("attempts"):
        if not isinstance(value, AttemptRecord):
            continue
        captured.get(stored, "segments", value.segment_id, (value.run_id,))
        run_value = captured.values[ResourceKey("runs", value.run_id)]
        if isinstance(run_value, RunManifest) and value.case_id not in run_value.case_ids:
            _failure("project_reference_wrong_owner", stored)
        if value.prior_attempt_id is not None:
            prior_stored, prior_value = captured.get(
                stored, "attempts", value.prior_attempt_id, (value.run_id,)
            )
            if not isinstance(prior_value, AttemptRecord) or prior_value.case_id != value.case_id:
                _failure("project_reference_wrong_owner", prior_stored)
    for stored, value in captured.all("attempt_events"):
        if isinstance(value, AttemptEvent):
            attempt_stored, attempt_value = captured.unique_by_id(
                stored, "attempts", value.attempt_id
            )
            if not isinstance(attempt_value, AttemptRecord):
                _failure("project_reference_wrong_owner", attempt_stored)
            captured.get(stored, "attempts", value.attempt_id, (attempt_value.run_id,))
    for stored, value in captured.all("result_snapshots"):
        if isinstance(value, ResultSnapshot):
            captured.get(stored, "runs", value.run_id)
            run_value = captured.values[ResourceKey("runs", value.run_id)]
            if not isinstance(run_value, RunManifest):
                _failure("project_reference_wrong_owner", stored)
            for result in value.results:
                if result.case_id not in run_value.case_ids:
                    _failure("project_reference_wrong_owner", stored)
                if result.attempt_id is not None:
                    attempt_stored, attempt_value = captured.get(
                        stored, "attempts", result.attempt_id, (value.run_id,)
                    )
                    if not isinstance(attempt_value, AttemptRecord) or (
                        attempt_value.case_id != result.case_id
                    ):
                        _failure("project_reference_wrong_owner", attempt_stored)
    for stored, value in captured.all("evaluations"):
        if isinstance(value, EvaluationRecord):
            captured.get(stored, "runs", value.run_id)
            result_stored, result_value = captured.get(
                stored, "result_snapshots", value.result_snapshot_id
            )
            label_stored, label_value = captured.get(
                stored, "label_snapshots", value.label_snapshot_id
            )
            if not isinstance(result_value, ResultSnapshot) or result_value.run_id != value.run_id:
                _failure("project_reference_wrong_owner", result_stored)
            run_value = captured.values[ResourceKey("runs", value.run_id)]
            if (
                isinstance(run_value, RunManifest)
                and isinstance(label_value, LabelSnapshot)
                and (
                    label_value.decision_id != run_value.decision_id
                    or label_value.dataset_snapshot_id != run_value.dataset_snapshot_id
                )
            ):
                _failure("project_reference_wrong_owner", label_stored)
    for stored, value in captured.all("annotations"):
        if isinstance(value, ResultAnnotation):
            _, run_value = captured.get(stored, "runs", value.run_id)
            if not isinstance(run_value, RunManifest) or value.case_id not in run_value.case_ids:
                _failure("project_reference_wrong_owner", stored)
            if value.content_hash != annotation_hash(value.run_id, value.case_id, value.note):
                _failure("annotation_hash_mismatch", stored)
    for stored, value in captured.all("comparisons"):
        if isinstance(value, ComparisonRecord):
            left_stored, left_value = captured.get(stored, "evaluations", value.left_evaluation_id)
            right_stored, right_value = captured.get(
                stored, "evaluations", value.right_evaluation_id
            )
            captured.get(stored, "result_snapshots", value.left_result_snapshot_id)
            captured.get(stored, "result_snapshots", value.right_result_snapshot_id)
            if not isinstance(left_value, EvaluationRecord) or (
                left_value.result_snapshot_id != value.left_result_snapshot_id
            ):
                _failure("project_reference_wrong_owner", left_stored)
            if not isinstance(right_value, EvaluationRecord) or (
                right_value.result_snapshot_id != value.right_result_snapshot_id
            ):
                _failure("project_reference_wrong_owner", right_stored)
    for stored, value in captured.all("execution_groups"):
        if isinstance(value, ExecutionGroup):
            for run_member in value.members:
                captured.get(stored, "runs", run_member.run_id)
    for stored, value in captured.all("group_segments"):
        if isinstance(value, ExecutionGroupSegment):
            captured.get(stored, "execution_groups", value.group_id)
            for segment_member in value.member_segments:
                captured.get(
                    stored,
                    "segments",
                    segment_member.segment_id,
                    (segment_member.run_id,),
                )
    for stored, value in captured.all("diagnostic_snapshots"):
        if isinstance(value, DiagnosticSnapshot):
            captured.get(stored, "execution_groups", value.group_id)
            for diagnostic_member in value.results:
                run_stored, run_value = captured.get(stored, "runs", diagnostic_member.run_id)
                result_stored, result_value = captured.get(
                    stored, "result_snapshots", diagnostic_member.result_snapshot_id
                )
                if (
                    not isinstance(run_value, RunManifest)
                    or not isinstance(result_value, ResultSnapshot)
                    or result_value.run_id != diagnostic_member.run_id
                ):
                    _failure("project_reference_wrong_owner", result_stored)
    for stored, value in captured.all("check_snapshots"):
        if isinstance(value, CheckSnapshot):
            captured.get(stored, "execution_groups", value.group_id)
            for check_member in value.results:
                captured.get(stored, "runs", check_member.run_id)
                result_stored, result_value = captured.get(
                    stored, "result_snapshots", check_member.result_snapshot_id
                )
                if not isinstance(result_value, ResultSnapshot) or (
                    result_value.run_id != check_member.run_id
                ):
                    _failure("project_reference_wrong_owner", result_stored)
    for stored, value in captured.all("regressions"):
        if not isinstance(value, RegressionRecord):
            continue
        if value.decision_id is not None:
            captured.get(stored, "decisions", value.decision_id)
            captured.get(stored, "revisions", value.decision_revision_id, (value.decision_id,))
        else:
            captured.unique_by_id(stored, "revisions", value.decision_revision_id)
        captured.get(stored, "datasets", value.dataset_id)
        if value.source_run_id is not None:
            captured.get(stored, "runs", value.source_run_id)
        if value.source_result_snapshot_id is not None:
            captured.get(stored, "result_snapshots", value.source_result_snapshot_id)
        if value.source_attempt_id is not None:
            captured.unique_by_id(stored, "attempts", value.source_attempt_id)
    for stored, value in captured.all("regression_removals"):
        if isinstance(value, RegressionRemoval):
            captured.get(stored, "regressions", value.regression_id)
            captured.get(stored, "decisions", value.decision_id)
    for stored, value in captured.all("reports"):
        if not isinstance(value, ReportRecord):
            continue
        for resource_id in value.evaluation_ids:
            captured.get(stored, "evaluations", resource_id)
        for resource_id in value.result_snapshot_ids:
            captured.get(stored, "result_snapshots", resource_id)
        for resource_id in value.label_snapshot_ids:
            captured.get(stored, "label_snapshots", resource_id)
        if value.comparison_id is not None:
            captured.get(stored, "comparisons", value.comparison_id)
        if value.diagnostic_snapshot_id is not None:
            captured.get(stored, "diagnostic_snapshots", value.diagnostic_snapshot_id)
        if value.check_snapshot_id is not None:
            captured.get(stored, "check_snapshots", value.check_snapshot_id)


def _validate_decisions(captured: _CapturedProject) -> None:
    for project_stored, project_value in captured.all("project"):
        project = project_value
        if isinstance(project, ProjectRecord) and project.default_provider_id is not None:
            captured.get(project_stored, "providers", project.default_provider_id)
    for stored, value in captured.all("decisions"):
        if isinstance(value, DecisionRecord):
            captured.get(stored, "drafts", value.id)
            if value.latest_revision_id is not None:
                captured.get(stored, "revisions", value.latest_revision_id, (value.id,))
    for stored, value in captured.all("drafts"):
        if not isinstance(value, DecisionDraft):
            continue
        captured.get(stored, "decisions", value.decision_id)
        if value.base_revision_id is not None:
            captured.get(stored, "revisions", value.base_revision_id, (value.decision_id,))
    for stored, value in captured.all("revisions"):
        if isinstance(value, DecisionRevision):
            captured.get(stored, "decisions", value.decision_id)
            if definition_hash(value.definition) != value.content_hash:
                _failure("revision_hash_mismatch", stored)


def _validate_datasets_and_labels(captured: _CapturedProject) -> None:
    for stored, value in captured.all("cases"):
        if isinstance(value, CaseRecord):
            captured.get(stored, "datasets", value.dataset_id)
    for stored, value in captured.all("labels"):
        if not isinstance(value, LabelRecord):
            continue
        label = admit_label_record(stored)
        captured.get(stored, "decisions", label.decision_id)
        captured.get(stored, "datasets", label.dataset_id)
        captured.get(stored, "cases", label.case_id, (label.dataset_id,))
    for stored, value in captured.all("label_history"):
        if not isinstance(value, LabelChange):
            continue
        captured.get(stored, "decisions", value.decision_id)
        captured.get(stored, "datasets", value.dataset_id)
        if stored.key.scope != (value.decision_id, value.dataset_id):
            _failure("project_reference_wrong_owner", stored)
        if value.label is not None:
            label = value.label
            if label.id != label_id(value.case_id, value.question_id):
                _failure("label_identity_mismatch", stored)
            if (
                label.decision_id,
                label.dataset_id,
                label.case_id,
                label.question_id,
            ) != (value.decision_id, value.dataset_id, value.case_id, value.question_id):
                _failure("label_identity_mismatch", stored)
    for stored, value in captured.all("dataset_snapshots"):
        if isinstance(value, DatasetSnapshot):
            captured.get(stored, "datasets", value.dataset_id)
            admit_dataset_snapshot(value)
    for stored, value in captured.all("label_snapshots"):
        if not isinstance(value, LabelSnapshot):
            continue
        captured.get(stored, "decisions", value.decision_id)
        _, dataset_value = captured.get(stored, "dataset_snapshots", value.dataset_snapshot_id)
        if not isinstance(dataset_value, DatasetSnapshot):
            _failure("project_reference_wrong_owner", stored)
        case_ids = {case.id for case in dataset_value.cases}
        identities: set[tuple[str, str]] = set()
        for label in value.labels:
            identity = (label.case_id, label.question_id)
            if (
                identity in identities
                or label.decision_id != value.decision_id
                or label.dataset_id != dataset_value.dataset_id
                or label.case_id not in case_ids
                or label.id != label_id(label.case_id, label.question_id)
            ):
                _failure("label_snapshot_identity_mismatch", stored)
            identities.add(identity)
        if value.content_hash != evidence_hash(tuple(dump_record(label) for label in value.labels)):
            _failure("label_snapshot_hash_mismatch", stored)


def _validate_fixtures_and_runs(captured: _CapturedProject) -> None:
    for stored, value in captured.all("fixtures"):
        if not isinstance(value, FixtureSet):
            continue
        try:
            validate_fixture_set(value)
        except ValueError:
            _failure("fixture_set_invalid", stored)
        captured.get(stored, "decisions", value.decision_id)
        captured.get(stored, "datasets", value.dataset_id)

    for stored, value in captured.all("runs"):
        if not isinstance(value, RunManifest):
            continue
        if value.decision_id is not None:
            captured.get(stored, "decisions", value.decision_id)
            captured.get(stored, "revisions", value.decision_revision_id, (value.decision_id,))
        else:
            captured.unique_by_id(stored, "revisions", value.decision_revision_id)
        if value.dataset_id is not None:
            captured.get(stored, "datasets", value.dataset_id)
        dataset_snapshot_stored, dataset_snapshot = captured.get(
            stored, "dataset_snapshots", value.dataset_snapshot_id
        )
        label_snapshot_stored, label_snapshot = captured.get(
            stored, "label_snapshots", value.label_snapshot_id
        )
        if not isinstance(dataset_snapshot, DatasetSnapshot) or not isinstance(
            label_snapshot, LabelSnapshot
        ):
            _failure("project_reference_wrong_owner", stored)
        if value.dataset_id is not None and dataset_snapshot.dataset_id != value.dataset_id:
            _failure("project_reference_wrong_owner", stored)
        if label_snapshot.dataset_snapshot_id != value.dataset_snapshot_id or (
            value.decision_id is not None and label_snapshot.decision_id != value.decision_id
        ):
            _failure("project_reference_wrong_owner", stored)
        if value.baseline_dataset_snapshot_id is not None:
            baseline_stored, baseline_value = captured.get(
                stored, "dataset_snapshots", value.baseline_dataset_snapshot_id
            )
            if (
                isinstance(baseline_value, DatasetSnapshot)
                and value.dataset_id is not None
                and (baseline_value.dataset_id != value.dataset_id)
            ):
                _failure("project_reference_wrong_owner", baseline_stored)
        if value.baseline_label_snapshot_id is not None:
            baseline_label_stored, baseline_label = captured.get(
                stored, "label_snapshots", value.baseline_label_snapshot_id
            )
            if isinstance(baseline_label, LabelSnapshot) and (
                baseline_label.dataset_snapshot_id != value.baseline_dataset_snapshot_id
                or (
                    value.decision_id is not None
                    and baseline_label.decision_id != value.decision_id
                )
            ):
                _failure("project_reference_wrong_owner", baseline_label_stored)
        if value.fixture_set_id is not None:
            fixture_stored, fixture_value = captured.get(stored, "fixtures", value.fixture_set_id)
            if (
                not isinstance(fixture_value, FixtureSet)
                or (
                    value.decision_id is not None and fixture_value.decision_id != value.decision_id
                )
                or (value.dataset_id is not None and fixture_value.dataset_id != value.dataset_id)
            ):
                _failure("project_reference_wrong_owner", fixture_stored)


def _validate_run_children(captured: _CapturedProject) -> None:
    collections: tuple[Collection, ...] = (
        "prepared_cases",
        "run_controls",
        "segments",
        "run_events",
        "attempts",
    )
    for collection in collections:
        for stored, value in captured.all(collection):
            run_child = cast(
                PreparedCase | RunControl | RunSegment | RunEvent | AttemptRecord, value
            )
            run_id = run_child.run_id
            captured.get(stored, "runs", run_id)
    for stored, value in captured.all("attempt_events"):
        if not isinstance(value, AttemptEvent):
            continue
        _, attempt_value = captured.unique_by_id(stored, "attempts", value.attempt_id)
        if not isinstance(attempt_value, AttemptRecord):
            _failure("project_reference_wrong_owner", stored)
        captured.get(stored, "attempts", value.attempt_id, (attempt_value.run_id,))


def _validate_evaluations_and_comparisons(captured: _CapturedProject) -> None:
    from deykit.application.evaluations import (
        admit_evaluation_record,
        frozen_evaluation_from_records,
    )

    for _stored, value in captured.all("result_snapshots"):
        if isinstance(value, ResultSnapshot):
            frozen_evaluation_from_records(
                captured.records, value.run_id, value.id, None, "original"
            )
    for stored, value in captured.all("evaluations"):
        if not isinstance(value, EvaluationRecord):
            continue
        captured.get(stored, "runs", value.run_id)
        result_stored, result_value = captured.get(
            stored, "result_snapshots", value.result_snapshot_id
        )
        label_stored, label_value = captured.get(stored, "label_snapshots", value.label_snapshot_id)
        if not isinstance(result_value, ResultSnapshot) or not isinstance(
            label_value, LabelSnapshot
        ):
            _failure("project_reference_wrong_owner", stored)
        if result_value.run_id != value.run_id:
            _failure("project_reference_wrong_owner", result_stored)
        run_value = captured.values[ResourceKey("runs", value.run_id)]
        if isinstance(run_value, RunManifest) and (
            label_value.decision_id != run_value.decision_id
            or label_value.dataset_snapshot_id != run_value.dataset_snapshot_id
        ):
            _failure("project_reference_wrong_owner", label_stored)
        admit_evaluation_record(stored)
        frozen_evaluation_from_records(
            captured.records,
            value.run_id,
            value.result_snapshot_id,
            value.label_snapshot_id,
            value.mode,
        )
    for stored, value in captured.all("annotations"):
        if not isinstance(value, ResultAnnotation):
            continue
        _, run_value = captured.get(stored, "runs", value.run_id)
        if not isinstance(run_value, RunManifest) or value.case_id not in run_value.case_ids:
            _failure("project_reference_wrong_owner", stored)
    for stored, value in captured.all("comparisons"):
        if not isinstance(value, ComparisonRecord):
            continue
        left_stored, left_value = captured.get(stored, "evaluations", value.left_evaluation_id)
        right_stored, right_value = captured.get(stored, "evaluations", value.right_evaluation_id)
        if not isinstance(left_value, EvaluationRecord) or not isinstance(
            right_value, EvaluationRecord
        ):
            _failure("project_reference_wrong_owner", stored)
        if left_value.result_snapshot_id != value.left_result_snapshot_id:
            _failure("project_reference_wrong_owner", left_stored)
        if right_value.result_snapshot_id != value.right_result_snapshot_id:
            _failure("project_reference_wrong_owner", right_stored)
        captured.get(stored, "result_snapshots", value.left_result_snapshot_id)
        captured.get(stored, "result_snapshots", value.right_result_snapshot_id)
        admit_comparison_from_records(stored, captured.records)


def _validate_groups(captured: _CapturedProject) -> None:
    from deykit.application.checks import check_snapshot_from_records
    from deykit.application.diagnostics import diagnostic_snapshot_from_records
    from deykit.runner.group_evidence import admit_group_snapshots

    group_ids = tuple(
        record.key.resource_id for record in captured.by_collection["execution_groups"]
    )
    for group_id in group_ids:
        admit_group_snapshots(captured.records, group_id)
    for stored, value in captured.all("group_segments"):
        if isinstance(value, ExecutionGroupSegment):
            captured.get(stored, "execution_groups", value.group_id)
    for _stored, value in captured.all("diagnostic_snapshots"):
        if isinstance(value, DiagnosticSnapshot):
            diagnostic_snapshot_from_records(captured.records, value.id)
    for _stored, value in captured.all("check_snapshots"):
        if isinstance(value, CheckSnapshot):
            check_snapshot_from_records(captured.records, value.id)


def _validate_regressions_reports(
    captured: _CapturedProject,
    warnings: list[tuple[StoredRecord, ServiceError]],
) -> None:
    from deykit.application.regressions import executable_regression
    from deykit.regressions.evidence import admit_regression_origin, regression_hash

    for stored, value in captured.all("regressions"):
        if not isinstance(value, RegressionRecord):
            continue
        if value.decision_id is not None:
            captured.get(stored, "decisions", value.decision_id)
            captured.get(stored, "revisions", value.decision_revision_id, (value.decision_id,))
        else:
            captured.unique_by_id(stored, "revisions", value.decision_revision_id)
        captured.get(stored, "datasets", value.dataset_id)
        revision_stored, revision_value = (
            captured.get(
                stored,
                "revisions",
                value.decision_revision_id,
                (value.decision_id,),
            )
            if value.decision_id is not None
            else captured.unique_by_id(stored, "revisions", value.decision_revision_id)
        )
        if not isinstance(revision_value, DecisionRevision):
            _failure("project_reference_wrong_owner", revision_stored)
        question = next(
            (item for item in revision_value.definition.questions if item.id == value.question_id),
            None,
        )
        if (
            question is None
            or len(set(value.acceptable_option_ids)) != len(value.acceptable_option_ids)
            or not set(value.acceptable_option_ids).issubset(
                {option.id for option in question.options}
            )
        ):
            _failure("regression_evidence_mismatch", stored)
        try:
            input_hash = (
                case_input_hash(value.source_case)
                if value.source_case is not None
                else JsonDocument(value.input_source).content_hash
            )
        except JsonError:
            _failure("regression_evidence_mismatch", stored)
        if input_hash != value.input_hash:
            _failure("regression_evidence_mismatch", stored)
        if value.content_hash is not None and value.content_hash != regression_hash(value):
            _failure("regression_evidence_mismatch", stored)
        linked_run_id = value.source_run_id
        result_value: ResultSnapshot | None = None
        if value.source_result_snapshot_id is not None:
            result_stored, result_record = captured.get(
                stored, "result_snapshots", value.source_result_snapshot_id
            )
            if not isinstance(result_record, ResultSnapshot):
                _failure("project_reference_wrong_owner", result_stored)
            result_value = result_record
            if linked_run_id is not None and result_value.run_id != linked_run_id:
                _failure("regression_evidence_mismatch", stored)
            linked_run_id = result_value.run_id
            result_case = next(
                (item for item in result_value.results if item.case_id == value.case_id), None
            )
            if result_case is None or result_case.input_hash != value.input_hash:
                _failure("regression_evidence_mismatch", stored)
        if value.source_attempt_id is not None:
            attempt_stored, attempt_value = captured.unique_by_id(
                stored, "attempts", value.source_attempt_id
            )
            if not isinstance(attempt_value, AttemptRecord) or (
                attempt_value.case_id != value.case_id
            ):
                _failure("project_reference_wrong_owner", attempt_stored)
            if linked_run_id is not None and attempt_value.run_id != linked_run_id:
                _failure("regression_evidence_mismatch", stored)
            linked_run_id = attempt_value.run_id
            if result_value is not None:
                result_case = next(
                    (item for item in result_value.results if item.case_id == value.case_id), None
                )
                if result_case is None or result_case.attempt_id != value.source_attempt_id:
                    _failure("regression_evidence_mismatch", stored)
        if linked_run_id is not None:
            run_stored, run_value = captured.get(stored, "runs", linked_run_id)
            if not isinstance(run_value, RunManifest):
                _failure("project_reference_wrong_owner", run_stored)
            if (
                run_value.dataset_id != value.dataset_id
                or run_value.decision_revision_id != value.decision_revision_id
                or (value.decision_id is not None and run_value.decision_id != value.decision_id)
            ):
                _failure("regression_evidence_mismatch", stored)
            dataset_stored, source_dataset = captured.get(
                run_stored, "dataset_snapshots", run_value.dataset_snapshot_id
            )
            if not isinstance(source_dataset, DatasetSnapshot) or (
                source_dataset.dataset_id != value.dataset_id
            ):
                _failure("project_reference_wrong_owner", dataset_stored)
            original_case = next(
                (case for case in source_dataset.cases if case.id == value.case_id), None
            )
            if original_case is None:
                _failure("regression_evidence_mismatch", stored)
            try:
                original_input_hash = case_input_hash(original_case)
            except JsonError:
                _failure("regression_evidence_mismatch", stored)
            if (
                original_case.input_source != value.input_source
                or original_input_hash != value.input_hash
                or (value.source_case is not None and original_case != value.source_case)
            ):
                _failure("regression_evidence_mismatch", stored)
        if value.source_case is not None:
            source_case = value.source_case
            try:
                source_input_hash = case_input_hash(source_case)
            except JsonError:
                _failure("regression_evidence_mismatch", stored)
            if (
                source_case.id != value.case_id
                or source_case.dataset_id != value.dataset_id
                or source_case.input_source != value.input_source
                or source_input_hash != value.input_hash
            ):
                _failure("regression_evidence_mismatch", stored)
        if executable_regression(value):
            admit_regression_origin(captured.records, value)
        else:
            warnings.append(
                (
                    stored,
                    ServiceError(
                        code="incompatible_data",
                        reason="legacy_regression_not_executable",
                        resource_id=value.id,
                    ),
                )
            )
    for stored, value in captured.all("regression_removals"):
        if not isinstance(value, RegressionRemoval):
            continue
        regression_stored, regression_value = captured.get(
            stored, "regressions", value.regression_id
        )
        captured.get(stored, "decisions", value.decision_id)
        if isinstance(regression_value, RegressionRecord):
            revision = (
                captured.get(
                    regression_stored,
                    "revisions",
                    regression_value.decision_revision_id,
                    (regression_value.decision_id,),
                )[1]
                if regression_value.decision_id is not None
                else captured.unique_by_id(
                    regression_stored,
                    "revisions",
                    regression_value.decision_revision_id,
                )[1]
            )
            if not isinstance(revision, DecisionRevision) or (
                (regression_value.decision_id or revision.decision_id) != value.decision_id
            ):
                _failure("project_reference_wrong_owner", regression_stored)
    for stored, value in captured.all("reports"):
        if not isinstance(value, ReportRecord):
            continue
        for evaluation_id in value.evaluation_ids:
            captured.get(stored, "evaluations", evaluation_id)
        for result_id in value.result_snapshot_ids:
            captured.get(stored, "result_snapshots", result_id)
        for label_id_value in value.label_snapshot_ids:
            captured.get(stored, "label_snapshots", label_id_value)
        if value.comparison_id is not None:
            captured.get(stored, "comparisons", value.comparison_id)
        if value.diagnostic_snapshot_id is not None:
            captured.get(stored, "diagnostic_snapshots", value.diagnostic_snapshot_id)
        if value.check_snapshot_id is not None:
            captured.get(stored, "check_snapshots", value.check_snapshot_id)
        try:
            metadata = admit_report_metadata(stored)
        except ReportAdmissionError as error:
            _failure(error.reason, stored)
        if metadata.legacy:
            warnings.append(
                (
                    stored,
                    ServiceError(
                        code="incompatible_data",
                        reason="unsupported_report_profile",
                        resource_id=value.id,
                    ),
                )
            )
        else:
            admit_report_from_records(stored, captured.records)
