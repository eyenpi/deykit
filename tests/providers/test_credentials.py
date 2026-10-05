import pytest

from deykit.contracts.records import ProviderProfile
from deykit.providers.choice import JEV_DESTINATION
from deykit.providers.credentials import (
    CredentialReference,
    Credentials,
    CredentialUnavailable,
    credentials_for,
)


class MemoryStore:
    def __init__(self):
        self.values = {}

    def get_password(self, service, username):
        return self.values.get((service, username))

    def set_password(self, service, username, password):
        self.values[(service, username)] = password

    def delete_password(self, service, username):
        self.values.pop((service, username), None)


def test_environment_resolution_and_status_are_local():
    credentials = Credentials({"JEV_TEST_KEY": "SENTINEL"})
    assert credentials.resolve("env:JEV_TEST_KEY") == "SENTINEL"
    assert credentials.status("env:MISSING") is False
    assert "SENTINEL" not in repr(credentials)
    with pytest.raises(ValueError):
        credentials.set("env:JEV_TEST_KEY", "replacement")


def test_keyring_operations_use_injected_store_only():
    store = MemoryStore()
    credentials = Credentials({}, store)
    ref = "keyring:deykit/test-user"
    assert credentials.status(ref) is False
    credentials.set(ref, "SENTINEL")
    assert credentials.resolve(ref) == "SENTINEL"
    credentials.forget(ref)
    assert credentials.status(ref) is False
    assert CredentialReference.parse(ref).encode() == ref


@pytest.mark.parametrize("reference", ["SENTINEL", "env:", "env:BAD NAME", "keyring:a/b/c"])
def test_invalid_references_never_echo_input(reference):
    with pytest.raises(ValueError) as failure:
        CredentialReference.parse(reference)
    assert reference not in str(failure.value) or reference == "env:"


def test_store_exception_and_invalid_header_secret_are_sanitized():
    class Broken(MemoryStore):
        def get_password(self, service, username):
            raise RuntimeError("SECRET_SENTINEL")

    with pytest.raises(CredentialUnavailable) as failure:
        Credentials({}, Broken()).resolve("keyring:deykit/user")
    assert "SECRET_SENTINEL" not in str(failure.value)
    assert failure.value.__suppress_context__
    assert not Credentials({"KEY": "bad\r\nheader"}).status("env:KEY")


def test_os_store_rejects_non_native_backend_without_credential_operation(monkeypatch):
    keyring = pytest.importorskip("keyring")

    from deykit.providers.credentials import os_secret_store

    monkeypatch.setattr(keyring, "get_keyring", lambda: MemoryStore())
    with pytest.raises(CredentialUnavailable):
        os_secret_store()


def test_missing_optional_os_store_dependency_is_safe_and_local(monkeypatch):
    from deykit.providers import credentials

    def unavailable(name):
        raise ImportError("SECRET_SENTINEL")

    monkeypatch.setattr(credentials, "import_module", unavailable)
    with pytest.raises(CredentialUnavailable) as failure:
        credentials.os_secret_store()
    assert "SECRET_SENTINEL" not in str(failure.value)


def test_credentials_for_profile_loads_os_store_only_for_keyring_reference(monkeypatch):
    from deykit.providers import credentials

    profile = ProviderProfile(
        id="p",
        adapter="jev",
        requested_model="jev-1.13.0",
        destination=JEV_DESTINATION,
        credential_ref="env:OFFLINE_KEY",
    )
    monkeypatch.setenv("OFFLINE_KEY", "TEST_SENTINEL")
    monkeypatch.setattr(
        credentials,
        "os_secret_store",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected keyring import")),
    )
    assert credentials_for(profile).status("env:OFFLINE_KEY") is True
    store = MemoryStore()
    store.set_password("deykit", "p", "TEST_SENTINEL")
    monkeypatch.setattr(credentials, "os_secret_store", lambda: store)
    keyring = profile.model_copy(update={"credential_ref": "keyring:deykit/p"})
    assert credentials_for(keyring).status("keyring:deykit/p") is True
    monkeypatch.setattr(
        credentials,
        "os_secret_store",
        lambda: (_ for _ in ()).throw(CredentialUnavailable()),
    )
    assert credentials_for(keyring).status("keyring:deykit/p") is False
