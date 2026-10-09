"""Validate immutable group membership and shared lifetime reservations from one epoch."""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from pydantic import ValidationError

from deykit.application.dataset_support import decoded, fail, validated_model
from deykit.contracts.execution_groups import (
    CheckSnapshot,
    DiagnosticSnapshot,
    ExecutionGroup,
    ExecutionGroupSegment,
)
from deykit.contracts.json_value import (
    JsonDocument,
    JsonValue,
    bytes_hash,
    canonical_bytes,
    semantic_hash,
)
from deykit.contracts.ports import Collection, ResourceKey, StoredRecord
from deykit.contracts.records import (
    DatasetSnapshot,
    DecisionRevision,
    HashedRecord,
    RunManifest,
)
from deykit.domain.definitions import definition_hash
from deykit.runner.group_selection import decode_group_start_selection, group_start_intent

PREPARED_EVIDENCE_PROFILE = "deykit-group-member-prepared-v1"


def member_prepared_hash(
    run_id: str, case_ids: tuple[str, ...], records: tuple[StoredRecord, ...]
) -> str:
    """Hash ordered exact prepared record bodies and their scoped source keys."""
    scoped = tuple(
        record
        for record in records
        if record.key.collection == "prepared_cases" and record.key.scope == (run_id,)
    )
    by_id = {record.key.resource_id: record for record in scoped}
    if (
        len(by_id) != len(scoped)
        or len(case_ids) != len(set(case_ids))
        or set(by_id) != set(case_ids)
    ):
        raise ValueError("prepared_member_scope_mismatch")
    prepared: list[JsonValue] = [
        {
            "key": {
                "collection": "prepared_cases",
                "scope": [run_id],
                "resource_id": case_id,
            },
            "body_sha256": bytes_hash(by_id[case_id].body),
        }
        for case_id in case_ids
    ]
    payload: JsonValue = {
        "profile": PREPARED_EVIDENCE_PROFILE,
        "run_id": run_id,
        "prepared": prepared,
    }
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def content_hash(record: HashedRecord) -> str:
    """Envelope hash for P12-owned evidence; source strings remain exact strings."""
    record = validated_model(type(record), record, "invalid_group_evidence")
    return semantic_hash(cast(JsonValue, record.model_dump(mode="json", exclude={"content_hash"})))


@dataclass(frozen=True)
class GroupBudget:
    group: ExecutionGroup
    used: int
    segments: tuple[ExecutionGroupSegment, ...] = ()

    @property
    def remaining(self) -> int:
        return max(0, self.group.max_attempts - self.used)


def _selection_allocation(group: ExecutionGroup) -> int:
    decoded_selection = decode_group_start_selection(
        group.selection_source, expected_kind=group.kind
    )
    selection = decoded_selection.original_selection
    if group_start_intent(decoded_selection) != group.intent_hash:
        fail("group_selection_intent_mismatch", "incompatible_data")
    request = selection.get("request")
    if not isinstance(request, dict):
        fail("invalid_group_selection", "incompatible_data")
    settings: object
    if group.kind == "choice_order":
        run = request.get("run")
        if not isinstance(run, dict):
            fail("invalid_group_selection", "incompatible_data")
        settings = run.get("settings")
    else:
        settings = request.get("settings")
    if not isinstance(settings, dict):
        fail("invalid_group_selection", "incompatible_data")
    allocation = settings.get("max_attempts")
    if isinstance(allocation, Decimal):
        exponent = allocation.as_tuple().exponent
        if not isinstance(exponent, int) or exponent < 0 or allocation != int(allocation):
            fail("invalid_group_attempt_allocation", "incompatible_data")
        allocation = int(allocation)
    if type(allocation) is not int or allocation <= 0:
        fail("invalid_group_attempt_allocation", "incompatible_data")
    return allocation


