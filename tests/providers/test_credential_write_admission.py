"""Credential writes happen only after durable profile admission in one source epoch."""

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import pytest

from deykit.api.runtime import SystemClock
from deykit.application.errors import ServiceFailure
from deykit.application.projects import ProjectService
from deykit.application.provider_operations import ProviderOperations
from deykit.contracts.errors import ServiceError
from deykit.contracts.provider_configuration import CredentialReference, CredentialUnavailable
from deykit.contracts.records import ProviderProfile
from deykit.providers.choice import JEV_DESTINATION
from deykit.providers.profiles import ProviderProfiles
from deykit.storage import FileProjectSource


class References:
    def validate(self, reference: str) -> CredentialReference:
        return CredentialReference.parse(reference)

    def environment(self, name: str) -> str:
        return CredentialReference.parse(f"env:{name}").encode()

    def os_store(self, profile_id: str) -> str:
        return CredentialReference("keyring", "deykit", profile_id).encode()


class Descriptor:
    def describe(self, profile: ProviderProfile):
        from deykit.contracts.provider_configuration import CompilerInfo, ProviderCapabilities

        return (
            CompilerInfo("jev-choice", "1"),
            ProviderCapabilities(("text", "json"), "choice", 255, "live"),
        )


class MemoryCredentials:
    def __init__(self, action: Callable[..., None] | None = None) -> None:
        self.action = action
        self.calls: list[tuple[str, str, str | None]] = []
        self.factory_calls = 0

    def status(self, reference: str) -> bool:
        return False

    def set(self, reference: str, value: str) -> None:
        self.calls.append(("set", reference, value))
        if self.action is not None:
            self.action(reference, value)

    def forget(self, reference: str) -> None:
        self.calls.append(("forget", reference, None))
        if self.action is not None:
            self.action(reference)


def live_profile(reference: str | None = None) -> ProviderProfile:
    return ProviderProfile(
        id="profile",
        adapter="jev",
        requested_model="jev-1.13.0",
        destination=JEV_DESTINATION,
        credential_ref=reference,
    )


def setup(
    tmp_path: Path,
    *,
    profile: ProviderProfile | None = None,
    store: MemoryCredentials | Callable[[], MemoryCredentials] | None = None,
):
    source = FileProjectSource(tmp_path / "project", create=True)
    ProjectService(lambda _path, _create: source, SystemClock(), lambda: "project-id").create_in(
        source, "Credential admission tests", "create-project"
    )
    writer = ProviderProfiles(source)
    receipt = writer.configure(
        profile or live_profile(), expected_etag=None, operation_id="configure-profile"
    )
    if store is None:
        store_factory = MemoryCredentials
    elif isinstance(store, MemoryCredentials):

        def store_factory() -> MemoryCredentials:
            store.factory_calls += 1
            return store

    else:
        store_factory = store
    service = ProviderOperations(
        reader=writer,
        writer=writer,
        credentials_factory=lambda _profile: MemoryCredentials(),
        os_credentials_factory=store_factory,
        references=References(),
        descriptor=Descriptor(),
        models=None,
    )
    return source, writer, service, receipt.changes[0].etag


def assert_unknown(failure: ServiceFailure) -> None:
    assert failure.error.code == "internal_error"
    assert failure.error.reason == "credential_update_outcome_unknown"
    assert failure.error.resource_id == "profile"


def assert_secret_absent_from_project(source: FileProjectSource) -> None:
    assert not any(
        b"SECRET_SENTINEL" in path.read_bytes() for path in source.root.rglob("*") if path.is_file()
    )


def test_stale_etag_skips_secret_and_store_factories(tmp_path: Path) -> None:
    factory_calls: list[str] = []

    def store_factory():
        factory_calls.append("open")
        return MemoryCredentials()

    source, writer, service, _ = setup(tmp_path, store=store_factory)
    factories: list[str] = []

    with pytest.raises(ServiceFailure) as failure:
        service.set_os_credential(
            "profile",
            value_factory=lambda: factories.append("value") or "SECRET_SENTINEL",
            expected_etag="stale",
            operation_id="set-stale",
        )

    assert failure.value.error.reason == "provider_profile_changed"
    assert factories == []
    assert factory_calls == []
    assert writer.view("profile").profile.credential_ref is None
    assert (
        writer.credential_replay(
            "profile",
            "keyring:deykit/profile",
            expected_etag="stale",
            operation_id="set-stale",
        )
        is None
    )
    source.close()


