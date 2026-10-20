"""Recoverable project source transactions with immutable operation history."""

from __future__ import annotations

import json
import math
import re
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.identities import validate_resource_id
from deykit.contracts.json_value import JsonError, bytes_hash
from deykit.contracts.ports import (
    Collection,
    CommitReceipt,
    ResourceKey,
    SourceChange,
    StoredRecord,
)
from deykit.contracts.records import ProjectRecord
from deykit.storage._body_validation import _SuccessfulBodyValidationMemo
from deykit.storage._history_capture import (
    HistoryCapture,
    OperationEvidence,
    OperationValidationMemo,
)
from deykit.storage._journal_validation import _SuccessfulJournalValidationMemo
from deykit.storage.errors import fail
from deykit.storage.filesystem import Parts, SafeFiles
from deykit.storage.index import SourceIndex
from deykit.storage.journal import (
    Cancellation,
    CancellationAcknowledgement,
    CommitDecision,
    JournalEntry,
    JournalManifest,
)
from deykit.storage.locks import acquire
from deykit.storage.records import (
    IMMUTABLE,
    SCOPES,
    TYPES,
    key_path,
    path_key,
    validate_body,
)

FaultHook = Callable[[str], None]
IndexUpdater = Callable[[tuple[StoredRecord, ...]], None]
API_SOURCE_ADMISSION_TIMEOUT_SECONDS = 5.0


