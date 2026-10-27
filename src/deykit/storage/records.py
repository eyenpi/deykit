"""Source collection validation and scoped layout; immutable history lives outside SQLite."""

from typing import cast

from deykit.contracts.base import Record
from deykit.contracts.codec import load_record, record_limits
from deykit.contracts.execution_groups import (
    CheckSnapshot,
    DiagnosticSnapshot,
    ExecutionGroup,
    ExecutionGroupSegment,
    ExperimentReuse,
    ExperimentSnapshot,
    RegressionRemoval,
)
from deykit.contracts.images import ImageAsset
from deykit.contracts.json_value import JsonError
from deykit.contracts.ports import Collection, ResourceKey
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
from deykit.storage.errors import fail

TYPES: dict[Collection, type[Record]] = {
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
    "regressions": RegressionRecord,
    "execution_groups": ExecutionGroup,
    "group_segments": ExecutionGroupSegment,
    "diagnostic_snapshots": DiagnosticSnapshot,
    "check_snapshots": CheckSnapshot,
    "experiment_snapshots": ExperimentSnapshot,
    "experiment_reuses": ExperimentReuse,
    "regression_removals": RegressionRemoval,
    "reports": ReportRecord,
}
MAX_RECORD_BYTES = max(record_limits(kind).max_bytes for kind in TYPES.values())
SCOPES: dict[Collection, tuple[str, ...]] = {
    "group_segments": ("group_id",),
    "regression_removals": ("decision_id",),
    "cases": ("dataset_id",),
    "labels": ("decision_id", "dataset_id"),
    "label_history": ("decision_id", "dataset_id"),
    "revisions": ("decision_id",),
    "segments": ("run_id",),
    "prepared_cases": ("run_id",),
    "run_controls": ("run_id",),
    "run_events": ("run_id",),
    "attempts": ("run_id",),
    "attempt_events": ("attempt_id",),
}
IMMUTABLE = frozenset(
    {
        "image_assets",
        "revisions",
        "label_history",
        "dataset_snapshots",
        "label_snapshots",
        "runs",
        "prepared_cases",
        "run_controls",
        "segments",
        "run_events",
        "attempts",
        "attempt_events",
        "result_snapshots",
        "annotations",
        "fixtures",
        "evaluations",
        "comparisons",
        "reports",
        "regressions",
        "execution_groups",
        "group_segments",
        "diagnostic_snapshots",
        "check_snapshots",
        "experiment_snapshots",
        "experiment_reuses",
        "regression_removals",
    }
)


def key_path(key: ResourceKey) -> tuple[str, ...]:
    if len(key.scope) != len(SCOPES.get(key.collection, ())):
        fail("invalid_resource_scope")
    if key.collection == "project":
        return ("deykit.project.json",)
    return ("source", key.collection, *key.scope, key.resource_id + ".json")


def path_key(parts: tuple[str, ...]) -> ResourceKey:
    if len(parts) < 3 or parts[0] != "source" or not parts[-1].endswith(".json"):
        fail("invalid_source_path")
    try:
        key = ResourceKey(cast(Collection, parts[1]), parts[-1][:-5], parts[2:-1])
        key_path(key)
        return key
    except ValueError:
        fail("invalid_source_path")


def validate_body(key: ResourceKey, body: bytes) -> Record:
    key_path(key)
    try:
        record = load_record(TYPES[key.collection], body)
    except JsonError as error:
        fail(error.code)
    identity = getattr(record, "decision_id" if key.collection == "drafts" else "id")
    if identity != key.resource_id:
        fail("record_identity_mismatch")
    if tuple(getattr(record, name) for name in SCOPES.get(key.collection, ())) != key.scope:
        fail("record_scope_mismatch")
    return record
