"""Small inward-facing capabilities. Adapters implement these; domain never imports them."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Literal, Protocol, get_args

from deykit.contracts.identities import validate_resource_id
from deykit.contracts.json_value import JsonValue
from deykit.contracts.records import (
    ChoiceDefinition,
    CompiledRequest,
    DispatchOutcome,
    NormalizedAnswer,
    ProviderProfile,
)


class Clock(Protocol):
    def utc_now(self) -> str: ...
    def monotonic(self) -> float: ...


class ChoiceCompiler(Protocol):
    """Pure compilation and response validation; no credentials or network."""

    @property
    def review_identity(self) -> CompilerIdentity: ...

    def compile(
        self, definition: ChoiceDefinition, selected_state: JsonValue, profile: ProviderProfile
    ) -> CompiledRequest: ...

    def validate_response(
        self, request: CompiledRequest, response_source: str
    ) -> NormalizedAnswer: ...


@dataclass(frozen=True)
class CompilerIdentity:
    compiler: str
    compiler_version: str


class ProviderTransport(Protocol):
    """Exactly one dispatch. Credentials are resolved privately by the implementation."""

    async def dispatch(
        self, request: CompiledRequest, *, timeout_seconds: float
    ) -> DispatchOutcome: ...


Collection = Literal[
    "project",
    "decisions",
    "drafts",
    "revisions",
    "datasets",
    "cases",
    "labels",
    "label_history",
    "dataset_snapshots",
    "label_snapshots",
    "providers",
    "fixtures",
    "runs",
    "prepared_cases",
    "run_controls",
    "segments",
    "run_events",
    "attempts",
    "attempt_events",
    "result_snapshots",
    "evaluations",
    "annotations",
    "comparisons",
    "execution_groups",
    "group_segments",
    "diagnostic_snapshots",
    "check_snapshots",
    "regression_removals",
    "regressions",
    "reports",
]


@dataclass(frozen=True)
class ResourceKey:
    collection: Collection
    resource_id: str
    scope: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_resource_id(self.resource_id)
        if not isinstance(self.scope, tuple):
            raise ValueError("invalid_scope")
        for component in self.scope:
            validate_resource_id(component)
        if self.collection not in get_args(Collection):
            raise ValueError("invalid_collection")


@dataclass(frozen=True)
class StoredRecord:
    key: ResourceKey
    body: bytes
    etag: str


@dataclass(frozen=True)
class SourceChange:
    """None expected_etag means create-only; body None means delete an existing record."""

    key: ResourceKey
    body: bytes | None
    expected_etag: str | None


@dataclass(frozen=True)
class CommitReceipt:
    operation_id: str
    changes: tuple[StoredRecord, ...]
    replayed: bool = False
    deleted_keys: tuple[ResourceKey, ...] = ()


class ProjectSource(Protocol):
    """Authoritative source, with recovery before reads and atomic conflict-checked commits."""

    def read(self, key: ResourceKey) -> StoredRecord | None: ...
    def list_ids(self, collection: Collection, scope: tuple[str, ...] = ()) -> tuple[str, ...]: ...
    def consistent_read(self) -> AbstractContextManager[ProjectSource]: ...
    def operation_receipt(self, operation_id: str, *, intent_hash: str) -> CommitReceipt | None: ...
    def commit(
        self,
        operation_id: str,
        changes: tuple[SourceChange, ...],
        *,
        intent_hash: str | None = None,
    ) -> CommitReceipt: ...


class SnapshotSource(ProjectSource, Protocol):
    """One consistent batch capture for lifecycle/evaluation readers."""

    def capture_snapshot(
        self, keys: tuple[ResourceKey, ...] | None = None
    ) -> tuple[StoredRecord, ...]: ...


class RecordViewSource(Protocol):
    """Admit fresh source/history, then reuse that lock epoch's validated record view."""

    def read_records(self) -> tuple[StoredRecord, ...]: ...


@dataclass(frozen=True)
class RecordViewDelta:
    records: tuple[StoredRecord, ...]
    # None requests full reconstruction. Empty changes means exact unchanged records.
    changes: tuple[StoredRecord, ...] | None = None
    deleted_keys: tuple[ResourceKey, ...] = ()
    previous_records: tuple[StoredRecord, ...] | None = None


class IncrementalRecordViewSource(Protocol):
    """Fresh admission plus a proved difference from an exact previous logical view."""

    def read_record_view(self, previous: tuple[StoredRecord, ...] | None) -> RecordViewDelta: ...
