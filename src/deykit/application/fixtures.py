"""Immutable authored fixture sets over the portable project source."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from pydantic import ValidationError

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ErrorCode, ServiceError
from deykit.contracts.identities import validate_resource_id
from deykit.contracts.json_value import JsonError, bytes_hash, semantic_hash
from deykit.contracts.ports import (
    Clock,
    Collection,
    ProjectSource,
    ResourceKey,
    SourceChange,
    StoredRecord,
)
from deykit.contracts.records import FixtureBinding, FixtureSet
from deykit.providers.fixtures import (
    FixtureInvalid,
    FixtureTransportFactory,
    fixture_set_hash,
    validate_fixture_set,
)


@dataclass(frozen=True)
class StoredFixtureSet:
    fixture_set: FixtureSet
    etag: str


def _fail(code: ErrorCode, reason: str, resource_id: str | None = None) -> ServiceFailure:
    return ServiceFailure(ServiceError(code=code, reason=reason, resource_id=resource_id))


def _id(value: str) -> str:
    try:
        return validate_resource_id(value)
    except ValueError:
        raise _fail("validation_error", "invalid_resource_id") from None


def _source_bytes(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        return value
    try:
        return value.encode("utf-8")
    except (AttributeError, UnicodeEncodeError):
        raise _fail("validation_error", "invalid_binding_source") from None


def _decoded(stored: StoredRecord) -> StoredFixtureSet:
    try:
        fixture_set = load_record(FixtureSet, stored.body)
        validate_fixture_set(fixture_set)
    except (JsonError, FixtureInvalid) as error:
        reason = error.code if isinstance(error, JsonError) else error.reason
        raise _fail("validation_error", reason, stored.key.resource_id) from None
    return StoredFixtureSet(fixture_set, stored.etag)


class FixtureService:
    def __init__(self, source: ProjectSource, clock: Clock) -> None:
        self.source = source
        self.clock = clock

    def create(
        self,
        fixture_set_id: str,
        decision_id: str,
        dataset_id: str,
        name: str,
        model_identity: str,
        binding_sources: tuple[str | bytes, ...],
        *,
        operation_id: str,
        note: str = "",
    ) -> StoredFixtureSet:
        fixture_set_id, decision_id, dataset_id = (
            _id(fixture_set_id),
            _id(decision_id),
            _id(dataset_id),
        )
        _id(operation_id)
        bodies = tuple(_source_bytes(source) for source in binding_sources)
        try:
            intent = semantic_hash(
                {
                    "command": "fixture.create",
                    "fixture_set_id": fixture_set_id,
                    "decision_id": decision_id,
                    "dataset_id": dataset_id,
                    "name_hash": bytes_hash(name.encode("utf-8")),
                    "model_hash": bytes_hash(model_identity.encode("utf-8")),
                    "note_hash": bytes_hash(note.encode("utf-8")),
                    "bindings": [bytes_hash(body) for body in bodies],
                }
            )
        except (AttributeError, UnicodeEncodeError):
            raise _fail("validation_error", "invalid_fixture_metadata") from None
        replay = self.source.operation_receipt(operation_id, intent_hash=intent)
        if replay is not None:
            return _decoded(replay.changes[0])
        with self.source.consistent_read() as source:
            replay = source.operation_receipt(operation_id, intent_hash=intent)
            if replay is not None:
                return _decoded(replay.changes[0])
            for collection, resource_id in (("decisions", decision_id), ("datasets", dataset_id)):
                if source.read(ResourceKey(cast(Collection, collection), resource_id)) is None:
                    raise _fail("not_found", "fixture_context_missing", resource_id)
            try:
                bindings = tuple(load_record(FixtureBinding, body) for body in bodies)
                for binding in bindings:
                    if source.read(ResourceKey("cases", binding.case_id, (dataset_id,))) is None:
                        raise _fail("not_found", "fixture_case_missing", binding.case_id)
                timestamp = self.clock.utc_now()

                def build(content_hash: str) -> FixtureSet:
                    return FixtureSet(
                        id=fixture_set_id,
                        decision_id=decision_id,
                        dataset_id=dataset_id,
                        name=name,
                        model_identity=model_identity,
                        bindings=bindings,
                        created_at=timestamp,
                        note=note,
                        content_hash=content_hash,
                    )

                fixture_set = build(fixture_set_hash(build("0" * 64)))
                validate_fixture_set(fixture_set)
                body = dump_record(fixture_set)
            except (JsonError, ValidationError, FixtureInvalid) as error:
                reason = (
                    error.code
                    if isinstance(error, JsonError)
                    else (
                        error.reason if isinstance(error, FixtureInvalid) else "invalid_fixture_set"
                    )
                )
                raise _fail("validation_error", reason, fixture_set_id) from None
            receipt = source.commit(
                operation_id,
                (SourceChange(ResourceKey("fixtures", fixture_set_id), body, None),),
                intent_hash=intent,
            )
            return _decoded(receipt.changes[0])

    def read(self, fixture_set_id: str) -> StoredFixtureSet:
        key = ResourceKey("fixtures", _id(fixture_set_id))
        with self.source.consistent_read() as source:
            stored = source.read(key)
            if stored is None:
                raise _fail("not_found", "fixture_set_missing", fixture_set_id)
            return _decoded(stored)

    def list_ids(self) -> tuple[str, ...]:
        with self.source.consistent_read() as source:
            return source.list_ids("fixtures")

    def transport_factory(self, fixture_set_id: str) -> FixtureTransportFactory:
        return FixtureTransportFactory(self.read(fixture_set_id).fixture_set)
