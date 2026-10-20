"""Extend the immutable ledger only from freshly compared operation evidence."""

from collections.abc import Iterable

from deykit.contracts.ports import ResourceKey, StoredRecord
from deykit.storage._history_capture import OperationEvidence
from deykit.storage._source_view import CapturedView
from deykit.storage.errors import fail
from deykit.storage.records import IMMUTABLE


class IntegrityIndex:
    def __init__(self) -> None:
        self.operations: dict[int, OperationEvidence] = {}
        self.latest: dict[ResourceKey, tuple[int, str | None]] = {}
        self.project_ids: set[str] = set()
        self.records: tuple[StoredRecord, ...] | None = None

    def clear(self) -> None:
        self.operations.clear()
        self.latest.clear()
        self.project_ids.clear()
        self.records = None

    def check(
        self,
        evidence: tuple[OperationEvidence, ...],
        records: tuple[StoredRecord, ...],
        view: CapturedView | None,
        *,
        check_current: bool,
    ) -> tuple[int, dict[ResourceKey, StoredRecord]]:
        try:
            operations = {op.sequence: op for op in evidence}
            if len(operations) != len(evidence):
                fail("journal_sequence_conflict", "conflict")
            if any(operations.get(n) is not op for n, op in self.operations.items()):
                self.clear()
            changed = set()
            for sequence, operation in operations.items():
                if sequence in self.operations:
                    continue
                for key, digest in operation.entries:
                    if key.collection == "project":
                        self.project_ids.add(key.resource_id)
                    if key.collection in IMMUTABLE:
                        if key not in self.latest or self.latest[key][0] < sequence:
                            self.latest[key] = (sequence, digest)
                            changed.add(key)
            admitted = view is not None and view.records is records
            current = view.by_key if admitted and view is not None else {r.key: r for r in records}
            physical = view.physical if admitted and view is not None else records
            current_projects = {
                r.key.resource_id for r in physical if r.key.collection == "project"
            }
            if len(self.project_ids) > 1 or (
                self.project_ids and current_projects != self.project_ids
            ):
                fail("project_identity_changed", "conflict")
            if check_current:
                keys: Iterable[ResourceKey]
                if records is self.records:
                    keys = changed
                elif (
                    self.records is not None
                    and admitted
                    and view is not None
                    and view.parent_records is self.records
                ):
                    keys = changed | view.changed
                else:
                    keys = self.latest.keys()
                for key in keys:
                    if key in self.latest:
                        record = current.get(key)
                        if (record.etag if record else None) != self.latest[key][1]:
                            fail("immutable_source_changed", "conflict")
            sequence = max(operations, default=0) + 1
            if admitted and len(self.latest) <= 131_072 and len(operations) <= 65_536:
                self.operations = operations
                self.records = records if check_current else None
            else:
                self.clear()
            return sequence, current
        except BaseException:
            self.clear()
            raise
