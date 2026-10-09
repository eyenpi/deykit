import asyncio
from collections.abc import Callable

import pytest

from deykit.application.errors import ServiceFailure
from deykit.application.provider_operations import ProviderOperations
from deykit.contracts.codec import dump_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.ports import CommitReceipt
from deykit.contracts.provider_configuration import (
    CompilerInfo,
    CredentialReference,
    CredentialUnavailable,
    ModelDescription,
    ProfilePage,
    ProfileView,
    ProviderCapabilities,
)
from deykit.contracts.records import ProviderProfile
from deykit.providers.choice import JEV_DESTINATION
from deykit.providers.credentials import CredentialReference as LegacyCredentialReference
from deykit.providers.credentials import CredentialUnavailable as LegacyCredentialUnavailable
from deykit.providers.profiles import ProfilePage as LegacyProfilePage
from deykit.providers.profiles import ProfileView as LegacyProfileView
from deykit.providers.profiles import validate_provider_profile


class References:
    def validate(self, value: str) -> CredentialReference:
        return CredentialReference.parse(value)

    def environment(self, name: str) -> str:
        return CredentialReference.parse(f"env:{name}").encode()

    def os_store(self, profile_id: str) -> str:
        return CredentialReference("keyring", "deykit", profile_id).encode()


class Reader:
    def __init__(self, profile: ProviderProfile, etag: str = "old") -> None:
        self.profile = profile
        self.etag = etag

    def view(self, profile_id: str) -> ProfileView:
        assert profile_id == self.profile.id
        return ProfileView(self.profile, self.etag)

    def list_views(self, *, cursor: str | None = None, limit: int = 50) -> ProfilePage:
        assert cursor is None and limit == 50
        return ProfilePage((self.view(self.profile.id),), 1, None)


class Writer:
    def __init__(self, reader: Reader) -> None:
        self.reader = reader
        self.replay: CommitReceipt | None = None
        self.set_calls: list[tuple[str, str | None, str, str]] = []

    def credential_replay(self, profile_id, reference, *, expected_etag, operation_id):
        return self.replay

    def set_credential_ref(
        self,
        profile_id,
        reference,
        *,
        expected_etag,
        operation_id,
        before_commit: Callable[[], None] | None = None,
    ):
        if self.replay is not None:
            return self.replay
        current = self.reader.view(profile_id)
        if current.etag != expected_etag:
            raise ServiceFailure(
                ServiceError(
                    code="conflict",
                    reason="provider_profile_changed",
                    resource_id=profile_id,
                )
            )
        if current.profile.adapter != "jev":
            raise ServiceFailure(
                ServiceError(
                    code="validation_error",
                    reason="fixture_has_no_credential",
                    resource_id=profile_id,
                )
            )
        candidate = validate_provider_profile(
            current.profile.model_copy(update={"credential_ref": reference})
        )
        dump_record(candidate)
        if before_commit is not None:
            before_commit()
        self.set_calls.append((profile_id, reference, expected_etag, operation_id))
        self.reader.profile = candidate
        self.reader.etag = "new"
        return CommitReceipt(operation_id, ())

    def from_receipt(self, receipt):
        return self.reader.view(self.reader.profile.id)

    def configure(self, profile, *, expected_etag, operation_id):
        raise AssertionError("configure is outside this test")


class Descriptor:
    def describe(self, profile):
        return (
            CompilerInfo("jev-choice", "1"),
            ProviderCapabilities(("text", "json"), "choice", 255, "live"),
        )


class Credentials:
    def status(self, reference: str) -> bool:
        return False

    def set(self, reference: str, value: str) -> None:
        raise AssertionError("credential mutation is outside this test")

    def forget(self, reference: str) -> None:
        raise AssertionError("credential mutation is outside this test")


def live_profile() -> ProviderProfile:
    return ProviderProfile(
        id="profile",
        adapter="jev",
        requested_model="jev-1.13.0",
        destination=JEV_DESTINATION,
    )


def operations(reader, writer, *, os_factory, credential_factory=None, model_lister=None):
    return ProviderOperations(
        reader=reader,
        writer=writer,
        credentials_factory=credential_factory or (lambda profile: Credentials()),
        os_credentials_factory=os_factory,
        references=References(),
        descriptor=Descriptor(),
        models=model_lister,
    )


