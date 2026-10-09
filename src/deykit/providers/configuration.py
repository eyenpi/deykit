"""Concrete local adapters for the shared provider configuration service."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from deykit.application.errors import ServiceFailure
from deykit.application.provider_operations import ProviderOperations
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import validate_resource_id
from deykit.contracts.provider_configuration import (
    CompilerInfo,
    CredentialReference,
    CredentialUnavailable,
    ModelDescription,
    ModelLister,
    ProviderCapabilities,
)
from deykit.contracts.ports import ProjectSource
from deykit.contracts.records import ProviderProfile
from deykit.providers.choice import COMPILER_ID, COMPILER_VERSION
from deykit.providers.credentials import Credentials, SecretStore, os_secret_store
from deykit.providers.profiles import ProviderProfiles


class _CredentialReferences:
    def validate(self, reference: str) -> CredentialReference:
        try:
            return CredentialReference.parse(reference)
        except (TypeError, ValueError):
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_credential_reference")
            ) from None

    def environment(self, name: str) -> str:
        return self.validate(f"env:{name}").encode()

    def os_store(self, profile_id: str) -> str:
        try:
            validate_resource_id(profile_id)
        except (TypeError, ValueError):
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_profile_id")
            ) from None
        return CredentialReference("keyring", "deykit", profile_id).encode()


class _ProviderDescriptor:
    def describe(
        self, profile: ProviderProfile
    ) -> tuple[CompilerInfo, ProviderCapabilities]:
        return (
            CompilerInfo(COMPILER_ID, COMPILER_VERSION),
            ProviderCapabilities(
                input_kinds=("text", "json"),
                question_kind="choice",
                max_options=255,
                evidence_mode="authored_fixture" if profile.adapter == "fixture" else "live",
            ),
        )


class _JevModelLister:
    def __init__(self, credentials_factory: Callable[[ProviderProfile], Credentials]) -> None:
        self._credentials_factory = credentials_factory

    async def models(
        self, profile: ProviderProfile, *, timeout_seconds: float
    ) -> tuple[ModelDescription, ...]:
        from deykit.providers.choice import ResponseInvalid
        from deykit.providers.http import HttpFailure
        from deykit.providers.jev import JevProvider

        if profile.adapter != "jev":
            raise ServiceFailure(
                ServiceError(code="preflight_failed", reason="models_require_live_provider")
            )
        try:
            models = await JevProvider(profile, self._credentials_factory(profile)).models(
                timeout_seconds=timeout_seconds
            )
        except CredentialUnavailable:
            raise ServiceFailure(
                ServiceError(code="preflight_failed", reason="credential_unavailable")
            ) from None
        except ResponseInvalid:
            raise ServiceFailure(
                ServiceError(code="response_invalid", reason="invalid_models")
            ) from None
        except HttpFailure as error:
            raise ServiceFailure(
                ServiceError(code="provider_rejected", reason=error.kind)
            ) from None
        except ValueError:
            raise ServiceFailure(
                ServiceError(code="provider_rejected", reason="model_list_failed")
            ) from None
        return tuple(
            ModelDescription(item["name"], item["description"], item["release_date"])
            for item in models
        )


def create_provider_operations(
    source: ProjectSource,
    *,
    environment: Mapping[str, str] | None = None,
    os_store_factory: Callable[[], SecretStore] = os_secret_store,
    model_lister: ModelLister | None = None,
) -> ProviderOperations:
    """Compose local adapters without opening a credential store or sending HTTP."""
    profiles = ProviderProfiles(source)

    def credentials_for_profile(profile: ProviderProfile) -> Credentials:
        reference = profile.credential_ref
        if reference is None:
            return Credentials(environment=environment)
        parsed = CredentialReference.parse(reference)
        if parsed.kind == "env":
            return Credentials(environment=environment)
        try:
            store = os_store_factory()
        except CredentialUnavailable:
            return Credentials(environment=environment)
        return Credentials(environment=environment, store=store)

    def os_credentials() -> Credentials:
        store = os_store_factory()
        return Credentials(environment=environment, store=store)

    selected_models = (
        _JevModelLister(credentials_for_profile) if model_lister is None else model_lister
    )
    return ProviderOperations(
        reader=profiles,
        writer=profiles,
        credentials_factory=credentials_for_profile,
        os_credentials_factory=os_credentials,
        references=_CredentialReferences(),
        descriptor=_ProviderDescriptor(),
        models=selected_models,
    )
