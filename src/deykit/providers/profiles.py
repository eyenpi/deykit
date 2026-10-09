"""Non-secret provider profiles over the authoritative project source port."""

from __future__ import annotations

from pydantic import ValidationError

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ErrorCode, ServiceError
from deykit.contracts.identities import validate_resource_id
from deykit.contracts.json_value import JsonError, bytes_hash, semantic_hash
from deykit.contracts.ports import (
    CommitReceipt,
    ProjectSource,
    ResourceKey,
    SourceChange,
    StoredRecord,
)
from deykit.contracts.provider_configuration import ProfilePage as ProfilePage
from deykit.contracts.provider_configuration import ProfileView as ProfileView
from deykit.contracts.records import ProviderProfile
from deykit.providers.credentials import CredentialReference
from deykit.providers.fixtures import FixtureInvalid, validate_fixture_profile
from deykit.providers.jev import validate_profile


def _fail(code: ErrorCode, reason: str, resource_id: str | None = None) -> ServiceFailure:
    return ServiceFailure(ServiceError(code=code, reason=reason, resource_id=resource_id))


def _id(value: str) -> str:
    try:
        validate_resource_id(value)
        return value
    except (TypeError, ValueError):
        raise _fail("validation_error", "invalid_profile_id") from None


def validate_provider_profile(profile: ProviderProfile) -> ProviderProfile:
    """One adapter dispatcher shared by CLI and execution, with no credential resolution."""
    try:
        if type(profile) is not ProviderProfile:
            raise ValueError
        candidate = ProviderProfile.model_validate(profile.model_dump(mode="python"))
        if candidate.adapter == "jev":
            return validate_profile(candidate)
        if candidate.adapter == "fixture":
            validate_fixture_profile(candidate)
            return candidate
    except (AttributeError, TypeError, ValueError, ValidationError, FixtureInvalid):
        pass
    raise _fail("validation_error", "invalid_provider_profile") from None


def _view(stored: StoredRecord) -> ProfileView:
    try:
        profile = load_record(ProviderProfile, stored.body)
        if profile.id != stored.key.resource_id:
            raise ValueError
        return ProfileView(validate_provider_profile(profile), stored.etag)
    except (JsonError, ValueError, ServiceFailure):
        raise _fail("validation_error", "invalid_stored_profile", stored.key.resource_id) from None


def _required(source: ProjectSource, profile_id: str) -> StoredRecord:
    stored = source.read(ResourceKey("providers", profile_id))
    if stored is None:
        raise _fail("not_found", "provider_profile_missing", profile_id)
    return stored


def _intent(profile: ProviderProfile, expected_etag: str | None) -> str:
    return semantic_hash(
        {
            "command": "provider.configure",
            "profile_id": profile.id,
            "body_hash": bytes_hash(dump_record(profile)),
            "expected_etag": expected_etag,
        }
    )


def _credential_intent(profile_id: str, reference: str | None, expected_etag: str) -> str:
    if reference is not None:
        try:
            CredentialReference.parse(reference)
        except ValueError:
            raise _fail("validation_error", "invalid_credential_reference") from None
    return semantic_hash(
        {
            "command": "provider.credential_ref",
            "profile_id": _id(profile_id),
            "reference": reference,
            "expected_etag": expected_etag,
        }
    )


class ProviderProfiles:
    """Configuration operations deliberately have no transport or credential dependency."""

    def __init__(self, source: ProjectSource) -> None:
        self._source = source

    def view(self, profile_id: str) -> ProfileView:
        key = ResourceKey("providers", _id(profile_id))
        with self._source.consistent_read() as source:
            return _view(_required(source, key.resource_id))

    def read(self, profile_id: str) -> ProviderProfile:
        return self.view(profile_id).profile

    def list_views(self, *, cursor: str | None = None, limit: int = 50) -> ProfilePage:
        if type(limit) is not int or not 1 <= limit <= 500:
            raise _fail("validation_error", "invalid_limit")
        if cursor is not None:
            _id(cursor)
        with self._source.consistent_read() as source:
            ids = source.list_ids("providers")
            views = tuple(_view(_required(source, item)) for item in ids)
        ordered = tuple(sorted(views, key=lambda value: value.profile.id))
        selected = tuple(value for value in ordered if cursor is None or value.profile.id > cursor)
        page = selected[:limit]
        next_cursor = page[-1].profile.id if len(selected) > limit else None
        return ProfilePage(page, len(ordered), next_cursor)

    def list(self) -> tuple[ProviderProfile, ...]:
        with self._source.consistent_read() as source:
            return tuple(
                _view(_required(source, profile_id)).profile
                for profile_id in source.list_ids("providers")
            )

    @staticmethod
    def from_receipt(receipt: CommitReceipt) -> ProfileView:
        if len(receipt.changes) != 1 or receipt.changes[0].key.collection != "providers":
            raise _fail("internal_error", "invalid_profile_receipt")
        return _view(receipt.changes[0])

    def replay(
        self, profile: ProviderProfile, *, expected_etag: str | None, operation_id: str
    ) -> CommitReceipt | None:
        _id(operation_id)
        profile = validate_provider_profile(profile)
        with self._source.consistent_read() as source:
            return source.operation_receipt(
                operation_id, intent_hash=_intent(profile, expected_etag)
            )

    def credential_replay(
        self,
        profile_id: str,
        reference: str | None,
        *,
        expected_etag: str,
        operation_id: str,
    ) -> CommitReceipt | None:
        _id(operation_id)
        digest = _credential_intent(profile_id, reference, expected_etag)
        with self._source.consistent_read() as source:
            return source.operation_receipt(operation_id, intent_hash=digest)

    def set_credential_ref(
        self,
        profile_id: str,
        reference: str | None,
        *,
        expected_etag: str,
        operation_id: str,
    ) -> CommitReceipt:
        _id(operation_id)
        digest = _credential_intent(profile_id, reference, expected_etag)
        with self._source.consistent_read() as source:
            replay = source.operation_receipt(operation_id, intent_hash=digest)
            if replay is not None:
                return replay
            current = _view(_required(source, _id(profile_id)))
            if current.etag != expected_etag:
                raise _fail("conflict", "provider_profile_changed", profile_id)
            if current.profile.adapter != "jev":
                raise _fail("validation_error", "fixture_has_no_credential", profile_id)
            candidate = validate_provider_profile(
                current.profile.model_copy(update={"credential_ref": reference})
            )
            return source.commit(
                operation_id,
                (
                    SourceChange(
                        ResourceKey("providers", profile_id), dump_record(candidate), expected_etag
                    ),
                ),
                intent_hash=digest,
            )

    def configure(
        self,
        profile: ProviderProfile,
        *,
        expected_etag: str | None,
        operation_id: str,
    ) -> CommitReceipt:
        _id(operation_id)
        profile = validate_provider_profile(profile)
        body = dump_record(profile)
        intent = _intent(profile, expected_etag)
        with self._source.consistent_read() as source:
            replay = source.operation_receipt(operation_id, intent_hash=intent)
            if replay is not None:
                return replay
            return source.commit(
                operation_id,
                (SourceChange(ResourceKey("providers", profile.id), body, expected_etag),),
                intent_hash=intent,
            )
