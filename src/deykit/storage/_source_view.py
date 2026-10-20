"""Reuse a logical projection only after a new complete byte capture is validated."""

from dataclasses import dataclass

from deykit.contracts.ports import ResourceKey, StoredRecord
from deykit.storage._history_capture import OperationEvidence
from deykit.storage.errors import fail
from deykit.storage.records import key_path

_MAX_OPERATIONS = 65_536
_MAX_HISTORY_ENTRIES = 262_144


@dataclass(frozen=True)
class CapturedView:
    physical: tuple[StoredRecord, ...]
    evidence: tuple[OperationEvidence, ...]
    records: tuple[StoredRecord, ...]
    packed_cases: frozenset[ResourceKey]
    by_key: dict[ResourceKey, StoredRecord]
    ordered: tuple[tuple[tuple[str, ...], StoredRecord], ...]
    parent_records: tuple[StoredRecord, ...] | None = None
    changed: frozenset[ResourceKey] = frozenset()


class SourceViewMemo:
    def __init__(self) -> None:
        self.view: CapturedView | None = None

    def get(
        self, physical: tuple[StoredRecord, ...], evidence: tuple[OperationEvidence, ...]
    ) -> CapturedView | None:
        old = self.view
        if (
            old is not None
            and old.physical == physical
            and len(old.evidence) == len(evidence)
            and all(a is b for a, b in zip(old.evidence, evidence, strict=True))
        ):
            return old
        return None

    def put(self, view: CapturedView) -> None:
        if (
            len(view.records) > 131_072
            or len(view.evidence) > _MAX_OPERATIONS
            or sum(len(op.entries) for op in view.evidence) > _MAX_HISTORY_ENTRIES
        ):
            self.clear()
            return
        # Logical records, projections and evidence often share the same byte object.
        # Count retained objects once, including superseded mutable versions.
        bodies: dict[int, int] = {}
        for records in (view.records, view.physical, view.parent_records or ()):
            for record in records:
                bodies[id(record.body)] = len(record.body)
        for operation in view.evidence:
            for record in operation.records:
                bodies[id(record.body)] = len(record.body)
            for _, _, case_record in operation.cases:
                if case_record is not None:
                    bodies[id(case_record.body)] = len(case_record.body)
            if operation.reference is not None:
                body = operation.reference[1]
                bodies[id(body)] = len(body)
        self.view = view if sum(bodies.values()) <= 128 * 1024 * 1024 else None

    def clear(self) -> None:
        self.view = None

    def advance(
        self, physical: tuple[StoredRecord, ...], evidence: tuple[OperationEvidence, ...]
    ) -> CapturedView | None:
        old = self.view
        if old is None:
            return None
        prior_ops = {op.sequence: op for op in old.evidence}
        next_ops = {op.sequence: op for op in evidence}
        if len(next_ops) != len(evidence) or any(
            next_ops.get(n) is not op for n, op in prior_ops.items()
        ):
            return None
        added = sorted(
            (op for n, op in next_ops.items() if n not in prior_ops), key=lambda op: op.sequence
        )
        # Inserting old sequence numbers needs chronological reconstruction of case versions.
        if added and added[0].sequence <= max(prior_ops, default=0):
            return None
        current = dict(old.by_key)
        old_physical = {r.key: r for r in old.physical}
        new_physical = {r.key: r for r in physical}
        changed = set(old_physical.keys() - new_physical.keys())
        for key in changed:
            current.pop(key, None)
        for key, record in new_physical.items():
            if key in old.packed_cases or (key in current and key not in old_physical):
                fail("immutable_source_changed", "conflict")
            if old_physical.get(key) != record:
                current[key] = record
                changed.add(key)
        packed = set(old.packed_cases)
        for op in added:
            for record in op.records:
                if record.key in current:
                    fail("immutable_source_changed", "conflict")
                current[record.key] = record
                changed.add(record.key)
            for key, old_hash, case_record in op.cases:
                if key in new_physical:
                    fail("immutable_source_changed", "conflict")
                previous = current.get(key) if key in packed else old.by_key.get(key)
                if (previous.etag if previous else None) != old_hash:
                    if key not in packed:
                        return None  # Recovery may already have removed a legacy source file.
                    fail("journal_integrity_error", "conflict")
                packed.add(key)
                changed.add(key)
                if case_record is None:
                    current.pop(key, None)
                else:
                    current[key] = case_record
        replaced = changed.intersection(old.by_key)
        retained = (
            tuple(item for item in old.ordered if item[1].key not in replaced)
            if replaced
            else old.ordered
        )
        updates = tuple((key_path(key), current[key]) for key in changed if key in current)
        ordered = tuple(sorted((*retained, *updates), key=lambda item: item[0]))
        records = tuple(record for _, record in ordered)
        return CapturedView(
            physical,
            evidence,
            records,
            frozenset(packed),
            current,
            ordered,
            old.records,
            frozenset(changed),
        )