def test_moved_provider_contracts_keep_legacy_import_identity():
    assert LegacyCredentialReference is CredentialReference
    assert LegacyCredentialUnavailable is CredentialUnavailable
    assert LegacyProfileView is ProfileView
    assert LegacyProfilePage is ProfilePage


def test_credential_replay_skips_secret_value_and_os_store_factories():
    reader = Reader(live_profile())
    writer = Writer(reader)
    writer.replay = CommitReceipt("op", (), replayed=True)
    service = operations(
        reader,
        writer,
        os_factory=lambda: pytest.fail("replay must not open the OS store"),
    )

    result = service.set_os_credential(
        "profile",
        value_factory=lambda: pytest.fail("replay must not read secret input"),
        expected_etag="old",
        operation_id="op",
    )

    assert result.replayed is True
    assert writer.set_calls == []


def test_stale_credential_etag_precedes_value_and_store_access():
    reader = Reader(live_profile(), etag="current")
    writer = Writer(reader)
    service = operations(
        reader,
        writer,
        os_factory=lambda: pytest.fail("stale ETag must not open the OS store"),
    )

    with pytest.raises(ServiceFailure) as failure:
        service.set_os_credential(
            "profile",
            value_factory=lambda: pytest.fail("stale ETag must not read secret input"),
            expected_etag="old",
            operation_id="op",
        )

    assert failure.value.error.code == "conflict"
    assert writer.set_calls == []


def test_environment_attachment_uses_neither_secret_input_nor_os_store():
    reader = Reader(live_profile())
    writer = Writer(reader)
    service = operations(
        reader,
        writer,
        os_factory=lambda: pytest.fail("environment attachment must not open OS store"),
    )

    result = service.attach_environment(
        "profile", "JEV_KEY", expected_etag="old", operation_id="attach"
    )

    assert result.profile.view.profile.credential_ref == "env:JEV_KEY"
    assert writer.set_calls == [("profile", "env:JEV_KEY", "old", "attach")]


def test_os_store_mutator_failure_has_unknown_outcome_and_leaves_profile_reference_unmodified():
    reader = Reader(live_profile())
    writer = Writer(reader)

    class Unavailable:
        def set(self, reference, value):
            raise CredentialUnavailable()

        def status(self, reference):
            return False

        def forget(self, reference):
            raise CredentialUnavailable()

    service = operations(reader, writer, os_factory=Unavailable)

    with pytest.raises(ServiceFailure) as failure:
        service.set_os_credential(
            "profile",
            value_factory=lambda: "SECRET_SENTINEL",
            expected_etag="old",
            operation_id="set",
        )

    assert failure.value.error.code == "internal_error"
    assert failure.value.error.reason == "credential_update_outcome_unknown"
    assert failure.value.error.resource_id == "profile"
    assert reader.profile.credential_ref is None
    assert writer.set_calls == []
    assert "SECRET_SENTINEL" not in str(failure.value)


def test_os_store_factory_failure_remains_safe_preflight_failure():
    reader = Reader(live_profile())
    writer = Writer(reader)
    factory_calls = []

    def unavailable_factory():
        factory_calls.append("open")
        raise CredentialUnavailable()

    service = operations(reader, writer, os_factory=unavailable_factory)

    with pytest.raises(ServiceFailure) as failure:
        service.set_os_credential(
            "profile",
            value_factory=lambda: "SECRET_SENTINEL",
            expected_etag="old",
            operation_id="set-store-unavailable",
        )

    assert failure.value.error.code == "preflight_failed"
    assert failure.value.error.reason == "credential_store_unavailable"
    assert failure.value.error.resource_id == "profile"
    assert factory_calls == ["open"]
    assert writer.set_calls == []
    assert reader.profile.credential_ref is None
    assert "SECRET_SENTINEL" not in str(failure.value)


def test_model_listing_uses_only_the_explicit_async_port():
    reader = Reader(live_profile())
    writer = Writer(reader)
    calls = []

    class Models:
        async def models(self, profile, *, timeout_seconds):
            calls.append((profile.id, timeout_seconds))
            return (ModelDescription("jev-1", "description", "2026-01-01"),)

    service = operations(
        reader,
        writer,
        os_factory=lambda: pytest.fail("fake model port owns this offline test"),
        model_lister=Models(),
    )

    result = asyncio.run(service.list_models("profile", timeout_seconds=12.5))

    assert result.network_check is True
    assert result.inference_calls == 0
    assert result.models[0].name == "jev-1"
    assert calls == [("profile", 12.5)]
