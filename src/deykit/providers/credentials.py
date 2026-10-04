"""Credential references and explicit local credential operations, without network."""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import Protocol, cast
from urllib.parse import quote, unquote


class CredentialUnavailable(Exception):
    def __init__(self) -> None:
        super().__init__(
            "Configured credential is unavailable; set its environment or OS-store value."
        )


class SecretStore(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


@dataclass(frozen=True)
class CredentialReference:
    kind: str
    name: str
    account: str | None = None

    @classmethod
    def parse(cls, reference: str) -> "CredentialReference":
        if reference.startswith("env:"):
            name = reference[4:]
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                return cls("env", name)
        if reference.startswith("keyring:"):
            parts = reference[8:].split("/")
            if len(parts) == 2:
                service, account = (unquote(part) for part in parts)
                if service and account and all(c.isprintable() for c in service + account):
                    return cls("keyring", service, account)
        raise ValueError("Credential reference must be env:NAME or keyring:SERVICE/ACCOUNT.")

    def encode(self) -> str:
        if self.kind == "env":
            return f"env:{self.name}"
        return f"keyring:{quote(self.name, safe='')}/{quote(self.account or '', safe='')}"


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
