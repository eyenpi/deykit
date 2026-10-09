"""Credential references and explicit local credential operations, without network."""

import os
from collections.abc import Mapping
from importlib import import_module
from typing import TYPE_CHECKING, Protocol, cast

from deykit.contracts.provider_configuration import (
    CredentialReference as CredentialReference,
)
from deykit.contracts.provider_configuration import (
    CredentialUnavailable as CredentialUnavailable,
)

if TYPE_CHECKING:
    from deykit.contracts.records import ProviderProfile


class SecretStore(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


class Credentials:
    def __init__(
        self, environment: Mapping[str, str] | None = None, store: SecretStore | None = None
    ) -> None:
        self._environment = os.environ if environment is None else environment
        self._store = store

    def __repr__(self) -> str:
        return "Credentials(<redacted>)"

    def resolve(self, reference: str) -> str:
        ref = CredentialReference.parse(reference)
        try:
            if ref.kind == "env":
                value = self._environment.get(ref.name)
            elif self._store is not None:
                value = self._store.get_password(ref.name, ref.account or "")
            else:
                value = None
        except Exception:
            raise CredentialUnavailable() from None
        if not value or not value.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise CredentialUnavailable()
        return value

    def status(self, reference: str) -> bool:
        try:
            self.resolve(reference)
        except CredentialUnavailable:
            return False
        return True

    def set(self, reference: str, value: str) -> None:
        ref = CredentialReference.parse(reference)
        if ref.kind != "keyring" or self._store is None:
            raise ValueError("Credential set requires an available OS-store reference.")
        if not value or not value.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise ValueError("Credential value must contain printable non-whitespace ASCII.")
        try:
            self._store.set_password(ref.name, ref.account or "", value)
        except Exception:
            raise CredentialUnavailable() from None

    def forget(self, reference: str) -> None:
        ref = CredentialReference.parse(reference)
        if ref.kind != "keyring" or self._store is None:
            raise ValueError("Credential forget requires an available OS-store reference.")
        try:
            # The native deletion can finish before a project-reference write fails.
            # A healthy read proving absence makes that explicit retry safe; backend
            # read/delete failures still block unlinking instead of pretending success.
            if self._store.get_password(ref.name, ref.account or "") is not None:
                self._store.delete_password(ref.name, ref.account or "")
        except Exception:
            raise CredentialUnavailable() from None


def os_secret_store() -> SecretStore:
    """Explicit opt-in to the installed OS keyring backend; never called at import."""
    try:
        keyring = import_module("keyring")
        backend = keyring.get_keyring()
        approved = {
            "keyring.backends.macOS",
            "keyring.backends.Windows",
            "keyring.backends.SecretService",
            "keyring.backends.kwallet",
        }
        if type(backend).__module__ not in approved:
            raise CredentialUnavailable()
        return cast(SecretStore, backend)
    except Exception:
        raise CredentialUnavailable() from None


def credentials_for(profile: "ProviderProfile") -> Credentials:
    """Resolve a frozen profile lazily; environment profiles never load keyring."""
    from deykit.contracts.records import ProviderProfile

    if type(profile) is not ProviderProfile or profile.credential_ref is None:
        return Credentials()
    try:
        reference = CredentialReference.parse(profile.credential_ref)
    except ValueError:
        return Credentials()
    if reference.kind != "keyring":
        return Credentials()
    try:
        return Credentials(store=os_secret_store())
    except CredentialUnavailable:
        return Credentials()
