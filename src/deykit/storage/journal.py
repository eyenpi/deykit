"""Private durable transaction records, strictly versioned like public source records."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

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
    sequence: Annotated[int, Field(gt=0)]
    entries: Annotated[tuple[JournalEntry, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_entries(self) -> Self:
        if len({entry.key for entry in self.entries}) != len(self.entries):
            raise ValueError("duplicate_journal_key")
        return self


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
