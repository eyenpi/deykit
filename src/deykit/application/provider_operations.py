"""Shared profile and credential orchestration over narrow provider ports."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Literal, cast

from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError
from deykit.contracts.ports import CommitReceipt
from deykit.contracts.provider_configuration import (
    CredentialConfiguration,
    CredentialReferences,
    CredentialStatus,
    CredentialUnavailable,
    ModelList,
    ModelLister,
    OSCredentialFactory,
    ProfileCredentialFactory,
    ProfileReader,
    ProfileView,
    ProfileWriter,
    ProviderDescriptor,
    ProviderMutation,
    ProviderPresentation,
    ProviderPresentationPage,
)
from deykit.contracts.records import ProviderProfile


class ProviderOperations:
    def __init__(
        self,
        reader: ProfileReader,
        writer: ProfileWriter,
        credentials_factory: ProfileCredentialFactory,
        os_credentials_factory: OSCredentialFactory,
        references: CredentialReferences,
        descriptor: ProviderDescriptor,
        models: ModelLister,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._credentials_factory = credentials_factory
        self._os_credentials_factory = os_credentials_factory
        self._references = references
        self._descriptor = descriptor
        self._models = models

    def _presentation(self, profile: ProviderProfile, etag: str) -> ProviderPresentation:
        compiler, capabilities = self._descriptor.describe(profile)
        reference = profile.credential_ref
        kind: Literal["env", "keyring"] | None = None
        if reference is not None:
            kind = cast(Literal["env", "keyring"], self._references.validate(reference).kind)
        return ProviderPresentation(
            view=self._view(profile, etag),
            compiler=compiler,
            capabilities=capabilities,
            credential=CredentialConfiguration(reference is not None, kind),
        )

    @staticmethod
    def _view(profile: ProviderProfile, etag: str) -> ProfileView:
        return ProfileView(profile, etag)

    def _mutation(self, operation_id: str, receipt: CommitReceipt) -> ProviderMutation:
        view = self._writer.from_receipt(receipt)
        return ProviderMutation(
            operation_id=operation_id,
            profile=self._presentation(view.profile, view.etag),
            replayed=receipt.replayed,
        )

    def describe(self, profile_id: str) -> ProviderPresentation:
        view = self._reader.view(profile_id)
        return self._presentation(view.profile, view.etag)

    def list(self, *, cursor: str | None = None, limit: int = 50) -> ProviderPresentationPage:
        page = self._reader.list_views(cursor=cursor, limit=limit)
        return ProviderPresentationPage(
            tuple(self._presentation(view.profile, view.etag) for view in page.items),
            page.total,
            page.next_cursor,
        )

    def configure(
        self,
        profile: ProviderProfile,
        *,
        expected_etag: str | None,
        operation_id: str,
    ) -> ProviderMutation:
        receipt = self._writer.configure(
            profile, expected_etag=expected_etag, operation_id=operation_id
        )
        return self._mutation(operation_id, receipt)

    def credential_status(self, profile_id: str) -> CredentialStatus:
        profile = self._reader.view(profile_id).profile
        reference = profile.credential_ref
        kind: Literal["env", "keyring"] | None = None
        available = False
        if reference is not None:
            kind = cast(Literal["env", "keyring"], self._references.validate(reference).kind)
            try:
                available = self._credentials_factory(profile).status(reference)
            except CredentialUnavailable:
                available = False
        return CredentialStatus(profile.id, reference is not None, available, kind)

    def _admit_credential_mutation(
        self,
        profile_id: str,
        reference: str | None,
        *,
        expected_etag: str,
        operation_id: str,
    ) -> ProviderMutation | ProviderProfile:
        replay = self._writer.credential_replay(
            profile_id,
            reference,
            expected_etag=expected_etag,
            operation_id=operation_id,
        )
        if replay is not None:
            return self._mutation(operation_id, replay)
        current = self._reader.view(profile_id)
        if current.etag != expected_etag:
            raise ServiceFailure(ServiceError(code="conflict", reason="provider_profile_changed"))
        if current.profile.adapter == "fixture":
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="fixture_has_no_credential")
            )
        return current.profile

    def attach_environment(
        self,
        profile_id: str,
        environment_name: str,
        *,
        expected_etag: str,
        operation_id: str,
    ) -> ProviderMutation:
        try:
            reference = self._references.environment(environment_name)
            self._references.validate(reference)
        except (TypeError, ValueError):
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_credential_reference")
            ) from None
        admitted = self._admit_credential_mutation(
            profile_id,
            reference,
            expected_etag=expected_etag,
            operation_id=operation_id,
        )
        if isinstance(admitted, ProviderMutation):
            return admitted
        receipt = self._writer.set_credential_ref(
            profile_id,
            reference,
            expected_etag=expected_etag,
            operation_id=operation_id,
        )
        return self._mutation(operation_id, receipt)

    def set_os_credential(
        self,
        profile_id: str,
        *,
        value_factory: Callable[[], str],
        expected_etag: str,
        operation_id: str,
    ) -> ProviderMutation:
        try:
            reference = self._references.os_store(profile_id)
            self._references.validate(reference)
        except (TypeError, ValueError):
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_credential_reference")
            ) from None
        external_attempted = False

        def set_external_credential() -> None:
            nonlocal external_attempted
            value = value_factory()
            try:
                credentials = self._os_credentials_factory()
            except (CredentialUnavailable, ValueError):
                raise ServiceFailure(
                    ServiceError(
                        code="preflight_failed",
                        reason="credential_store_unavailable",
                        resource_id=profile_id,
                    )
                ) from None
            external_attempted = True
            credentials.set(reference, value)

        try:
            receipt = self._writer.set_credential_ref(
                profile_id,
                reference,
                expected_etag=expected_etag,
                operation_id=operation_id,
                before_commit=set_external_credential,
            )
            return self._mutation(operation_id, receipt)
        except Exception:
            if external_attempted:
                raise ServiceFailure(
                    ServiceError(
                        code="internal_error",
                        reason="credential_update_outcome_unknown",
                        resource_id=profile_id,
                    )
                ) from None
            raise

    def forget_credential(
        self, profile_id: str, *, expected_etag: str, operation_id: str
    ) -> ProviderMutation:
        admitted = self._admit_credential_mutation(
            profile_id,
            None,
            expected_etag=expected_etag,
            operation_id=operation_id,
        )
        if isinstance(admitted, ProviderMutation):
            return admitted
        reference = admitted.credential_ref
        external_attempted = False
        before_commit = None
        if reference is not None:
            parsed = self._references.validate(reference)
            if parsed.kind == "keyring":

                def forget_external_credential() -> None:
                    nonlocal external_attempted
                    try:
                        credentials = self._os_credentials_factory()
                    except (CredentialUnavailable, ValueError):
                        raise ServiceFailure(
                            ServiceError(
                                code="preflight_failed",
                                reason="credential_store_unavailable",
                                resource_id=profile_id,
                            )
                        ) from None
                    external_attempted = True
                    credentials.forget(reference)

                before_commit = forget_external_credential
        try:
            receipt = self._writer.set_credential_ref(
                profile_id,
                None,
                expected_etag=expected_etag,
                operation_id=operation_id,
                before_commit=before_commit,
            )
            return self._mutation(operation_id, receipt)
        except Exception:
            if external_attempted:
                raise ServiceFailure(
                    ServiceError(
                        code="internal_error",
                        reason="credential_update_outcome_unknown",
                        resource_id=profile_id,
                    )
                ) from None
            raise

    async def list_models(self, profile_id: str, *, timeout_seconds: float = 60) -> ModelList:
        profile = self._reader.view(profile_id).profile
        return await self._list_models_for_profile(profile, timeout_seconds=timeout_seconds)

    async def _list_models_for_profile(
        self, profile: ProviderProfile, *, timeout_seconds: float = 60
    ) -> ModelList:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 600
        ):
            raise ServiceFailure(ServiceError(code="validation_error", reason="invalid_timeout"))
        if profile.adapter == "openai":
            raise ServiceFailure(
                ServiceError(code="preflight_failed", reason="model_listing_unsupported")
            )
        if profile.adapter != "jev":
            raise ServiceFailure(
                ServiceError(code="preflight_failed", reason="models_require_live_provider")
            )
        result = await self._models.models(profile, timeout_seconds=float(timeout_seconds))
        return ModelList(profile.id, True, 0, result)
