"""Private durable transaction records, strictly versioned like public source records."""

from typing import Literal

from deykit.contracts.base import Record
from deykit.contracts.identities import ContentHash, ResourceId
from deykit.contracts.ports import Collection, ResourceKey


class JournalEntry(Record):
    collection: Collection
    resource_id: ResourceId
    scope: tuple[ResourceId, ...]
    old_hash: ContentHash | None
    new_hash: ContentHash | None

    @property
    def key(self) -> ResourceKey:
        return ResourceKey(self.collection, self.resource_id, self.scope)


class JournalManifest(Record):
    operation_id: ResourceId
    payload_hash: ContentHash
    intent_hash: ContentHash | None = None
    sequence: int
    entries: tuple[JournalEntry, ...]


class CommitDecision(Record):
    operation_id: ResourceId
    manifest_hash: ContentHash
    state: Literal["commit"] = "commit"


class Cancellation(Record):
    id: ResourceId
    run_id: ResourceId
    requested: Literal[True] = True


class CancellationAcknowledgement(Record):
    run_id: ResourceId
    segment_id: ResourceId
    request_ids: tuple[ResourceId, ...]