def _admit_profile_revision(
    records: tuple[StoredRecord, ...],
    *,
    decision_id: str,
    mode: str,
    provider_id: str | None,
    revision_id: str | None,
    members: tuple[tuple[RunManifest, DecisionRevision], ...],
) -> None:
    expected_adapter = "fixture" if mode == "fixture" else "jev"
    for manifest, _frozen_revision in members:
        profile = manifest.provider
        if profile is None or profile.adapter != expected_adapter:
            fail("group_provider_selection_mismatch", "incompatible_data")
        if provider_id is not None and (
            provider_id != manifest.provider_profile_id or provider_id != profile.id
        ):
            fail("group_provider_selection_mismatch", "incompatible_data")
    if revision_id is None:
        return
    index = {record.key: record for record in records}
    stored = index.get(ResourceKey("revisions", revision_id, (decision_id,)))
    if stored is None:
        fail("group_revision_selection_mismatch", "incompatible_data")
    revision = decoded(DecisionRevision, stored)
    if (
        revision.id != revision_id
        or revision.decision_id != decision_id
        or definition_hash(revision.definition) != revision.content_hash
        or any(
            revision.definition != frozen_revision.definition
            or revision.content_hash != frozen_revision.content_hash
            for _, frozen_revision in members
        )
    ):
        fail("group_revision_selection_mismatch", "incompatible_data")


def _admit_diagnostic_scope(
    split: str, case_ids: tuple[str, ...], datasets: tuple[DatasetSnapshot, ...]
) -> None:
    expected: JsonValue = {"split": split, "case_ids": list(case_ids)}
    for dataset in datasets:
        try:
            selected = JsonDocument(dataset.selection_source).value
        except ValueError:
            fail("diagnostic_scope_selection_mismatch", "incompatible_data")
        if selected != expected:
            fail("diagnostic_scope_selection_mismatch", "incompatible_data")
        selected_ids = set(case_ids)
        if any(
            (selected_ids and case.id not in selected_ids)
            or (split != "all" and case.split != split)
            for case in dataset.cases
        ):
            fail("diagnostic_scope_selection_mismatch", "incompatible_data")