def test_receipt_replay_after_profile_edit_skips_value_and_store_factories(
    tmp_path: Path,
) -> None:
    store = MemoryCredentials()
    source, writer, service, original_etag = setup(tmp_path, store=store)
    values: list[str] = []

    first = service.set_os_credential(
        "profile",
        value_factory=lambda: values.append("read") or "SECRET_SENTINEL",
        expected_etag=original_etag,
        operation_id="set-once",
    )
    edited = writer.view("profile")
    writer.configure(
        edited.profile.model_copy(update={"requested_model": "jev-1.14.0"}),
        expected_etag=edited.etag,
        operation_id="edit-after-set",
    )
    replay = service.set_os_credential(
        "profile",
        value_factory=lambda: pytest.fail("receipt replay must not read the secret"),
        expected_etag=original_etag,
        operation_id="set-once",
    )

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.profile.view.profile.credential_ref == "keyring:deykit/profile"
    assert values == ["read"]
    assert store.factory_calls == 1
    assert store.calls == [("set", "keyring:deykit/profile", "SECRET_SENTINEL")]
    source.close()


def test_forget_receipt_replay_after_profile_edit_skips_store_factory(tmp_path: Path) -> None:
    store = MemoryCredentials()
    source, writer, service, original_etag = setup(
        tmp_path, profile=live_profile("keyring:deykit/profile"), store=store
    )
    first = service.forget_credential(
        "profile", expected_etag=original_etag, operation_id="forget-once"
    )
    edited = writer.view("profile")
    writer.configure(
        edited.profile.model_copy(update={"requested_model": "jev-1.14.0"}),
        expected_etag=edited.etag,
        operation_id="edit-after-forget",
    )
    replay = service.forget_credential(
        "profile", expected_etag=original_etag, operation_id="forget-once"
    )

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.profile.view.profile.credential_ref is None
    assert store.factory_calls == 1
    assert store.calls == [("forget", "keyring:deykit/profile", None)]
    source.close()


def test_forget_store_factory_failure_is_safe_before_external_action(tmp_path: Path) -> None:
    factory_calls: list[str] = []

    def unavailable_factory():
        factory_calls.append("open")
        raise CredentialUnavailable()

    source, writer, service, etag = setup(
        tmp_path,
        profile=live_profile("keyring:deykit/profile"),
        store=unavailable_factory,
    )
    with pytest.raises(ServiceFailure) as failure:
        service.forget_credential("profile", expected_etag=etag, operation_id="forget-unavailable")

    assert failure.value.error.code == "preflight_failed"
    assert failure.value.error.reason == "credential_store_unavailable"
    assert factory_calls == ["open"]
    assert writer.view("profile").profile.credential_ref == "keyring:deykit/profile"
    assert (
        writer.credential_replay(
            "profile", None, expected_etag=etag, operation_id="forget-unavailable"
        )
        is None
    )
    source.close()


def test_mutate_then_raise_is_unknown_and_never_retried(tmp_path: Path) -> None:
    stored: dict[str, str] = {}

    def mutate_then_fail(reference: str, value: str) -> None:
        stored[reference] = value
        raise CredentialUnavailable()

    store = MemoryCredentials(mutate_then_fail)
    source, writer, service, etag = setup(tmp_path, store=store)
    with pytest.raises(ServiceFailure) as failure:
        service.set_os_credential(
            "profile",
            value_factory=lambda: "SECRET_SENTINEL",
            expected_etag=etag,
            operation_id="set-unknown",
        )

    assert_unknown(failure.value)
    assert "SECRET_SENTINEL" not in repr(failure.value.error.safe_dict())
    assert store.calls == [("set", "keyring:deykit/profile", "SECRET_SENTINEL")]
    assert stored == {"keyring:deykit/profile": "SECRET_SENTINEL"}
    assert store.factory_calls == 1
    assert_secret_absent_from_project(source)
    assert writer.view("profile").profile.credential_ref is None
    assert (
        writer.credential_replay(
            "profile",
            "keyring:deykit/profile",
            expected_etag=etag,
            operation_id="set-unknown",
        )
        is None
    )
    source.close()


@pytest.mark.parametrize("action", ["set", "forget"])
@pytest.mark.parametrize("durable_before_error", [False, True])
def test_commit_failure_is_unknown_and_exact_replay_controls_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    durable_before_error: bool,
) -> None:
    store = MemoryCredentials()
    reference = "keyring:deykit/profile" if action == "forget" else None
    source, writer, service, etag = setup(tmp_path, profile=live_profile(reference), store=store)
    commit = source.commit
    operation_id = f"{action}-commit-failure"

    def fail_commit(operation_id, changes, *, intent_hash=None):
        if durable_before_error:
            commit(operation_id, changes, intent_hash=intent_hash)
        raise OSError("SECRET_SENTINEL from source adapter")

    def perform(*, replay: bool = False):
        if action == "set":
            value_factory = (
                (lambda: pytest.fail("durable receipt replay must skip the secret"))
                if replay
                else (lambda: "SECRET_SENTINEL")
            )
            return service.set_os_credential(
                "profile",
                value_factory=value_factory,
                expected_etag=etag,
                operation_id=operation_id,
            )
        return service.forget_credential("profile", expected_etag=etag, operation_id=operation_id)

    monkeypatch.setattr(source, "commit", fail_commit)
    with pytest.raises(ServiceFailure) as failure:
        perform()

    assert_unknown(failure.value)
    assert "SECRET_SENTINEL" not in repr(failure.value.error.safe_dict())
    assert_secret_absent_from_project(source)
    assert len(store.calls) == 1
    assert store.factory_calls == 1
    monkeypatch.setattr(source, "commit", commit)
    if durable_before_error:
        replay = perform(replay=True)
        assert replay.replayed is True
        assert len(store.calls) == 1
        assert store.factory_calls == 1
    else:
        perform()
        assert len(store.calls) == 2
        assert store.factory_calls == 2
    source.close()


