"""Ephemeral ProjectSource used only to author an atomic packaged demo batch."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock

from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import validate_resource_id
from deykit.contracts.json_value import bytes_hash
from deykit.contracts.ports import (
    Collection,
    CommitReceipt,
    ResourceKey,
    SourceChange,
    StoredRecord,
)


class DemoStagingSource:
    """Small in-memory source that delegates all record semantics to app services."""

    last_index_error: str | None = None

    def __init__(self) -> None:
        self._records: dict[ResourceKey, StoredRecord] = {}
        self._receipts: dict[str, tuple[str | None, str, CommitReceipt]] = {}
        self._lock = RLock()
        self._closed = False

    def _ensure_open(self) -> None:
        if self._closed:
            raise ServiceFailure(ServiceError(code="conflict", reason="source_closed"))

    @staticmethod
    def _payload(changes: tuple[SourceChange, ...]) -> str:
        ordered = sorted(
            changes,
            key=lambda change: (
                change.key.collection,
                change.key.scope,
                change.key.resource_id,
            ),
        )
        value = [
            [
                change.key.collection,
                change.key.scope,
                change.key.resource_id,
                change.expected_etag,
                bytes_hash(change.body) if change.body is not None else None,
            ]
            for change in ordered
        ]
        return bytes_hash(json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode())

    @contextmanager
    def consistent_read(self) -> Iterator[DemoStagingSource]:
        with self._lock:
            self._ensure_open()
            yield self

    def read(self, key: ResourceKey) -> StoredRecord | None:
        with self.consistent_read():
            return self._records.get(key)

    def list_ids(self, collection: Collection, scope: tuple[str, ...] = ()) -> tuple[str, ...]:
        with self.consistent_read():
            return tuple(
                sorted(
                    key.resource_id
                    for key in self._records
                    if key.collection == collection and key.scope == scope
                )
            )

    def capture_snapshot(
        self, keys: tuple[ResourceKey, ...] | None = None
    ) -> tuple[StoredRecord, ...]:
        with self.consistent_read():
            if keys is None:
                return tuple(
                    self._records[key]
                    for key in sorted(
                        self._records,
                        key=lambda item: (item.collection, item.scope, item.resource_id),
                    )
                )
            if len(keys) != len(set(keys)):
                raise ServiceFailure(
                    ServiceError(code="validation_error", reason="duplicate_resource_key")
                )
            if any(key not in self._records for key in keys):
                raise ServiceFailure(
                    ServiceError(code="not_found", reason="snapshot_resource_missing")
                )
            return tuple(self._records[key] for key in keys)

    def operation_receipt(self, operation_id: str, *, intent_hash: str) -> CommitReceipt | None:
        try:
            validate_resource_id(operation_id)
        except ValueError:
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_operation_id")
            ) from None
        if type(intent_hash) is not str or re.fullmatch(r"[0-9a-f]{64}", intent_hash) is None:
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_intent_hash")
            )
        with self.consistent_read():
            previous = self._receipts.get(operation_id)
            if previous is None:
                return None
            old_intent, _, receipt = previous
            if old_intent != intent_hash:
                raise ServiceFailure(ServiceError(code="conflict", reason="operation_id_conflict"))
            return CommitReceipt(
                receipt.operation_id, receipt.changes, True, receipt.deleted_keys
            )

    def commit(
        self,
        operation_id: str,
        changes: tuple[SourceChange, ...],
        *,
        intent_hash: str | None = None,
    ) -> CommitReceipt:
        try:
            validate_resource_id(operation_id)
        except ValueError:
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_operation_id")
            ) from None
        if not changes or len({change.key for change in changes}) != len(changes):
            raise ServiceFailure(ServiceError(code="validation_error", reason="invalid_changes"))
        if intent_hash is not None and (
            type(intent_hash) is not str or re.fullmatch(r"[0-9a-f]{64}", intent_hash) is None
        ):
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_intent_hash")
            )
        payload = self._payload(changes)
        with self.consistent_read():
            previous = self._receipts.get(operation_id)
            if previous is not None:
                old_intent, old_payload, receipt = previous
                if old_intent != intent_hash or (intent_hash is None and old_payload != payload):
                    raise ServiceFailure(
                        ServiceError(code="conflict", reason="operation_id_conflict")
                    )
                return CommitReceipt(
                    receipt.operation_id, receipt.changes, True, receipt.deleted_keys
                )
            staged = self._records.copy()
            stored: list[StoredRecord] = []
            deleted: list[ResourceKey] = []
            for change in changes:
                current = staged.get(change.key)
                if (current.etag if current else None) != change.expected_etag:
                    raise ServiceFailure(ServiceError(code="conflict", reason="revision_changed"))
                if change.body is None:
                    if current is None:
                        raise ServiceFailure(
                            ServiceError(code="not_found", reason="delete_missing_record")
                        )
                    del staged[change.key]
                    deleted.append(change.key)
                else:
                    record = StoredRecord(change.key, change.body, bytes_hash(change.body))
                    staged[change.key] = record
                    stored.append(record)
            receipt = CommitReceipt(operation_id, tuple(stored), False, tuple(deleted))
            self._records = staged
            self._receipts[operation_id] = (intent_hash, payload, receipt)
            return receipt

    def execution_active(self) -> bool:
        with self.consistent_read():
            return False

    def rebuild_index(self) -> int:
        with self.consistent_read():
            return len(self._records)

    def close(self) -> None:
        with self._lock:
            self._closed = True
