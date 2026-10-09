"""Pure provider configuration values and application-facing ports."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol
from urllib.parse import quote, unquote

from deykit.contracts.ports import CommitReceipt
from deykit.contracts.records import ProviderProfile


class CredentialUnavailable(Exception):
    def __init__(self) -> None:
        super().__init__(
            "Configured credential is unavailable; set its environment or OS-store value."
        )


@dataclass(frozen=True)
class CredentialReference:
    kind: str
    name: str
    account: str | None = None

    @classmethod
    def parse(cls, reference: str) -> CredentialReference:
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


@dataclass(frozen=True)
class ProfileView:
    profile: ProviderProfile
    etag: str


@dataclass(frozen=True)
class ProfilePage:
    items: tuple[ProfileView, ...]
    total: int
    next_cursor: str | None


@dataclass(frozen=True)
class CompilerInfo:
    id: str
    version: str


@dataclass(frozen=True)
class ProviderCapabilities:
    input_kinds: tuple[Literal["text", "json"], ...]
    question_kind: Literal["choice"]
    max_options: int
    evidence_mode: Literal["authored_fixture", "live"]


@dataclass(frozen=True)
class CredentialConfiguration:
    configured: bool
    kind: Literal["env", "keyring"] | None


@dataclass(frozen=True)
class ProviderPresentation:
    view: ProfileView
    compiler: CompilerInfo
    capabilities: ProviderCapabilities
    credential: CredentialConfiguration


@dataclass(frozen=True)
class CredentialStatus:
    profile_id: str
    configured: bool
    available: bool
    kind: Literal["env", "keyring"] | None


@dataclass(frozen=True)
class ProviderMutation:
    operation_id: str
    profile: ProviderPresentation
    replayed: bool


@dataclass(frozen=True)
class ProviderPresentationPage:
    items: tuple[ProviderPresentation, ...]
    total: int
    next_cursor: str | None


@dataclass(frozen=True)
class ModelDescription:
    name: str
    description: str
    release_date: str


@dataclass(frozen=True)
class ModelList:
    profile_id: str
    network_check: Literal[True]
    inference_calls: Literal[0]
    models: tuple[ModelDescription, ...]


class ProfileReader(Protocol):
    def view(self, profile_id: str) -> ProfileView: ...

    def list_views(self, *, cursor: str | None = None, limit: int = 50) -> ProfilePage: ...


class ProfileWriter(Protocol):
    def configure(
        self, profile: ProviderProfile, *, expected_etag: str | None, operation_id: str
    ) -> CommitReceipt: ...

    def credential_replay(
        self,
        profile_id: str,
        reference: str | None,
        *,
        expected_etag: str,
        operation_id: str,
    ) -> CommitReceipt | None: ...

    def set_credential_ref(
        self,
        profile_id: str,
        reference: str | None,
        *,
        expected_etag: str,
        operation_id: str,
    ) -> CommitReceipt: ...

    def from_receipt(self, receipt: CommitReceipt) -> ProfileView: ...


class CredentialAccess(Protocol):
    def status(self, reference: str) -> bool: ...

    def set(self, reference: str, value: str) -> None: ...

    def forget(self, reference: str) -> None: ...


class CredentialReferences(Protocol):
    def validate(self, reference: str) -> CredentialReference: ...

    def environment(self, name: str) -> str: ...

    def os_store(self, profile_id: str) -> str: ...


class ProviderDescriptor(Protocol):
    def describe(
        self, profile: ProviderProfile
    ) -> tuple[CompilerInfo, ProviderCapabilities]: ...


class ModelLister(Protocol):
    def models(
        self, profile: ProviderProfile, *, timeout_seconds: float
    ) -> Awaitable[tuple[ModelDescription, ...]]: ...


ProfileCredentialFactory = Callable[[ProviderProfile], CredentialAccess]
OSCredentialFactory = Callable[[], CredentialAccess]