def group_budget(records: tuple[StoredRecord, ...], group_id: str) -> GroupBudget:
    # Local import avoids coupling plain run records to group orchestration.
    from deykit.runner.history import history_from_records
    from deykit.runner.repository import deadline_at

    index = {record.key: record for record in records}
    if len(index) != len(records):
        fail("duplicate_captured_key", "incompatible_data")
    stored = index.get(ResourceKey("execution_groups", group_id))
    if stored is None:
        fail("execution_group_missing", "incompatible_data")
    group = decoded(ExecutionGroup, stored)
    if group.id != group_id or group.content_hash != content_hash(group):
        fail("execution_group_hash_mismatch", "incompatible_data")
    allocation = _selection_allocation(group)
    if group.max_attempts != allocation:
        fail("execution_group_cap_selection_mismatch", "incompatible_data")
    used = 0
    histories = {}
    for member in group.members:
        stored = index.get(ResourceKey("runs", member.run_id))
        if stored is None or bytes_hash(stored.body) != member.manifest_hash:
            fail("execution_group_member_mismatch", "incompatible_data")
        manifest = decoded(RunManifest, stored)
        if manifest.settings.max_attempts != allocation:
            fail("execution_group_member_cap_mismatch", "incompatible_data")
        try:
            actual_prepared_hash = member_prepared_hash(member.run_id, manifest.case_ids, records)
        except ValueError:
            fail("execution_group_prepared_scope_mismatch", "incompatible_data")
        if actual_prepared_hash != member.prepared_hash:
            fail("execution_group_prepared_hash_mismatch", "incompatible_data")
        history = history_from_records(records, member.run_id, verify_group=False)
        if (
            history.manifest.id != member.run_id
            or history.manifest.operation_id != group.operation_id
            or history.manifest.execution_group_id != group.id
            or history.manifest.settings.deadline_seconds != group.deadline_seconds
            or member.initial_requests != sum(item.request is not None for item in history.prepared)
            or (group.kind == "regression_check") != bool(history.manifest.regression_ids)
        ):
            fail("execution_group_context_mismatch", "incompatible_data")
        if any(control.action != "cancel" for control in history.controls):
            fail("execution_group_cap_fixed", "incompatible_data")
        histories[member.run_id] = history
        used += history.used
    if used > group.max_attempts:
        fail("execution_group_cap_exceeded", "incompatible_data")
    # Orphan manifests must not claim membership or borrow this group's budget.
    members = {member.run_id for member in group.members}
    for record in records:
        if record.key.collection == "runs":
            manifest = decoded(RunManifest, record)
            if manifest.execution_group_id == group.id and manifest.id not in members:
                fail("execution_group_foreign_member", "incompatible_data")
    segments = tuple(
        sorted(
            (
                decoded(ExecutionGroupSegment, r)
                for r in records
                if r.key.collection == "group_segments" and r.key.scope == (group_id,)
            ),
            key=lambda s: s.sequence,
        )
    )
    if tuple(s.sequence for s in segments) != tuple(range(1, len(segments) + 1)):
        fail("invalid_group_segment_sequence", "incompatible_data")
    linked: set[str] = set()
    if len({s.operation_id for s in segments}) != len(segments):
        fail("duplicate_group_segment_operation", "incompatible_data")
    for segment in segments:
        if (
            segment.group_id != group_id
            or ResourceKey("group_segments", segment.id, (group_id,)) not in index
            or segment.deadline_at != deadline_at(segment.started_at, group.deadline_seconds)
            or (
                segment.sequence == 1
                and (segment.operation_id != group.operation_id or segment.retry_unknown)
            )
        ):
            fail("group_segment_identity_mismatch", "incompatible_data")
        if tuple(m.run_id for m in segment.member_segments) != tuple(
            m.run_id for m in group.members
        ):
            fail("group_segment_membership_mismatch", "incompatible_data")
        for linked_member in segment.member_segments:
            child = next(
                (
                    s
                    for s in histories[linked_member.run_id].segments
                    if s.id == linked_member.segment_id
                ),
                None,
            )
            if (
                child is None
                or child.run_id != linked_member.run_id
                or child.id in linked
                or child.sequence != segment.sequence
                or child.started_at != segment.started_at
                or child.deadline_at != segment.deadline_at
                or child.retry_unknown != segment.retry_unknown
            ):
                fail("group_segment_context_mismatch", "incompatible_data")
            linked.add(child.id)
    if linked != {s.id for history in histories.values() for s in history.segments}:
        fail("unowned_group_child_segment", "incompatible_data")
    return GroupBudget(group, used, segments)


GroupSnapshot = DiagnosticSnapshot | CheckSnapshot


