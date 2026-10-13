"""Bounded per-source memo for successful immutable-body validation."""

from __future__ import annotations

from collections import OrderedDict

from deykit.contracts.ports import ResourceKey
from deykit.storage.records import key_path, validate_body

_MAX_ENTRIES = 2048
_MAX_RETAINED_KEY_BYTES = 8 * 1024 * 1024


class _SuccessfulBodyValidationMemo:
    """Remember successful validation for exact keys and bytes only."""

    def __init__(self) -> None:
        self._entries: OrderedDict[tuple[ResourceKey, bytes], int] = OrderedDict()
        self._retained_key_bytes = 0

    def validate(self, key: ResourceKey, body: bytes) -> None:
        key_path(key)
        identity = (key, body)
        weight = self._entries.get(identity)
        if weight is not None:
            self._entries.move_to_end(identity)
            return

        validate_body(key, body)
        weight = (
            len(body)
            + sum(
                len(component.encode("utf-8"))
                for component in (key.collection, key.resource_id, *key.scope)
            )
            + 8 * (2 + len(key.scope))
        )
        if weight > _MAX_RETAINED_KEY_BYTES:
            return
        self._entries[identity] = weight
        self._retained_key_bytes += weight
        while (
            len(self._entries) > _MAX_ENTRIES or self._retained_key_bytes > _MAX_RETAINED_KEY_BYTES
        ):
            _, evicted_weight = self._entries.popitem(last=False)
            self._retained_key_bytes -= evicted_weight

    def clear(self) -> None:
        self._entries.clear()
        self._retained_key_bytes = 0
