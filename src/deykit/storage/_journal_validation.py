"""Bounded reuse of successful journal parsing for exact record types and bytes."""

from collections import OrderedDict
from typing import TypeVar, cast

from deykit.contracts.codec import load_record
from deykit.storage.journal import CommitDecision, JournalManifest

J = TypeVar("J", JournalManifest, CommitDecision)
_MAX_ENTRIES = 2048
_MAX_RETAINED_BYTES = 8 * 1024 * 1024


class _SuccessfulJournalValidationMemo:
    def __init__(self) -> None:
        self._entries: OrderedDict[
            tuple[type[JournalManifest] | type[CommitDecision], bytes],
            JournalManifest | CommitDecision,
        ] = OrderedDict()
        self._retained_bytes = 0

    def load(self, kind: type[J], body: bytes) -> J:
        identity = (kind, body)
        cached = self._entries.get(identity)
        if cached is not None:
            self._entries.move_to_end(identity)
            return cast(J, cached)
        record = load_record(kind, body)
        if len(body) > _MAX_RETAINED_BYTES:
            return record
        self._entries[identity] = record
        self._retained_bytes += len(body)
        while len(self._entries) > _MAX_ENTRIES or self._retained_bytes > _MAX_RETAINED_BYTES:
            (_, evicted_body), _ = self._entries.popitem(last=False)
            self._retained_bytes -= len(evicted_body)
        return record

    def clear(self) -> None:
        self._entries.clear()
        self._retained_bytes = 0
