"""Immutable evaluations over frozen run, result, input and label evidence."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, TypeVar, cast

from deykit.application.dataset_support import fail, identifier, page
from deykit.application.evaluation_evidence import snapshot_attempts
from deykit.contracts.base import Record
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.evidence import evidence_hash
from deykit.contracts.execution_groups import ExecutionGroup
from deykit.contracts.identities import new_id
from deykit.contracts.json_value import JsonError, JsonValue, dump_json, parse_json, semantic_hash
from deykit.contracts.ports import (
    Clock,
    Collection,
    ResourceKey,
    SnapshotSource,
    SourceChange,
    StoredRecord,
)
from deykit.contracts.records import (
    AttemptEvent,
    AttemptRecord,
    DatasetSnapshot,
    DecisionRevision,
    EvaluationRecord,
    LabelRecord,
    LabelSnapshot,
    ResultSnapshot,
    RunManifest,
)
from deykit.domain.definitions import definition_hash
from deykit.domain.label_identity import label_id
from deykit.metrics import assess_results, live_latency, majority_baseline, reported_usage
from deykit.metrics.baseline import unavailable_regression_baseline
from deykit.metrics.summary import MetricsInvalid

if TYPE_CHECKING:
    from deykit.runner.decoding import HistoryDecoder
    from deykit.runner.history import RunHistory

R = TypeVar("R", bound=Record)
EvaluationMode = Literal["original", "saved_answer_reevaluation"]


@dataclass(frozen=True)
class FrozenEvaluation:
    manifest: RunManifest
    revision: DecisionRevision
    dataset: DatasetSnapshot
    labels: LabelSnapshot
    results: ResultSnapshot
    baseline_dataset: DatasetSnapshot
    baseline_labels: LabelSnapshot
    dispatched_attempts: tuple[tuple[AttemptRecord, AttemptEvent], ...]
    group_kind: str | None = None


@dataclass(frozen=True)
class EvaluationView:
    record: EvaluationRecord
    etag: str
    metrics: dict[str, JsonValue]
    replayed: bool = False


@dataclass(frozen=True)
class EvaluationPage:
    items: tuple[EvaluationView, ...]
    total: int
    next_cursor: str | None


def evaluation_hash(record: EvaluationRecord) -> str:
    return _evaluation_hash(
        record.run_id,
        record.result_snapshot_id,
        record.label_snapshot_id,
        record.mode,
        record.metrics_source,
        record.execution_operation_id,
    )


def _evaluation_hash(
    run_id: str,
    result_snapshot_id: str,
    label_snapshot_id: str,
    mode: str,
    metrics_source: str,
    execution_operation_id: str | None = None,
) -> str:
    return semantic_hash(
        {
            "run_id": run_id,
            "result_snapshot_id": result_snapshot_id,
            "label_snapshot_id": label_snapshot_id,
            "mode": mode,
            "metrics": parse_json(metrics_source),
            **(
                {"execution_operation_id": execution_operation_id} if execution_operation_id else {}
            ),
        }
    )


def _typed(record: StoredRecord, kind: type[R]) -> R:
    try:
        return load_record(kind, record.body)
    except JsonError:
        fail("invalid_frozen_record", "incompatible_data")


def _required(
    index: dict[ResourceKey, StoredRecord],
    kind: type[R],
    collection: Collection,
    resource_id: str,
    scope: tuple[str, ...] = (),
) -> R:
    stored = index.get(ResourceKey(collection, resource_id, scope))
    if stored is None:
        fail("frozen_resource_missing", "not_found")
    return _typed(stored, kind)


def _verify_hashes(frozen: FrozenEvaluation) -> None:
    if frozen.revision.content_hash != definition_hash(frozen.revision.definition):
        fail("revision_hash_mismatch", "incompatible_data")
    for snapshot, records in (
        (frozen.dataset, frozen.dataset.cases),
        (frozen.baseline_dataset, frozen.baseline_dataset.cases),
        (frozen.labels, frozen.labels.labels),
        (frozen.baseline_labels, frozen.baseline_labels.labels),
    ):
        if snapshot.content_hash != evidence_hash(tuple(dump_record(item) for item in records)):
            fail("frozen_snapshot_hash_mismatch", "incompatible_data")
    if frozen.results.content_hash != evidence_hash(
        tuple(item.model_dump_json().encode("utf-8") for item in frozen.results.results)
    ):
        fail("result_snapshot_hash_mismatch", "incompatible_data")


def frozen_evaluation_from_records(
    records: tuple[StoredRecord, ...],
    run_id: str,
    result_snapshot_id: str,
    label_snapshot_id: str | None,
    mode: EvaluationMode,
    *,
    decoder: HistoryDecoder | None = None,
    history: RunHistory | None = None,
) -> FrozenEvaluation:
    """Admit original immutable context from one already captured source batch."""
    index = {record.key: record for record in records}
    manifest = _required(index, RunManifest, "runs", run_id)
    if history is not None and history.manifest != manifest:
        fail("run_evidence_identity_mismatch", "incompatible_data")
    if (
        manifest.id != run_id
        or manifest.decision_id is None
        or manifest.dataset_id is None
        or manifest.baseline_dataset_snapshot_id is None
        or manifest.baseline_label_snapshot_id is None
    ):
        fail("incomplete_run_manifest", "incompatible_data")
    if mode == "original":
        if label_snapshot_id is not None and label_snapshot_id != manifest.label_snapshot_id:
            fail("original_label_snapshot_mismatch", "incompatible_data")
        label_snapshot_id = manifest.label_snapshot_id
    elif label_snapshot_id is None:
        fail("reevaluation_label_snapshot_required")
    revision = _required(
        index,
        DecisionRevision,
        "revisions",
        manifest.decision_revision_id,
        (manifest.decision_id,),
    )
    dataset = _required(index, DatasetSnapshot, "dataset_snapshots", manifest.dataset_snapshot_id)
    labels = _required(index, LabelSnapshot, "label_snapshots", label_snapshot_id)
    results = _required(index, ResultSnapshot, "result_snapshots", result_snapshot_id)
    baseline_dataset = _required(
        index, DatasetSnapshot, "dataset_snapshots", manifest.baseline_dataset_snapshot_id
    )
    baseline_labels = _required(
        index, LabelSnapshot, "label_snapshots", manifest.baseline_label_snapshot_id
    )
    from deykit.application.images import check_case_assets

    check_case_assets((*dataset.cases, *baseline_dataset.cases), records)
    if (
        revision.decision_id != manifest.decision_id
        or dataset.dataset_id != manifest.dataset_id
        or baseline_dataset.dataset_id != manifest.dataset_id
        or labels.decision_id != manifest.decision_id
        or baseline_labels.decision_id != manifest.decision_id
        or labels.dataset_snapshot_id != dataset.id
        or baseline_labels.dataset_snapshot_id != baseline_dataset.id
        or results.run_id != run_id
        or tuple(case.id for case in dataset.cases) != manifest.case_ids
        or tuple(result.case_id for result in results.results) != manifest.case_ids
    ):
        fail("frozen_context_mismatch", "incompatible_data")
    if manifest.baseline_unavailable_reason and (baseline_dataset.cases or baseline_labels.labels):
        fail("regression_baseline_must_be_empty", "incompatible_data")
    frozen = FrozenEvaluation(
        manifest,
        revision,
        dataset,
        labels,
        results,
        baseline_dataset,
        baseline_labels,
        snapshot_attempts(records, results, decoder=decoder, history=history),
        _required(index, ExecutionGroup, "execution_groups", manifest.execution_group_id).kind
        if manifest.execution_group_id
        else None,
    )
    _verify_hashes(frozen)
    return frozen


def metrics_from_frozen(
    frozen: FrozenEvaluation, evaluation_mode: EvaluationMode
) -> dict[str, JsonValue]:
    try:
        summary = assess_results(
            frozen.revision.definition,
            frozen.dataset,
            frozen.labels,
            frozen.results,
            frozen.manifest.case_ids,
        )
        paired = tuple(item.case_id for item in summary.cases if item.set_correct is not None)
        if frozen.manifest.baseline_unavailable_reason:
            baseline = unavailable_regression_baseline(
                frozen.baseline_dataset,
                frozen.baseline_labels,
                frozen.dataset,
                frozen.labels,
                len(frozen.manifest.case_ids),
                len(paired),
            )
        else:
            baseline = majority_baseline(
                frozen.revision.definition,
                frozen.baseline_dataset,
                frozen.baseline_labels,
                frozen.dataset,
                frozen.labels,
                frozen.manifest.case_ids,
                paired,
            )
        dispatched = (
            tuple(
                (attempt, event)
                for attempt, event in frozen.dispatched_attempts
                if event.state != "not_sent"
            )
            if frozen.group_kind == "experiment"
            else frozen.dispatched_attempts
        )
        latency = live_latency(
            frozen.manifest.mode,
            tuple(
                event.duration_seconds
                for _, event in dispatched
                if event.duration_seconds is not None
            ),
        )
        usage_sources = tuple(
            event.outcome.usage_source if event.outcome else None for _, event in dispatched
        )
        reported_at = max(
            (
                event.created_at
                for _, event in dispatched
                if event.outcome and event.outcome.usage_source is not None
            ),
            default=None,
        )
        usage = reported_usage(frozen.manifest.mode, usage_sources, reported_at=reported_at)
    except (MetricsInvalid, JsonError) as error:
        reason = error.code if isinstance(error, JsonError) else str(error)
        fail(reason, "incompatible_data")
    return {
        "profile": "deykit-evaluation-v1",
        "run_id": frozen.manifest.id,
        "decision_id": frozen.manifest.decision_id,
        "dataset_id": frozen.manifest.dataset_id,
        "decision_revision_id": frozen.revision.id,
        "dataset_snapshot_id": frozen.dataset.id,
        "result_snapshot_id": frozen.results.id,
        "label_snapshot_id": frozen.labels.id,
        "evaluation_mode": evaluation_mode,
        "evidence_mode": frozen.manifest.mode,
        "summary": summary.source(),
        "baseline": baseline.source(),
        "latency": latency.source(),
        "usage": usage.source(),
    }


def admit_evaluation_record(stored: StoredRecord, *, replayed: bool = False) -> EvaluationView:
    """Decode and verify an evaluation without reading source or mutable state."""
    record = _typed(stored, EvaluationRecord)
    if stored.key != ResourceKey("evaluations", record.id):
        fail("evaluation_record_identity_mismatch", "incompatible_data")
    try:
        if record.content_hash != evaluation_hash(record):
            fail("evaluation_hash_mismatch", "incompatible_data")
        parse_json(record.metrics_source)
        # Exact integer counters stay JSON integers in command/API output. Fractional
        # tokens, if a future metric adds them, remain Decimal instead of float.
        metrics = json.loads(record.metrics_source, parse_float=Decimal)
    except JsonError as error:
        fail(error.code, "incompatible_data")
    if not isinstance(metrics, dict):
        fail("invalid_evaluation_metrics", "incompatible_data")
    return EvaluationView(record, stored.etag, metrics, replayed)


# Existing result inspection imports these names; both point to the same pure
# implementations rather than maintaining a second admission path.
_frozen = frozen_evaluation_from_records
_view = admit_evaluation_record


class EvaluationService:
    def __init__(
        self, source: SnapshotSource, clock: Clock, id_factory: Callable[[], str] = new_id
    ) -> None:
        self.source, self.clock, self.id_factory = source, clock, id_factory

    def frozen_context(
        self,
        run_id: str,
        result_snapshot_id: str,
        *,
        label_snapshot_id: str | None = None,
        mode: EvaluationMode = "original",
    ) -> FrozenEvaluation:
        identifier(run_id), identifier(result_snapshot_id)
        if label_snapshot_id is not None:
            identifier(label_snapshot_id)
        if mode not in ("original", "saved_answer_reevaluation"):
            fail("invalid_evaluation_mode")
        with self.source.consistent_read() as source:
            return frozen_evaluation_from_records(
                cast(SnapshotSource, source).capture_snapshot(),
                run_id,
                result_snapshot_id,
                label_snapshot_id,
                mode,
            )

    def evaluate_saved(
        self,
        run_id: str,
        result_snapshot_id: str,
        *,
        label_snapshot_id: str | None = None,
        mode: EvaluationMode = "original",
        operation_id: str,
    ) -> EvaluationView:
        return self._evaluate(
            run_id,
            result_snapshot_id,
            label_snapshot_id=label_snapshot_id,
            mode=mode,
            operation_id=operation_id,
        )

    def evaluate_execution(
        self,
        run_id: str,
        result_snapshot_id: str,
        *,
        execution_operation_id: str,
        allow_create: bool = True,
    ) -> EvaluationView | None:
        """Bind one execution action to its first frozen original-label evaluation.

        Replaying a start/resume after later segments returns this same evaluation,
        even when the runner's current latest result snapshot has advanced.
        """
        identifier(run_id), identifier(result_snapshot_id), identifier(execution_operation_id)
        if type(allow_create) is not bool:
            fail("invalid_evaluation_creation_setting")
        with self.source.consistent_read() as source:
            records = cast(SnapshotSource, source).capture_snapshot()
            matches = tuple(
                admit_evaluation_record(item, replayed=True)
                for item in records
                if item.key.collection == "evaluations"
                and _typed(item, EvaluationRecord).execution_operation_id == execution_operation_id
            )
            if matches:
                if (
                    len(matches) != 1
                    or matches[0].record.run_id != run_id
                    or matches[0].record.mode != "original"
                ):
                    fail("execution_evaluation_conflict", "incompatible_data")
                record = matches[0].record
                frozen_evaluation_from_records(
                    records, run_id, record.result_snapshot_id, record.label_snapshot_id, "original"
                )
                return matches[0]
            if not allow_create:
                return None
            operation_id = "evaluation-" + semantic_hash(
                [execution_operation_id, result_snapshot_id]
            )
            return self._evaluate(
                run_id,
                result_snapshot_id,
                operation_id=operation_id,
                execution_operation_id=execution_operation_id,
            )

    def _evaluate(
        self,
        run_id: str,
        result_snapshot_id: str,
        *,
        label_snapshot_id: str | None = None,
        mode: EvaluationMode = "original",
        operation_id: str,
        execution_operation_id: str | None = None,
    ) -> EvaluationView:
        identifier(run_id), identifier(result_snapshot_id), identifier(operation_id)
        if label_snapshot_id is not None:
            identifier(label_snapshot_id)
        if mode not in ("original", "saved_answer_reevaluation"):
            fail("invalid_evaluation_mode")
        digest = semantic_hash(
            {
                "command": "evaluation.evaluate_saved",
                **(
                    {"execution_operation_id": execution_operation_id}
                    if execution_operation_id
                    else {}
                ),
                "run_id": run_id,
                "result_snapshot_id": result_snapshot_id,
                "label_snapshot_id": label_snapshot_id,
                "mode": mode,
            }
        )
        with self.source.consistent_read() as source:
            replay = source.operation_receipt(operation_id, intent_hash=digest)
            if replay is not None:
                return admit_evaluation_record(replay.changes[0], replayed=True)
            before = cast(SnapshotSource, source).capture_snapshot()
            frozen = frozen_evaluation_from_records(
                before, run_id, result_snapshot_id, label_snapshot_id, mode
            )
            try:
                metrics_source = dump_json(metrics_from_frozen(frozen, mode))
                content_hash = _evaluation_hash(
                    run_id,
                    result_snapshot_id,
                    frozen.labels.id,
                    mode,
                    metrics_source,
                    execution_operation_id,
                )
                record = EvaluationRecord(
                    execution_operation_id=execution_operation_id,
                    id=identifier(self.id_factory()),
                    run_id=run_id,
                    result_snapshot_id=result_snapshot_id,
                    label_snapshot_id=frozen.labels.id,
                    mode=mode,
                    metrics_source=metrics_source,
                    content_hash=content_hash,
                    created_at=self.clock.utc_now(),
                )
                body = dump_record(record)
            except (JsonError, ValueError):
                fail("invalid_evaluation", "validation_error")
            if cast(SnapshotSource, source).capture_snapshot() != before:
                fail("evaluation_source_changed", "conflict")
            receipt = source.commit(
                operation_id,
                (SourceChange(ResourceKey("evaluations", record.id), body, None),),
                intent_hash=digest,
            )
            return admit_evaluation_record(receipt.changes[0], replayed=receipt.replayed)

    def reevaluate_current_labels(
        self, run_id: str, result_snapshot_id: str, *, operation_id: str
    ) -> EvaluationView:
        """Freeze current decision-specific labels and score saved answers with zero dispatch."""
        identifier(run_id), identifier(result_snapshot_id), identifier(operation_id)
        digest = semantic_hash(
            {
                "command": "evaluation.reevaluate_current_labels",
                "run_id": run_id,
                "result_snapshot_id": result_snapshot_id,
            }
        )
        with self.source.consistent_read() as source:
            replay = source.operation_receipt(operation_id, intent_hash=digest)
            if replay is not None:
                saved = next(
                    (item for item in replay.changes if item.key.collection == "evaluations"),
                    None,
                )
                if saved is None:
                    fail("incomplete_evaluation_receipt", "incompatible_data")
                return admit_evaluation_record(saved, replayed=True)
            captured = cast(SnapshotSource, source).capture_snapshot()
            index = {item.key: item for item in captured}
            manifest = _required(index, RunManifest, "runs", run_id)
            if manifest.decision_id is None or manifest.dataset_id is None:
                fail("incomplete_run_manifest", "incompatible_data")
            dataset = _required(
                index, DatasetSnapshot, "dataset_snapshots", manifest.dataset_snapshot_id
            )
            case_ids = {case.id for case in dataset.cases}
            labels: list[LabelRecord] = []
            for stored in captured:
                if stored.key.collection != "labels" or stored.key.scope != (
                    manifest.decision_id,
                    manifest.dataset_id,
                ):
                    continue
                label = _typed(stored, LabelRecord)
                if (
                    label.id != label_id(label.case_id, label.question_id)
                    or label.id != stored.key.resource_id
                    or label.decision_id != manifest.decision_id
                    or label.dataset_id != manifest.dataset_id
                ):
                    fail("label_identity_mismatch", "incompatible_data")
                if label.case_id in case_ids:
                    labels.append(label)
            labels.sort(key=lambda item: item.id)
            try:
                stamp = self.clock.utc_now()
                label_snapshot = LabelSnapshot(
                    id=identifier(self.id_factory()),
                    decision_id=manifest.decision_id,
                    dataset_snapshot_id=dataset.id,
                    labels=tuple(labels),
                    content_hash=evidence_hash(tuple(dump_record(item) for item in labels)),
                    created_at=stamp,
                )
                provisional = StoredRecord(
                    ResourceKey("label_snapshots", label_snapshot.id),
                    dump_record(label_snapshot),
                    "",
                )
                frozen = frozen_evaluation_from_records(
                    (*captured, provisional),
                    run_id,
                    result_snapshot_id,
                    label_snapshot.id,
                    "saved_answer_reevaluation",
                )
                metrics_source = dump_json(metrics_from_frozen(frozen, "saved_answer_reevaluation"))
                evaluation = EvaluationRecord(
                    id=identifier(self.id_factory()),
                    run_id=run_id,
                    result_snapshot_id=result_snapshot_id,
                    label_snapshot_id=label_snapshot.id,
                    mode="saved_answer_reevaluation",
                    metrics_source=metrics_source,
                    content_hash=_evaluation_hash(
                        run_id,
                        result_snapshot_id,
                        label_snapshot.id,
                        "saved_answer_reevaluation",
                        metrics_source,
                    ),
                    created_at=stamp,
                )
                evaluation_body = dump_record(evaluation)
            except (JsonError, ValueError):
                fail("invalid_evaluation", "validation_error")
            if cast(SnapshotSource, source).capture_snapshot() != captured:
                fail("evaluation_source_changed", "conflict")
            receipt = source.commit(
                operation_id,
                (
                    SourceChange(provisional.key, provisional.body, None),
                    SourceChange(ResourceKey("evaluations", evaluation.id), evaluation_body, None),
                ),
                intent_hash=digest,
            )
            saved = next(
                (item for item in receipt.changes if item.key.collection == "evaluations"), None
            )
            if saved is None:
                fail("incomplete_evaluation_receipt", "incompatible_data")
            return admit_evaluation_record(saved, replayed=receipt.replayed)

    def read(self, evaluation_id: str) -> EvaluationView:
        key = ResourceKey("evaluations", identifier(evaluation_id))
        with self.source.consistent_read() as source:
            stored = source.read(key)
            if stored is None:
                fail("evaluation_missing", "not_found")
            return admit_evaluation_record(stored)

    def list(
        self,
        run_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> EvaluationPage:
        identifier(run_id)
        with self.source.consistent_read() as source:
            records = cast(SnapshotSource, source).capture_snapshot()
            views = {
                stored.key.resource_id: view
                for stored in records
                if stored.key.collection == "evaluations"
                if (view := admit_evaluation_record(stored)).record.run_id == run_id
            }
            chosen, next_cursor = page(tuple(views), cursor, limit)
            return EvaluationPage(tuple(views[key] for key in chosen), len(views), next_cursor)