def _validate_admission_timeout(value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid_source_admission_timeout")
    try:
        valid = math.isfinite(value) and value >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("invalid_source_admission_timeout")


@dataclass(frozen=True)
class HistoryEntry:
    operation_id: str
    before: StoredRecord | None
    after: StoredRecord | None


class _SourceTreeVisitor:
    def __init__(
        self,
        records: list[StoredRecord],
        validator: Callable[[ResourceKey, bytes], object] = validate_body,
    ) -> None:
        self.records = records
        self.validator = validator

    def include(self, parts: Parts) -> bool:
        return not parts[-1].startswith(".tmp-")

    def validate_entry(self, parts: Parts, *, directory: bool) -> None:
        if not directory:
            path_key(parts)
            return
        if parts[1] not in TYPES or parts[1] == "project":
            fail("invalid_source_path")
        collection = cast(Collection, parts[1])
        if len(parts) > 2 + len(SCOPES.get(collection, ())):
            fail("invalid_source_path")
        for component in parts[2:]:
            try:
                validate_resource_id(component)
            except ValueError:
                fail("invalid_source_path")

    def accept_file(self, parts: Parts, body: bytes) -> None:
        key = path_key(parts)
        self.validator(key, body)
        self.records.append(StoredRecord(key, body, bytes_hash(body)))


class FileProjectSource:
    def __init__(
        self,
        root: Path,
        *,
        create: bool = False,
        fault_hook: FaultHook | None = None,
        index_updater: IndexUpdater | None = None,
        admission_timeout_seconds: float | None = None,
    ) -> None:
        _validate_admission_timeout(admission_timeout_seconds)
        self._initialize(
            SafeFiles(root, create=create),
            fault_hook,
            index_updater,
            admission_timeout_seconds,
        )

    def _initialize(
        self,
        files: SafeFiles,
        fault_hook: FaultHook | None,
        index_updater: IndexUpdater | None,
        admission_timeout_seconds: float | None = None,
    ) -> None:
        _validate_admission_timeout(admission_timeout_seconds)
        self.files = files
        self.root = self.files.root
        self._hook = fault_hook or (lambda _: None)
        self._index = index_updater or SourceIndex(self.files).rebuild
        self._mutex = threading.RLock()
        self._local = threading.local()
        self._body_validation = _SuccessfulBodyValidationMemo()
        self._journal_validation = _SuccessfulJournalValidationMemo()
        self._operation_validation = OperationValidationMemo()
        self._admission_timeout_seconds = admission_timeout_seconds
        self._admission_condition = threading.Condition()
        self._admission_waiters: deque[object] = deque()
        self.last_index_error: str | None = None

    @classmethod
    def _from_files(
        cls,
        files: SafeFiles,
        *,
        fault_hook: FaultHook | None = None,
        index_updater: IndexUpdater | None = None,
        admission_timeout_seconds: float | None = None,
    ) -> FileProjectSource:
        _validate_admission_timeout(admission_timeout_seconds)
        source = cls.__new__(cls)
        source._initialize(files, fault_hook, index_updater, admission_timeout_seconds)
        return source

    def close(self) -> None:
        with self._mutex:
            try:
                self.files.close()
            finally:
                self._body_validation.clear()
                self._journal_validation.clear()
                self._operation_validation.clear()

    def _validate_source_body(self, key: ResourceKey, body: bytes) -> None:
        if getattr(self._local, "source_depth", 0) <= 0:
            validate_body(key, body)
            return
        self._body_validation.validate(key, body)

    def __enter__(self) -> FileProjectSource:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @contextmanager
    def consistent_read(self) -> Iterator[FileProjectSource]:
        try:
            depth = getattr(self._local, "source_depth", 0)
            if depth:
                if not self._mutex.acquire(blocking=False):
                    fail("source_busy", "conflict")
                self._local.source_depth = depth + 1
                try:
                    if self.files.names(("history", "journal")):
                        self._local.records = None
                        self._local.checked_records = None
                        self._recover()
                    yield self
                except BaseException:
                    self._local.records = None
                    self._local.checked_records = None
                    raise
                finally:
                    self._local.source_depth = depth
                    self._mutex.release()
            else:
                with self._admission_ticket():
                    if not self._mutex.acquire(blocking=False):
                        fail("source_busy", "conflict")
                    try:
                        with acquire(self.files, "source.lock"):
                            self._local.source_depth = 1
                            self._local.records = None
                            self._local.checked_records = None
                            try:
                                self._recover()
                                yield self
                            finally:
                                self._local.records = None
                                self._local.checked_records = None
                                self._local.source_depth = 0
                    finally:
                        self._mutex.release()
        except OSError:
            fail("storage_io", "internal_error")
        except JsonError as error:
            fail(error.code)

    @contextmanager
    def _admission_ticket(self) -> Iterator[None]:
        timeout = self._admission_timeout_seconds
        if timeout is None:
            yield
            return
        ticket = object()
        deadline = time.monotonic() + timeout
        with self._admission_condition:
            self._admission_waiters.append(ticket)
            self._admission_condition.notify_all()
            waited = False
            try:
                while True:
                    if self._admission_waiters[0] is ticket:
                        if waited and time.monotonic() >= deadline:
                            fail("source_busy", "conflict")
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        fail("source_busy", "conflict")
                    self._admission_condition.wait(remaining)
                    waited = True
            except BaseException:
                self._admission_waiters.remove(ticket)
                self._admission_condition.notify_all()
                raise
        try:
            yield
        finally:
            with self._admission_condition:
                if self._admission_waiters and self._admission_waiters[0] is ticket:
                    self._admission_waiters.popleft()
                else:
                    self._admission_waiters.remove(ticket)
                self._admission_condition.notify_all()

    def _read(self, key: ResourceKey) -> StoredRecord | None:
        body = self.files.read(key_path(key))
        if body is None:
            return None
        self._validate_source_body(key, body)
        return StoredRecord(key, body, bytes_hash(body))

    def read(self, key: ResourceKey) -> StoredRecord | None:
        key_path(key)
        with self.consistent_read():
            records = self._all()
            self._check_integrity(records)
            return next((record for record in records if record.key == key), None)

    def _all(self) -> tuple[StoredRecord, ...]:
        captured = getattr(self._local, "records", None)
        if captured is not None:
            return cast(tuple[StoredRecord, ...], captured)
        return self._fresh_all()

    def _fresh_all(self) -> tuple[StoredRecord, ...]:
        records: list[StoredRecord] = []
        project = self.files.read(("deykit.project.json",))
        if project is not None:
            try:
                project_record = load_record(ProjectRecord, project)
            except JsonError as error:
                fail(error.code)
            records.append(
                StoredRecord(
                    ResourceKey("project", project_record.id), project, bytes_hash(project)
                )
            )
        self.files.read_tree(("source",), _SourceTreeVisitor(records, self._validate_source_body))
        captured = tuple(sorted(records, key=lambda item: key_path(item.key)))
        if getattr(self._local, "source_depth", 0):
            self._local.records = captured
        return captured

    def list_ids(self, collection: Collection, scope: tuple[str, ...] = ()) -> tuple[str, ...]:
        key_path(ResourceKey(collection, "scope-validation", scope))
        with self.consistent_read():
            records = self._all()
            self._check_integrity(records)
            return tuple(
                sorted(
                    record.key.resource_id
                    for record in records
                    if record.key.collection == collection and record.key.scope == scope
                )
            )

    def capture_snapshot(
        self, keys: tuple[ResourceKey, ...] | None = None
    ) -> tuple[StoredRecord, ...]:
        with self.consistent_read():
            before = self._all()
            self._check_integrity(before)
            self._hook("snapshot_captured")
            after = self._fresh_all()
            if before != after:
                self._local.checked_records = None
                fail("unstable_source", "conflict")
            self._local.records = before
            if keys is None:
                return before
            if len(set(keys)) != len(keys):
                fail("duplicate_resource_key")
            selected = {record.key: record for record in before}
            if any(key not in selected for key in keys):
                fail("snapshot_resource_missing", "not_found")
            return tuple(selected[key] for key in keys)

    def _payload(self, changes: tuple[SourceChange, ...]) -> str:
        value = [
            [
                change.key.collection,
                change.key.scope,
                change.key.resource_id,
                change.expected_etag,
                bytes_hash(change.body) if change.body is not None else None,
            ]
            for change in changes
        ]
        return bytes_hash(json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode())

    def operation_receipt(self, operation_id: str, *, intent_hash: str) -> CommitReceipt | None:
        self._validate_operation(operation_id, intent_hash)
        with self.consistent_read():
            self._check_integrity(self._all())
            folder = ("history", "operations", operation_id)
            if self.files.read((*folder, "manifest.json")) is None:
                return None
            manifest = self._manifest(folder)
            if manifest.intent_hash != intent_hash:
                fail("operation_id_conflict", "conflict")
            return self._receipt(folder, manifest, replayed=True)

    def _peek_durable_receipt(self, operation_id: str, *, intent_hash: str) -> CommitReceipt | None:
        """Inspect one durable receipt without locks, recovery, or writes."""
        self._validate_operation(operation_id, intent_hash)
        archived = ("history", "operations", operation_id)
        journal = ("history", "journal", operation_id)
        for attempt in range(3):
            location = self._receipt_location(operation_id, archived, journal)
            if location is None:
                return None
            folder = archived if location == "archived" else journal
            try:
                receipt = self._peek_receipt_folder(folder, operation_id, intent_hash=intent_hash)
            except ServiceFailure:
                relocated = self._receipt_location(operation_id, archived, journal)
                if attempt < 2 and relocated != location:
                    continue
                raise
            if self._receipt_location(operation_id, archived, journal) != location:
                if attempt < 2:
                    continue
                fail("unstable_source", "conflict")
            return receipt
        fail("unstable_source", "conflict")

    def _receipt_location(self, operation_id: str, archived: Parts, journal: Parts) -> str | None:
        has_archive = operation_id in self.files.names(archived[:-1])
        has_journal = operation_id in self.files.names(journal[:-1])
        if has_archive and has_journal:
            fail("journal_integrity_error", "conflict")
        return "archived" if has_archive else "journal" if has_journal else None

    def _peek_receipt_folder(
        self, folder: Parts, operation_id: str, *, intent_hash: str
    ) -> CommitReceipt:
        manifest_body = self.files.read((*folder, "manifest.json"))
        if manifest_body is None:
            fail("journal_manifest_missing", "conflict")
        manifest = self._manifest(folder)
        if manifest.intent_hash != intent_hash:
            fail("operation_id_conflict", "conflict")
        expected_files = {"manifest.json", "commit.json"}
        for index, entry in enumerate(manifest.entries):
            for old in (True, False):
                body = self._blob(folder, index, entry, old=old)
                if body is not None:
                    expected_files.add(f"{'old' if old else 'new'}-{index}.json")
        if set(self.files.names(folder)) != expected_files:
            fail("journal_integrity_error", "conflict")
        if manifest.operation_id != operation_id:
            fail("journal_identity_mismatch", "conflict")
        # Demo creation is a create-only operation. The application checks its graph.
        if any(entry.old_hash is not None or entry.new_hash is None for entry in manifest.entries):
            fail("journal_integrity_error", "conflict")
        if (
            self.files.read((*folder, "manifest.json")) != manifest_body
            or self._manifest(folder) != manifest
        ):
            fail("unstable_source", "conflict")
        return self._receipt(folder, manifest, replayed=True)

    @staticmethod
    def _validate_operation(operation_id: str, intent_hash: str | None) -> None:
        try:
            validate_resource_id(operation_id)
        except ValueError:
            fail("invalid_operation_id")
        if intent_hash is not None and not re.fullmatch(r"[0-9a-f]{64}", intent_hash):
            fail("invalid_intent_hash")

    def commit(
        self,
        operation_id: str,
        changes: tuple[SourceChange, ...],
        *,
        intent_hash: str | None = None,
    ) -> CommitReceipt:
        self._validate_operation(operation_id, intent_hash)
        if not changes or len({change.key for change in changes}) != len(changes):
            fail("invalid_changes")
        ordered = tuple(sorted(changes, key=lambda change: key_path(change.key)))
        if len({key_path(change.key) for change in ordered}) != len(ordered):
            fail("duplicate_target_path", "conflict")
        payload = self._payload(ordered)
        with self.consistent_read():
            current = self._all()  # Invalid/unknown versions anywhere block mutation.
            # Preparation callbacks can expose uncooperative history edits within this epoch.
            self._local.checked_records = None
            self._check_integrity(current)
            archived = ("history", "operations", operation_id)
            previous = self.files.read((*archived, "manifest.json"))
            if previous is not None:
                manifest = self._manifest(archived)
                if manifest.intent_hash != intent_hash or (
                    intent_hash is None and manifest.payload_hash != payload
                ):
                    fail("operation_id_conflict", "conflict")
                return self._receipt(archived, manifest, replayed=True)
            existing = {record.key: record for record in current}
            entries: list[JournalEntry] = []
            for change in ordered:
                self.files.check_path_spelling(key_path(change.key))
                if change.key.collection == "project" and change.body is None:
                    fail("project_identity_immutable", "conflict")
                old = existing.get(change.key)
                if (old.etag if old else None) != change.expected_etag:
                    fail("revision_changed", "conflict")
                if change.body is None and old is None:
                    fail("delete_missing_record", "not_found")
                if change.key.collection in IMMUTABLE and old is not None:
                    if change.key.collection == "segments" and change.body is not None:
                        self._validate_segment_end(old, change.body)
                    else:
                        fail("immutable_record", "conflict")
                if change.body is not None:
                    self._validate_source_body(change.key, change.body)
                entries.append(
                    JournalEntry(
                        collection=change.key.collection,
                        resource_id=change.key.resource_id,
                        scope=change.key.scope,
                        old_hash=old.etag if old else None,
                        new_hash=bytes_hash(change.body) if change.body is not None else None,
                    )
                )
            final_keys = set(existing)
            for change in ordered:
                if change.body is None:
                    final_keys.discard(change.key)
                else:
                    final_keys.add(change.key)
            self._check_collisions(final_keys)
            sequence = cast(int, self._local.next_sequence)
            manifest = JournalManifest(
                operation_id=operation_id,
                payload_hash=payload,
                entries=tuple(entries),
                intent_hash=intent_hash,
                sequence=sequence,
            )
            manifest_body = dump_record(manifest)
            stage = ("history", "journal", operation_id)
            self.files.mkdir(stage)
            for index, change in enumerate(ordered):
                old = existing.get(change.key)
                if old is not None:
                    self.files.replace((*stage, f"old-{index}.json"), old.body)
                if change.body is not None:
                    self.files.replace((*stage, f"new-{index}.json"), change.body)
                self._hook(f"staged:{index}")
            self.files.replace((*stage, "manifest.json"), manifest_body)
            self._hook("prepared")
            if current != self._fresh_all():
                self._local.checked_records = None
                fail("unstable_source", "conflict")
            self._local.records = None
            self._local.checked_records = None
            self.files.replace(
                (*stage, "commit.json"),
                dump_record(
                    CommitDecision(
                        operation_id=operation_id, manifest_hash=bytes_hash(manifest_body)
                    )
                ),
            )
            self._hook("decided")
            self._apply(stage, manifest)
            for change in ordered:
                if change.body is None:
                    existing.pop(change.key, None)
                else:
                    existing[change.key] = StoredRecord(
                        change.key, change.body, bytes_hash(change.body)
                    )
            self.files.rename_directory(stage, archived)
            updated = tuple(sorted(existing.values(), key=lambda item: key_path(item.key)))
            self._local.records = updated
            self._local.checked_records = updated
            self._hook("archived")
            self._update_index()
            return self._receipt(archived, manifest, replayed=False)

    @staticmethod
    def _validate_segment_end(old: StoredRecord, new_body: bytes) -> None:
        previous = validate_body(old.key, old.body).model_dump()
        new = validate_body(old.key, new_body).model_dump()
        previous_end = previous.pop("ended_at")
        new_end = new.pop("ended_at")
        if previous != new or previous_end is not None or new_end is None:
            fail("immutable_record", "conflict")
        if datetime.fromisoformat(new_end) < datetime.fromisoformat(new["started_at"]):
            fail("invalid_segment_end")

    @staticmethod
    def _check_collisions(keys: set[ResourceKey]) -> None:
        paths = [key_path(key) for key in keys]
        folded: dict[tuple[str, ...], tuple[str, ...]] = {}
        project_count = sum(key.collection == "project" for key in keys)
        if project_count > 1:
            fail("project_identity_conflict", "conflict")
        for path in paths:
            for depth in range(1, len(path) + 1):
                prefix = path[:depth]
                canonical = tuple(component.casefold() for component in prefix)
                if canonical in folded and folded[canonical] != prefix:
                    fail("casefold_collision", "conflict")
                folded[canonical] = prefix

    def _history_read(self, parts: Parts) -> bytes | None:
        captured = getattr(self._local, "history_capture", None)
        if captured is not None and parts[:2] == ("history", "operations"):
            return cast(HistoryCapture, captured).read(parts)
        return self.files.read(parts)

    def _manifest(self, folder: Parts) -> JournalManifest:
        body = self._history_read((*folder, "manifest.json"))
        if body is None:
            fail("journal_manifest_missing", "conflict")
        try:
            manifest = (
                self._journal_validation.load(JournalManifest, body)
                if getattr(self._local, "source_depth", 0) > 0
                else load_record(JournalManifest, body)
            )
        except JsonError:
            fail("journal_invalid", "conflict")
        if manifest.operation_id != folder[-1]:
            fail("journal_identity_mismatch", "conflict")
        decision = self._history_read((*folder, "commit.json"))
        if decision is None:
            fail("journal_decision_missing", "conflict")
        try:
            marker = (
                self._journal_validation.load(CommitDecision, decision)
                if getattr(self._local, "source_depth", 0) > 0
                else load_record(CommitDecision, decision)
            )
        except JsonError:
            fail("journal_invalid", "conflict")
        if marker.operation_id != manifest.operation_id or marker.manifest_hash != bytes_hash(body):
            fail("journal_integrity_error", "conflict")
        return manifest

    def _blob(self, folder: Parts, index: int, entry: JournalEntry, *, old: bool) -> bytes | None:
        expected = entry.old_hash if old else entry.new_hash
        if expected is None:
            return None
        body = self._history_read((*folder, f"{'old' if old else 'new'}-{index}.json"))
        if body is None or bytes_hash(body) != expected:
            fail("journal_integrity_error", "conflict")
        self._validate_source_body(entry.key, body)
        return body

    def _apply(self, folder: Parts, manifest: JournalManifest) -> None:
        # Validate every blob/target before applying anything. Recovery never overwrites
        # unrelated external changes and can repeat after every replacement boundary.
        new_bodies = []
        for index, entry in enumerate(manifest.entries):
            self._blob(folder, index, entry, old=True)
            body = self._blob(folder, index, entry, old=False)
            current = self._read(entry.key)
            if (current.etag if current else None) not in (entry.old_hash, entry.new_hash):
                fail("recovery_source_conflict", "conflict")
            new_bodies.append(body)
        for index, (entry, body) in enumerate(zip(manifest.entries, new_bodies, strict=True)):
            if body is None:
                self.files.unlink(key_path(entry.key))
            else:
                self.files.replace(key_path(entry.key), body)
            self._hook(f"applied:{index}")

    def _recover(self) -> None:
        self._local.records = None
        self._local.checked_records = None
        # Completed history must be intact before even recovery may alter source.
        # Pending replacements can temporarily differ from the latest completed ledger.
        pending = self.files.names(("history", "journal"))
        if pending:
            self._check_integrity(self._all(), check_current=False)
        for operation_id in pending:
            try:
                validate_resource_id(operation_id)
            except ValueError:
                fail("invalid_journal_path", "conflict")
            folder = ("history", "journal", operation_id)
            if self.files.read((*folder, "commit.json")) is None:
                self.files.remove_directory(folder)
                self._hook("discarded")
                continue
            manifest = self._manifest(folder)
            self._local.records = None
            self._local.checked_records = None
            self._apply(folder, manifest)
            self.files.rename_directory(folder, ("history", "operations", operation_id))
            self._local.records = None
            self._local.checked_records = None
            self._hook("recovered")
            self._update_index()
        self._check_integrity(self._all())

    def _receipt(
        self, folder: Parts, manifest: JournalManifest, *, replayed: bool
    ) -> CommitReceipt:
        records = []
        deleted = []
        for index, entry in enumerate(manifest.entries):
            body = self._blob(folder, index, entry, old=False)
            if body is None:
                deleted.append(entry.key)
            else:
                records.append(StoredRecord(entry.key, body, bytes_hash(body)))
        return CommitReceipt(manifest.operation_id, tuple(records), replayed, tuple(deleted))

    def _check_integrity(
        self, records: tuple[StoredRecord, ...], *, check_current: bool = True
    ) -> None:
        if getattr(self._local, "checked_records", None) is records:
            return
        captured = HistoryCapture(self.files)
        self._local.history_capture = captured
        try:
            self._check_captured_integrity(records, captured, check_current=check_current)
            if check_current:
                self._local.checked_records = records
        finally:
            self._local.history_capture = None

    def _check_captured_integrity(
        self, records: tuple[StoredRecord, ...], captured: HistoryCapture, *, check_current: bool
    ) -> None:
        latest: dict[ResourceKey, tuple[int, str | None]] = {}
        project_ids: set[str] = set()
        sequences: set[int] = set()
        for operation_id in captured.names(("history", "operations")):
            folder = ("history", "operations", operation_id)
            bodies = captured.operations.get(operation_id, {})
            cached = self._operation_validation.get(operation_id, bodies)
            if cached is None:
                manifest = self._manifest(folder)
                expected_files = {"manifest.json", "commit.json"}
                keyed = tuple((entry.key, entry) for entry in manifest.entries)
                paths = [key_path(key) for key, _ in keyed]
                if len(set(paths)) != len(paths):
                    fail("duplicate_target_path", "conflict")
                for index, (key, entry) in enumerate(keyed):
                    for old, digest in ((True, entry.old_hash), (False, entry.new_hash)):
                        self._blob(folder, index, entry, old=old)
                        if digest is not None:
                            expected_files.add(f"{'old' if old else 'new'}-{index}.json")
                    if key.collection == "project" and entry.new_hash is None:
                        fail("project_identity_immutable", "conflict")
                if set(captured.names(folder)) != expected_files:
                    fail("journal_integrity_error", "conflict")
                cached = OperationEvidence(
                    manifest.sequence, tuple((key, entry.new_hash) for key, entry in keyed)
                )
                self._operation_validation.put(operation_id, bodies, cached)
            sequence, entries = cached.sequence, cached.entries
            if sequence in sequences:
                fail("journal_sequence_conflict", "conflict")
            sequences.add(sequence)
            for key, new_hash in entries:
                if key.collection == "project":
                    project_ids.add(key.resource_id)
                if key.collection in IMMUTABLE:
                    if key not in latest or latest[key][0] < sequence:
                        latest[key] = (sequence, new_hash)
        self._local.next_sequence = max(sequences, default=0) + 1
        current = {record.key: record.etag for record in records}
        current_projects = {key.resource_id for key in current if key.collection == "project"}
        if len(project_ids) > 1 or (project_ids and current_projects != project_ids):
            fail("project_identity_changed", "conflict")
        if check_current:
            for key, (_, expected_hash) in latest.items():
                if current.get(key) != expected_hash:
                    fail("immutable_source_changed", "conflict")
        self._validate_cancellation_history(set(current))

    def _validate_cancellation_history(self, keys: set[ResourceKey]) -> None:
        run_ids: set[str] = set()
        for collection in ("cancellations", "cancel_ack"):
            for run_id in self.files.names(("history", collection)):
                self._valid_run_id(run_id)
                if ResourceKey("runs", run_id) not in keys:
                    fail("cancellation_run_missing", "conflict")
                run_ids.add(run_id)
        for run_id in run_ids:
            self._cancellations(run_id)
            for name in self.files.names(("history", "cancel_ack", run_id)):
                if re.fullmatch(r"\.tmp-[0-9a-f]{32}", name):
                    continue
                segment_id = name.removesuffix(".json")
                if ResourceKey("segments", segment_id, (run_id,)) not in keys:
                    fail("cancellation_segment_missing", "conflict")

    def operation_history(self, key: ResourceKey) -> tuple[HistoryEntry, ...]:
        with self.consistent_read():
            history = []
            manifests = [
                self._manifest(("history", "operations", name))
                for name in self.files.names(("history", "operations"))
            ]
            for manifest in sorted(manifests, key=lambda item: item.sequence):
                operation_id = manifest.operation_id
                folder = ("history", "operations", operation_id)
                for index, entry in enumerate(manifest.entries):
                    if entry.key != key:
                        continue
                    old = self._blob(folder, index, entry, old=True)
                    new = self._blob(folder, index, entry, old=False)
                    history.append(
                        HistoryEntry(
                            operation_id,
                            StoredRecord(key, old, bytes_hash(old)) if old is not None else None,
                            StoredRecord(key, new, bytes_hash(new)) if new is not None else None,
                        )
                    )
            return tuple(history)

    def _update_index(self) -> None:
        try:
            self._index(self._all())
            self.last_index_error = None
        except Exception:
            # Source commit is durable; a cache failure cannot undo it or obscure success.
            self.last_index_error = "index_unavailable"

    def rebuild_index(self) -> int:
        with self.consistent_read():
            records = self.capture_snapshot()
            try:
                self._index(records)
            except Exception:
                fail("index_unavailable", "internal_error")
            self.last_index_error = None
            return len(records)

    @contextmanager
    def execution_owner(self) -> Iterator[None]:
        if getattr(self._local, "source_depth", 0):
            fail("lock_order_violation", "conflict")
        try:
            with acquire(self.files, "execution.lock", execution=True):
                self._local.execution_owned = True
                try:
                    yield
                finally:
                    self._local.execution_owned = False
        except OSError:
            fail("storage_io", "internal_error")

    def execution_active(self) -> bool:
        try:
            with self.execution_owner():
                return False
        except ServiceFailure as error:
            if error.error.code == "execution_locked":
                return True
            raise

    def _cancellations(self, run_id: str) -> tuple[str, ...]:
        requests: set[str] = set()
        acknowledged: set[str] = set()
        for name in self.files.names(("history", "cancellations", run_id)):
            if re.fullmatch(r"\.tmp-[0-9a-f]{32}", name):
                continue
            body = self.files.read(("history", "cancellations", run_id, name))
            try:
                request = load_record(Cancellation, body or b"")
            except JsonError:
                fail("invalid_cancellation")
            if request.run_id != run_id or name != request.id + ".json":
                fail("invalid_cancellation")
            requests.add(request.id)
        for name in self.files.names(("history", "cancel_ack", run_id)):
            if re.fullmatch(r"\.tmp-[0-9a-f]{32}", name):
                continue
            body = self.files.read(("history", "cancel_ack", run_id, name))
            try:
                ack = load_record(CancellationAcknowledgement, body or b"")
            except JsonError:
                fail("invalid_cancellation")
            if ack.run_id != run_id or name != ack.segment_id + ".json":
                fail("invalid_cancellation")
            acknowledged.update(ack.request_ids)
        if not acknowledged.issubset(requests):
            fail("invalid_cancellation")
        return tuple(sorted(requests - acknowledged))

    @staticmethod
    def _valid_run_id(run_id: str) -> None:
        try:
            validate_resource_id(run_id)
        except ValueError:
            fail("invalid_resource_id")

    def request_cancel(self, run_id: str) -> None:
        self._valid_run_id(run_id)
        with self.consistent_read():
            if self._read(ResourceKey("runs", run_id)) is None:
                fail("run_missing", "not_found")
            if self._cancellations(run_id):
                return
            request = Cancellation(id=uuid4().hex, run_id=run_id)
            self.files.replace(
                ("history", "cancellations", run_id, request.id + ".json"), dump_record(request)
            )

    def cancellation_requested(self, run_id: str) -> bool:
        self._valid_run_id(run_id)
        with self.consistent_read():
            return bool(self._cancellations(run_id))

    def acknowledge_cancel(self, run_id: str, segment_id: str) -> None:
        """Explicit resume consumes prior cancellation requests, preserving all history."""
        self._valid_run_id(run_id)
        self._valid_run_id(segment_id)
        if not getattr(self._local, "execution_owned", False):
            fail("execution_ownership_required", "execution_locked")
        with self.consistent_read():
            if self._read(ResourceKey("segments", segment_id, (run_id,))) is None:
                fail("segment_missing", "not_found")
            path = ("history", "cancel_ack", run_id, segment_id + ".json")
            pending = self._cancellations(run_id)
            if self.files.read(path) is not None:
                if pending:
                    fail("new_cancellation_requires_new_segment", "conflict")
                return
            self.files.replace(
                path,
                dump_record(
                    CancellationAcknowledgement(
                        run_id=run_id, segment_id=segment_id, request_ids=pending
                    )
                ),
            )
