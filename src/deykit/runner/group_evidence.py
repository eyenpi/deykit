"""Validate immutable group membership and shared lifetime reservations from one epoch."""

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from pydantic import ValidationError

from deykit.application.dataset_support import decoded, fail, safe_hash, validated_model
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
    semantic_hash,
)
from deykit.contracts.ports import Collection, ResourceKey, StoredRecord
from deykit.contracts.records import HashedRecord


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
    used = 0
    histories = {}
    for member in group.members:
        stored = index.get(ResourceKey("runs", member.run_id))
        if stored is None or bytes_hash(stored.body) != member.manifest_hash:
            fail("execution_group_member_mismatch", "incompatible_data")
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
    from deykit.contracts.records import RunManifest

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
    from deykit.application.evaluations import _frozen
    from deykit.runner.history import history_from_records

    budget = group_budget(records, group_id)
    collection: Collection = (
        "diagnostic_snapshots" if budget.group.kind == "choice_order" else "check_snapshots"
    )
    kind = DiagnosticSnapshot if budget.group.kind == "choice_order" else CheckSnapshot
    segments = {s.id: s for s in budget.segments}
    # Missing group summaries do not relax admission of frozen child context.
    contexts = []
    for execution_member in budget.group.members:
        history = history_from_records(records, execution_member.run_id, verify_group=False)
        if not history.snapshots:
            fail("group_member_result_missing", "incompatible_data")
        for result in history.snapshots:
            frozen = _frozen(records, execution_member.run_id, result.id, None, "original")
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
    selection = JsonDocument(budget.group.selection_source).value
    if (
        not isinstance(selection, dict)
        or selection.get("kind") != budget.group.kind
        or not isinstance(selection.get("request"), dict)
        or safe_hash({"command": "execution_group.start", "selection": selection})
        != budget.group.intent_hash
    ):
        fail("group_selection_intent_mismatch", "incompatible_data")
    if budget.group.kind == "choice_order":
        from deykit.application.diagnostics import ChoiceOrderRequest
        from deykit.diagnostics.orders import choice_orders

        try:
            requested = ChoiceOrderRequest.model_validate_json(
                json.dumps(_selection_integers(selection["request"]))
            )
        except ValidationError:
            fail("invalid_group_selection", "incompatible_data")
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
            frozen = _frozen(records, member.run_id, member.result_snapshot_id, None, "original")
            history = history_from_records(records, member.run_id, verify_group=False)
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
