"""One anchored inventory of completed operation bytes for integrity validation."""

from collections import OrderedDict
from dataclasses import dataclass

from deykit.contracts.identities import validate_resource_id
from deykit.contracts.ports import ResourceKey, StoredRecord
from deykit.storage._chunks import CHUNK_LIMIT
from deykit.storage.errors import fail
from deykit.storage.filesystem import Parts, SafeFiles


class HistoryCapture:
    def __init__(self, files: SafeFiles) -> None:
        self.bodies: dict[Parts, bytes] = {}
        self.children: dict[Parts, set[str]] = {}
        self.operations: dict[str, dict[str, bytes]] = {}
        files.read_tree(("history", "operations"), self, limit=CHUNK_LIMIT)

    def include(self, parts: Parts) -> bool:
        return True

    def validate_entry(self, parts: Parts, *, directory: bool) -> None:
        if len(parts) == 3 and directory:
            try:
                validate_resource_id(parts[-1])
            except ValueError:
                fail("invalid_operation_id")
        elif len(parts) != 4 or directory:
            fail("journal_integrity_error", "conflict")
        self.children.setdefault(parts[:-1], set()).add(parts[-1])

    def accept_file(self, parts: Parts, body: bytes) -> None:
        self.bodies[parts] = body
        self.operations.setdefault(parts[2], {})[parts[3]] = body

    def read(self, parts: Parts) -> bytes | None:
        return self.bodies.get(parts)

    def names(self, parts: Parts) -> tuple[str, ...]:
        return tuple(sorted(self.children.get(parts, ())))


@dataclass(frozen=True)
class OperationEvidence:
    sequence: int
    entries: tuple[tuple[ResourceKey, str | None], ...]
    records: tuple[StoredRecord, ...] = ()
    reference: tuple[str, bytes] | None = None
    cases: tuple[tuple[ResourceKey, str | None, StoredRecord | None], ...] = ()


class OperationValidationMemo:
    """Reuse successful operation validation only after comparing every freshly read byte."""

    def __init__(self) -> None:
        self.entries: OrderedDict[str, tuple[dict[str, bytes], OperationEvidence]] = OrderedDict()
        self.bytes = 0

    def get(self, operation_id: str, bodies: dict[str, bytes]) -> OperationEvidence | None:
        previous = self.entries.get(operation_id)
        if previous is None or previous[0] != bodies:
            return None
        self.entries.move_to_end(operation_id)
        return previous[1]

    def put(self, operation_id: str, bodies: dict[str, bytes], value: OperationEvidence) -> None:
        previous = self.entries.pop(operation_id, None)
        if previous is not None:
            self.bytes -= self._weight(*previous)
        weight = self._weight(bodies, value)
        if weight > 128 * 1024 * 1024:
            return
        self.entries[operation_id] = (bodies, value)
        self.bytes += weight
        while len(self.entries) > 65_536 or self.bytes > 128 * 1024 * 1024:
            _, (removed, evidence) = self.entries.popitem(last=False)
            self.bytes -= self._weight(removed, evidence)

    @staticmethod
    def _weight(bodies: dict[str, bytes], evidence: OperationEvidence) -> int:
        return (
            sum(map(len, bodies.values()))
            + sum(len(record.body) for record in evidence.records)
            + (len(evidence.reference[1]) if evidence.reference else 0)
            + sum(len(record.body) for _, _, record in evidence.cases if record is not None)
        )

    def clear(self) -> None:
        self.entries.clear()
        self.bytes = 0