@pytest.mark.parametrize("action", ["set", "forget"])
@pytest.mark.parametrize(
    ("code", "reason"),
    [("conflict", "casefold_collision"), ("validation_error", "invalid_source_path")],
)
def test_posthook_source_admission_errors_are_unknown_for_both_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    code: Literal["conflict", "validation_error"],
    reason: Literal["casefold_collision", "invalid_source_path"],
) -> None:
    store = MemoryCredentials()
    reference = "keyring:deykit/profile" if action == "forget" else None
    source, writer, service, etag = setup(tmp_path, profile=live_profile(reference), store=store)
    admitted_source = source.capture_snapshot()
    operation_id = f"{action}-posthook-{reason}"

    def reject_after_external_action(_operation_id, _changes, *, intent_hash=None):
        del intent_hash
        raise ServiceFailure(ServiceError(code=code, reason=reason))

    monkeypatch.setattr(source, "commit", reject_after_external_action)
    with pytest.raises(ServiceFailure) as failure:
        if action == "set":
            service.set_os_credential(
                "profile",
                value_factory=lambda: "SECRET_SENTINEL",
                expected_etag=etag,
                operation_id=operation_id,
            )
        else:
            service.forget_credential("profile", expected_etag=etag, operation_id=operation_id)

    assert_unknown(failure.value)
    assert "SECRET_SENTINEL" not in repr(failure.value.error.safe_dict())
    assert len(store.calls) == 1
    assert store.factory_calls == 1
    assert source.capture_snapshot() == admitted_source
    assert writer.view("profile").profile.credential_ref == reference
    receipt_reference = "keyring:deykit/profile" if action == "set" else None
    assert (
        writer.credential_replay(
            "profile",
            receipt_reference,
            expected_etag=etag,
            operation_id=operation_id,
        )
        is None
    )
    assert_secret_absent_from_project(source)
    source.close()


@pytest.mark.parametrize("action", ["set", "forget"])
def test_credential_action_and_competing_project_edit_share_one_source_epoch(
    tmp_path: Path, action: str
) -> None:
    reference = "keyring:deykit/profile" if action == "forget" else None
    entered = threading.Event()
    release = threading.Event()

    def hold(_reference: str, _value: str | None = None) -> None:
        entered.set()
        assert release.wait(3), "test action was not released"

    store = MemoryCredentials(hold)
    source, writer, service, etag = setup(tmp_path, profile=live_profile(reference), store=store)
    second_source = FileProjectSource(source.root)
    competing_writer = ProviderProfiles(second_source)
    errors: list[Exception] = []

    def mutate() -> None:
        try:
            if action == "set":
                service.set_os_credential(
                    "profile",
                    value_factory=lambda: "SECRET_SENTINEL",
                    expected_etag=etag,
                    operation_id="held-set",
                )
            else:
                service.forget_credential("profile", expected_etag=etag, operation_id="held-forget")
        except Exception as error:
            errors.append(error)

    worker = threading.Thread(target=mutate)
    worker.start()
    assert entered.wait(3), "credential mutation did not enter its admitted action"
    changed = live_profile(reference).model_copy(update={"requested_model": "jev-1.14.0"})
    competing_done = threading.Event()
    competing_errors: list[Exception] = []

    def compete() -> None:
        try:
            competing_writer.configure(changed, expected_etag=etag, operation_id="competing-edit")
        except Exception as error:
            competing_errors.append(error)
        finally:
            competing_done.set()

    competing = threading.Thread(target=compete)
    competing.start()
    finished_while_held = competing_done.wait(1)
    if not finished_while_held:
        release.set()
        worker.join(3)
        competing.join(3)
        pytest.fail("a competing source edit waited for the credential action to finish")
    assert len(competing_errors) == 1
    assert isinstance(competing_errors[0], ServiceFailure)
    failure = competing_errors[0]
    assert failure.error.reason == "source_busy"

    release.set()
    worker.join(3)
    competing.join(3)
    assert not worker.is_alive()
    assert not competing.is_alive()
    assert errors == []
    current = competing_writer.view("profile")
    competing_writer.configure(
        current.profile.model_copy(update={"requested_model": "jev-1.14.0"}),
        expected_etag=current.etag,
        operation_id="competing-edit-after-release",
    )
    assert len(store.calls) == 1
    assert store.factory_calls == 1
    source.close()
    second_source.close()
