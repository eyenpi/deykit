"""Bounded reuse of typed lifecycle records, keyed by exact captured source bytes."""

from collections import OrderedDict
from threading import RLock
from typing import TypeVar, cast

from deykit.application.dataset_support import decoded
from deykit.contracts.base import Record
from deykit.contracts.ports import StoredRecord

R = TypeVar("R", bound=Record)
_MAX_ENTRIES = 131_072
_MAX_BYTES = 64 * 1024 * 1024


class HistoryDecoder:
    def __init__(self) -> None:
        self._entries: OrderedDict[tuple[type[Record], StoredRecord], Record] = OrderedDict()
        self._bytes = 0
        self._mutex = RLock()

    def decode(self, kind: type[R], record: StoredRecord) -> R:
        with self._mutex:
            return self._decode(kind, record)

    def _decode(self, kind: type[R], record: StoredRecord) -> R:
        key = (kind, record)
        cached = self._entries.get(key)
        if cached is not None:
            self._entries.move_to_end(key)
            return cast(R, cached)
        value = decoded(kind, record)
        weight = len(record.body)
        if weight <= _MAX_BYTES:
            self._entries[key] = value
            self._bytes += weight
            while len(self._entries) > _MAX_ENTRIES or self._bytes > _MAX_BYTES:
                (_, removed), _ = self._entries.popitem(last=False)
                self._bytes -= len(removed.body)
        return value