def admit_group_snapshots(
    records: tuple[StoredRecord, ...], group_id: str
) -> tuple[GroupSnapshot, ...]:
    """Admit every retained boundary before any recovery mutation; no source access."""
    from deykit.application.evaluations import frozen_evaluation_from_records
    from deykit.runner.history import history_from_records

    budget = group_budget(records, group_id)
    collection: Collection = (
        "diagnostic_snapshots" if budget.group.kind == "choice_order" else "check_snapshots"
    )
    kind = DiagnosticSnapshot if budget.group.kind == "choice_order" else CheckSnapshot
    segments = {s.id: s for s in budget.segments}
    if not segments:
        fail("group_segment_missing", "incompatible_data")
    # Missing group summaries do not relax admission of frozen child context.
    contexts = []
    for execution_member in budget.group.members:
        history = history_from_records(records, execution_member.run_id, verify_group=False)
        if not history.snapshots:
            fail("group_member_result_missing", "incompatible_data")
        for result in history.snapshots:
            frozen = frozen_evaluation_from_records(
                records, execution_member.run_id, result.id, None, "original"
            )
        if (
            frozen.revision.id != frozen.manifest.decision_revision_id
            or frozen.dataset.id != frozen.manifest.dataset_snapshot_id
            or frozen.labels.id != frozen.manifest.label_snapshot_id
            or frozen.baseline_dataset.id != frozen.manifest.baseline_dataset_snapshot_id
            or frozen.baseline_labels.id != frozen.manifest.baseline_label_snapshot_id
            or any(c.dataset_id != frozen.manifest.dataset_id for c in frozen.dataset.cases)
        ):
            fail("group_frozen_identity_mismatch", "incompatible_data")
        for values, collection_name, scope in (
            (history.prepared, "prepared_cases", (execution_member.run_id,)),
            (history.segments, "segments", (execution_member.run_id,)),
            (history.events, "run_events", (execution_member.run_id,)),
            (history.attempts, "attempts", (execution_member.run_id,)),
            (history.controls, "run_controls", (execution_member.run_id,)),
        ):
            actual_keys = {
                r.key.resource_id
                for r in records
                if r.key.collection == collection_name and r.key.scope == scope
            }
            ids = tuple(v.id for v in values)
            if set(ids) != actual_keys or len(ids) != len(set(ids)):
                fail("group_child_path_mismatch", "incompatible_data")
        if any(s.cancel_through_sequence > len(history.controls) for s in history.segments):
            fail("group_cancel_cutoff_mismatch", "incompatible_data")
        contexts.append(frozen)
    first = contexts[0]
    if budget.group.kind == "choice_order" and any(
        f.revision.definition != first.revision.definition
        or f.dataset.cases != first.dataset.cases
        or f.labels.labels != first.labels.labels
        or f.baseline_dataset.cases != first.baseline_dataset.cases
        or f.baseline_labels.labels != first.baseline_labels.labels
        or f.manifest.provider != first.manifest.provider
        or f.manifest.settings != first.manifest.settings
        for f in contexts
    ):
        fail("diagnostic_source_mismatch", "incompatible_data")
    _selection_allocation(budget.group)
    selection = decode_group_start_selection(
        budget.group.selection_source, expected_kind=budget.group.kind
    ).original_selection
    assert isinstance(selection, dict) and isinstance(selection.get("request"), dict)
    if budget.group.kind == "choice_order":
        from deykit.application.diagnostics import ChoiceOrderRequest
        from deykit.diagnostics.orders import choice_orders

        try:
            requested = ChoiceOrderRequest.model_validate_json(
                json.dumps(_selection_integers(selection["request"]))
            )
        except ValidationError:
            fail("invalid_group_selection", "incompatible_data")
        if requested.run.option_order is not None or requested.run.regression_ids:
            fail("diagnostic_selection_override", "incompatible_data")
        _admit_profile_revision(
            records,
            decision_id=requested.run.decision_id,
            mode=requested.run.mode,
            provider_id=requested.run.provider_id,
            revision_id=requested.run.revision_id,
            members=tuple((f.manifest, f.revision) for f in contexts),
        )
        _admit_diagnostic_scope(
            requested.run.split,
            requested.run.case_ids,
            tuple(f.dataset for f in contexts),
        )
        expected_orders = choice_orders(
            tuple(o.id for o in first.revision.definition.questions[0].options),
            orders=requested.orders,
            seed=requested.seed,
        )
        if tuple(f.manifest.option_order for f in contexts) != expected_orders or any(
            f.manifest.decision_id != requested.run.decision_id
            or f.manifest.dataset_id != requested.run.dataset_id
            or f.manifest.mode != requested.run.mode
            or f.manifest.fixture_set_id != requested.run.fixture_set_id
            or f.manifest.settings != requested.run.settings
            for f in contexts
        ):
            fail("diagnostic_selection_mismatch", "incompatible_data")
    else:
        from deykit.application.checks import CheckRequest
        from deykit.contracts.records import RegressionRecord
        from deykit.regressions.evidence import admit_regression_origin

        try:
            requested_check = CheckRequest.model_validate_json(
                json.dumps(_selection_integers(selection["request"]))
            )
        except ValidationError:
            fail("invalid_group_selection", "incompatible_data")
        _admit_profile_revision(
            records,
            decision_id=requested_check.decision_id,
            mode=requested_check.mode,
            provider_id=requested_check.provider_id,
            revision_id=requested_check.revision_id,
            members=tuple((f.manifest, f.revision) for f in contexts),
        )
        ids = tuple(key for f in contexts for key in f.manifest.regression_ids)
        if len(ids) != len(set(ids)) or (
            requested_check.regression_ids and set(ids) != set(requested_check.regression_ids)
        ):
            fail("check_selection_mismatch", "incompatible_data")
        index = {r.key: r for r in records}
        for f in contexts:
            if (
                f.manifest.decision_id != requested_check.decision_id
                or f.manifest.mode != requested_check.mode
                or f.manifest.settings != requested_check.settings
                or f.manifest.fixture_set_id != requested_check.fixture_set_id
            ):
                fail("check_selection_mismatch", "incompatible_data")
            for key in f.manifest.regression_ids:
                stored_regression = index.get(ResourceKey("regressions", key))
                if stored_regression is None:
                    fail("check_regression_missing", "incompatible_data")
                regression = decoded(RegressionRecord, stored_regression)
                case = admit_regression_origin(records, regression)
                if (
                    case not in f.dataset.cases
                    or regression.decision_id != f.manifest.decision_id
                    or regression.dataset_id != f.manifest.dataset_id
                    or regression.question_id != f.revision.definition.questions[0].id
                ):
                    fail("check_regression_mismatch", "incompatible_data")
    selected: list[GroupSnapshot] = []
    for stored in records:
        if stored.key.collection not in {"diagnostic_snapshots", "check_snapshots"}:
            continue
        record: GroupSnapshot
        if stored.key.collection == "diagnostic_snapshots":
            record = decoded(DiagnosticSnapshot, stored)
        else:
            record = decoded(CheckSnapshot, stored)
        if ResourceKey("execution_groups", record.group_id) not in {r.key for r in records}:
            fail("group_snapshot_group_missing", "incompatible_data")
        if record.group_id != group_id:
            continue
        if (
            stored.key != ResourceKey(collection, record.id)
            or type(record) is not kind
            or record.content_hash != content_hash(record)
            or record.segment_id not in segments
            or tuple(r.run_id for r in record.results)
            != tuple(m.run_id for m in budget.group.members)
        ):
            fail("group_snapshot_context_mismatch", "incompatible_data")
        segment = segments[record.segment_id]
        if record.sequence != segment.sequence:
            fail("group_snapshot_segment_sequence_mismatch", "incompatible_data")
        for member in record.results:
            frozen = frozen_evaluation_from_records(
                records, member.run_id, member.result_snapshot_id, None, "original"
            )
            history = history_from_records(records, member.run_id, verify_group=False)
            if frozen.results.id != member.result_snapshot_id:
                fail("group_result_path_mismatch", "incompatible_data")
            boundary = frozen.results.through_event_sequence
            child_id = next(
                m.segment_id for m in segment.member_segments if m.run_id == member.run_id
            )
            visible = tuple(e for e in history.events if e.sequence <= boundary)
            last_segment = next(
                (e.segment_id for e in reversed(visible) if e.segment_id is not None), None
            )
            # A member not yet started may retain its initial boundary. Earlier terminal
            # evidence is valid only if it predates the selected group's next segment.
            child = next(s for s in history.segments if s.id == child_id)
            first_marker = next(e.sequence for e in history.events if e.segment_id == child_id)
            if last_segment != child_id and boundary >= first_marker:
                fail("group_snapshot_result_segment_mismatch", "incompatible_data")
            if any(s.sequence > child.sequence and s.id == last_segment for s in history.segments):
                fail("group_snapshot_future_result", "incompatible_data")
        selected.append(record)
    selected.sort(key=lambda s: s.sequence)
    if tuple(s.sequence for s in selected) != tuple(range(1, len(selected) + 1)):
        fail("invalid_group_snapshot_sequence", "incompatible_data")
    return tuple(selected)


def _selection_integers(value: JsonValue) -> JsonValue:
    """Command envelope numeric fields are integer counts; user sources stay strings."""
    if isinstance(value, Decimal):
        if value != int(value):
            fail("invalid_group_selection", "incompatible_data")
        return int(value)
    if isinstance(value, list):
        return [_selection_integers(item) for item in value]
    if isinstance(value, dict):
        return {key: _selection_integers(item) for key, item in value.items()}
    return value
