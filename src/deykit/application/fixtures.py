"""Immutable authored fixture sets over the portable project source."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from pydantic import ValidationError

from deykit.application.dataset_support import page
from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ErrorCode, ServiceError
from deykit.contracts.identities import validate_resource_id
from deykit.contracts.json_value import (
    JsonError,
    JsonValue,
    bytes_hash,
    dump_json,
    parse_json,
    semantic_hash,
)
from deykit.contracts.ports import (
    Clock,
    Collection,
    ProjectSource,
    ResourceKey,
    SourceChange,
    StoredRecord,
)
from deykit.contracts.records import FixtureBinding, FixtureSet, ProviderProfile
from deykit.contracts.redaction import Sanitizer
from deykit.providers.fixtures import (
    FIXTURE_DESTINATION,
    FixtureInvalid,
    FixtureTransportFactory,
    fixture_set_hash,
    validate_fixture_profile,
    validate_fixture_set,
)


@dataclass(frozen=True)
class StoredFixtureSet:
    fixture_set: FixtureSet
    etag: str
    replayed: bool = field(default=False, compare=False)


@dataclass(frozen=True)
class FixtureBindingSummary:
    id: str
    case_id: str
    compiler: str
    compiler_version: str
    model_identity: str
    request_hash: str
    answer_question_id: str | None
    answer_option_id: str | None
    error_code: str | None
    error_reason: str | None


@dataclass(frozen=True)
class FixtureSummary:
    id: str
    decision_id: str
    dataset_id: str
    name: str
    model_identity: str
    binding_count: int
    created_at: str
    content_hash: str
    bindings: tuple[FixtureBindingSummary, ...]
    requests: tuple[str, ...] = ()


@dataclass(frozen=True)
class FixturePage:
    items: tuple[FixtureSummary, ...]
    total: int
    next_cursor: str | None


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


def _decoded(stored: StoredRecord, *, replayed: bool = False) -> StoredFixtureSet:
    try:
        fixture_set = load_record(FixtureSet, stored.body)
        validate_fixture_set(fixture_set)
    except (JsonError, FixtureInvalid) as error:
        reason = error.code if isinstance(error, JsonError) else error.reason
        raise _fail("validation_error", reason, stored.key.resource_id) from None
    return StoredFixtureSet(fixture_set, stored.etag, replayed)


class FixtureService:
    def __init__(
        self, source: ProjectSource, clock: Clock, sanitizer: Sanitizer | None = None
    ) -> None:
        self.source = source
        self.clock = clock
        self.sanitizer = sanitizer or Sanitizer()

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
        if type(binding_sources) is not tuple or not binding_sources:
            raise _fail("validation_error", "invalid_binding_sources") from None
        if any(type(value) not in (str, bytes) for value in binding_sources):
            raise _fail("validation_error", "invalid_binding_source") from None
        if any(type(value) is not str for value in (name, model_identity, note)):
            raise _fail("validation_error", "invalid_fixture_metadata") from None
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
            return _decoded(replay.changes[0], replayed=True)
        with self.source.consistent_read() as source:
            replay = source.operation_receipt(operation_id, intent_hash=intent)
            if replay is not None:
                return _decoded(replay.changes[0], replayed=True)
            for collection, resource_id in (("decisions", decision_id), ("datasets", dataset_id)):
                if source.read(ResourceKey(cast(Collection, collection), resource_id)) is None:
                    raise _fail("not_found", "fixture_context_missing", resource_id)
            try:
                parsed_bindings: list[FixtureBinding] = []
                for row, body in enumerate(bodies, start=1):
                    try:
                        parsed_bindings.append(load_record(FixtureBinding, body))
                    except (JsonError, ValidationError) as error:
                        raise ServiceFailure(
                            ServiceError(
                                code="validation_error",
                                reason=(
                                    error.code
                                    if isinstance(error, JsonError)
                                    else "invalid_fixture_binding"
                                ),
                                resource_id=fixture_set_id,
                                row=row,
                            )
                        ) from None
                bindings = tuple(parsed_bindings)
                for row, binding in enumerate(bindings, start=1):
                    if source.read(ResourceKey("cases", binding.case_id, (dataset_id,))) is None:
                        raise ServiceFailure(
                            ServiceError(
                                code="not_found",
                                reason="fixture_case_missing",
                                resource_id=binding.case_id,
                                row=row,
                            )
                        ) from None
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
            return _decoded(receipt.changes[0], replayed=receipt.replayed)

    def read(self, fixture_set_id: str) -> StoredFixtureSet:
        key = ResourceKey("fixtures", _id(fixture_set_id))
        with self.source.consistent_read() as source:
            stored = source.read(key)
            if stored is None:
                raise _fail("not_found", "fixture_set_missing", fixture_set_id)
            return _decoded(stored)

    def read_summary(
        self, fixture_set_id: str, *, include_requests: bool = False
    ) -> FixtureSummary:
        return self.identity_summary(
            self.read(fixture_set_id),
            include_requests=include_requests,
            sanitizer=self.sanitizer,
        )

    def list(self, *, cursor: str | None = None, limit: int = 50) -> FixturePage:
        if type(limit) is not int or not 1 <= limit <= 500:
            raise _fail("validation_error", "invalid_page_limit")
        if cursor is not None:
            cursor = _id(cursor)
        with self.source.consistent_read() as source:
            all_ids = tuple(sorted(source.list_ids("fixtures")))
            selected, next_cursor = page(all_ids, cursor, limit)
            items: list[FixtureSummary] = []
            for fixture_set_id in selected:
                stored = source.read(ResourceKey("fixtures", fixture_set_id))
                if stored is None:
                    raise _fail("not_found", "fixture_set_missing", fixture_set_id)
                items.append(self.identity_summary(_decoded(stored), sanitizer=self.sanitizer))
            return FixturePage(tuple(items), len(all_ids), next_cursor)

    @staticmethod
    def identity_summary(
        stored: StoredFixtureSet,
        *,
        include_requests: bool = False,
        sanitizer: Sanitizer | None = None,
    ) -> FixtureSummary:
        fixture_set = stored.fixture_set
        safe = sanitizer or Sanitizer()
        bindings = tuple(
            FixtureBindingSummary(
                id=binding.id,
                case_id=binding.case_id,
                compiler=safe.text(binding.request.compiler),
                compiler_version=safe.text(binding.request.compiler_version),
                model_identity=safe.text(binding.request.requested_model),
                request_hash=binding.request.body_hash,
                answer_question_id=binding.answer.question_id if binding.answer else None,
                answer_option_id=binding.answer.option_id if binding.answer else None,
                error_code=binding.error.code if binding.error else None,
                error_reason=(
                    safe.text(binding.error.reason)
                    if binding.error is not None and binding.error.reason is not None
                    else None
                ),
            )
            for binding in fixture_set.bindings
        )
        requests = (
            tuple(
                _project_request_source(binding.request.body.decode("utf-8"), safe)
                for binding in fixture_set.bindings
            )
            if include_requests
            else ()
        )
        return FixtureSummary(
            id=fixture_set.id,
            decision_id=fixture_set.decision_id,
            dataset_id=fixture_set.dataset_id,
            name=safe.text(fixture_set.name),
            model_identity=safe.text(fixture_set.model_identity),
            binding_count=len(bindings),
            created_at=fixture_set.created_at,
            content_hash=fixture_set.content_hash,
            bindings=bindings,
            requests=requests,
        )

    def list_ids(self) -> tuple[str, ...]:
        with self.source.consistent_read() as source:
            return source.list_ids("fixtures")

    def create_profile(
        self, profile_id: str, model_identity: str, *, operation_id: str
    ) -> ProviderProfile:
        profile_id, operation_id = _id(profile_id), _id(operation_id)
        if type(model_identity) is not str:
            raise _fail("validation_error", "invalid_fixture_profile") from None
        try:
            intent = semantic_hash(
                {
                    "command": "fixture.create_profile",
                    "profile_id": profile_id,
                    "model_hash": bytes_hash(model_identity.encode("utf-8")),
                }
            )
        except (AttributeError, UnicodeEncodeError):
            raise _fail("validation_error", "invalid_fixture_profile") from None
        with self.source.consistent_read() as source:
            replay = source.operation_receipt(operation_id, intent_hash=intent)
            if replay is not None:
                return self._profile_from_receipt(replay.changes[0])
            try:
                profile = ProviderProfile(
                    id=profile_id,
                    adapter="fixture",
                    requested_model=model_identity,
                    destination=FIXTURE_DESTINATION,
                )
                validate_fixture_profile(profile)
                body = dump_record(profile)
            except (ValidationError, FixtureInvalid, JsonError):
                raise _fail("validation_error", "invalid_fixture_profile", profile_id) from None
            receipt = source.commit(
                operation_id,
                (SourceChange(ResourceKey("providers", profile_id), body, None),),
                intent_hash=intent,
            )
            return self._profile_from_receipt(receipt.changes[0])

    @staticmethod
    def _profile_from_receipt(stored: StoredRecord) -> ProviderProfile:
        try:
            profile = load_record(ProviderProfile, stored.body)
            validate_fixture_profile(profile)
        except (JsonError, FixtureInvalid):
            raise _fail(
                "validation_error", "invalid_fixture_profile", stored.key.resource_id
            ) from None
        return profile

    def read_profile(self, profile_id: str) -> ProviderProfile:
        key = ResourceKey("providers", _id(profile_id))
        with self.source.consistent_read() as source:
            stored = source.read(key)
            if stored is None:
                raise _fail("not_found", "fixture_profile_missing", profile_id)
            return self._profile_from_receipt(stored)

    def transport_factory(
        self, fixture_set_id: str, *, profile_id: str | None = None
    ) -> FixtureTransportFactory:
        profile = self.read_profile(profile_id) if profile_id is not None else None
        try:
            return FixtureTransportFactory(self.read(fixture_set_id).fixture_set, profile)
        except FixtureInvalid as error:
            raise _fail("validation_error", error.reason, fixture_set_id) from None


def _project_request_source(source: str, sanitizer: Sanitizer) -> str:
    """Retain exact JSON text unless pure structured redaction changes its value."""
    value = parse_json(source)
    safe_value = sanitizer.value(value)
    if safe_value == value:
        return source
    return dump_json(cast(JsonValue, safe_value))
