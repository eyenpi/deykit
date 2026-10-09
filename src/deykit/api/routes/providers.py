"""Provider configuration, explicit credential actions, models, and fixture evidence."""

from fastapi import APIRouter, Response

from deykit.api.dependencies import ApiDependencies
from deykit.application.fixtures import FixtureService, FixtureSummary
from deykit.application.provider_operations import ProviderOperations
from deykit.contracts.provider_configuration import ProviderPresentation
from deykit.contracts.records import ProviderProfile

from ..dto.common import Success, VersionRequest
from ..dto.providers import (
    CredentialStatusDTO,
    EnvironmentCredentialRequest,
    FixtureBindingDTO,
    FixtureCreatedDTO,
    FixtureCreateRequest,
    FixturePageDTO,
    FixtureSummaryDTO,
    ModelDTO,
    ModelListDTO,
    OSCredentialRequest,
    ProviderETagRequest,
    ProviderMutationDTO,
    ProviderPageDTO,
    ProviderProfileDTO,
    ProviderProfileRequest,
)
from ..query import boolean, decimal
from ..registry import ProjectRegistry
from ..runtime import TrackedWorkers


def _profile(presentation: ProviderPresentation) -> ProviderProfileDTO:
    view = presentation.view
    profile = view.profile
    return ProviderProfileDTO(
        id=profile.id,
        adapter=profile.adapter,
        requested_model=profile.requested_model,
        destination=profile.destination,
        etag=view.etag,
        compiler_id=presentation.compiler.id,
        compiler_version=presentation.compiler.version,
        input_kinds=presentation.capabilities.input_kinds,
        question_kind=presentation.capabilities.question_kind,
        max_options=presentation.capabilities.max_options,
        evidence_mode=presentation.capabilities.evidence_mode,
        credential_configured=presentation.credential.configured,
        credential_kind=presentation.credential.kind,
    )


def _fixture(value: FixtureSummary, etag: str | None = None) -> FixtureSummaryDTO:
    return FixtureSummaryDTO(
        id=value.id,
        decision_id=value.decision_id,
        dataset_id=value.dataset_id,
        name=value.name,
        model_identity=value.model_identity,
        binding_count=str(value.binding_count),
        created_at=value.created_at,
        content_hash=value.content_hash,
        bindings=tuple(FixtureBindingDTO(**item.__dict__) for item in value.bindings),
        requests=value.requests,
        etag=etag,
    )


def register(
    router: APIRouter,
    dependencies: ApiDependencies,
    registry: ProjectRegistry,
    workers: TrackedWorkers,
) -> None:
    def operations(registration_id: str) -> ProviderOperations:
        return dependencies.provider_operations_factory(registry.require(registration_id).source)

    def fixtures(registration_id: str) -> FixtureService:
        return FixtureService(
            registry.require(registration_id).source,
            dependencies.clock,
        )

    @router.get(
        "/projects/{registration_id}/providers",
        response_model=Success[ProviderPageDTO],
        operation_id="listProviderProfiles",
    )
    async def list_providers(
        registration_id: str,
        cursor: str | None = None,
        limit: str = "50",
    ) -> Success[ProviderPageDTO]:
        page = await workers.run_sync(
            operations(registration_id).list,
            cursor=cursor,
            limit=decimal(limit, reason="invalid_page_limit", minimum=1, maximum=500),
        )
        return Success(
            data=ProviderPageDTO(
                items=tuple(_profile(item) for item in page.items),
                total=str(page.total),
                next_cursor=page.next_cursor,
            )
        )

    @router.get(
        "/projects/{registration_id}/providers/{profile_id}",
        response_model=Success[ProviderProfileDTO],
        operation_id="readProviderProfile",
    )
    async def read_provider(
        registration_id: str, profile_id: str, response: Response
    ) -> Success[ProviderProfileDTO]:
        value = await workers.run_sync(operations(registration_id).describe, profile_id)
        response.headers["ETag"] = f'"{value.view.etag}"'
        return Success(data=_profile(value))

    @router.put(
        "/projects/{registration_id}/providers/{profile_id}",
        response_model=Success[ProviderMutationDTO],
        operation_id="configureProviderProfile",
    )
    async def configure_provider(
        registration_id: str,
        profile_id: str,
        body: ProviderProfileRequest,
        response: Response,
    ) -> Success[ProviderMutationDTO]:
        if body.profile_id != profile_id:
            from deykit.application.errors import ServiceFailure
            from deykit.contracts.errors import ServiceError

            raise ServiceFailure(
                ServiceError(code="validation_error", reason="profile_identity_mismatch")
            )
        service = operations(registration_id)
        profile = ProviderProfile(
            id=profile_id,
            adapter=body.adapter,
            requested_model=body.requested_model,
            destination=body.destination,
            credential_ref=body.credential_ref,
        )
        result = await workers.run_sync(
            service.configure,
            profile,
            expected_etag=body.expected_etag,
            operation_id=body.operation_id,
        )
        response.headers["ETag"] = f'"{result.profile.view.etag}"'
        return Success(
            data=ProviderMutationDTO(
                operation_id=result.operation_id,
                replayed=result.replayed,
                profile=_profile(result.profile),
            )
        )

    @router.get(
        "/projects/{registration_id}/providers/{profile_id}/credential-status",
        response_model=Success[CredentialStatusDTO],
        operation_id="providerCredentialStatus",
    )
    async def credential_status(
        registration_id: str, profile_id: str
    ) -> Success[CredentialStatusDTO]:
        value = await workers.run_sync(operations(registration_id).credential_status, profile_id)
        return Success(data=CredentialStatusDTO(**value.__dict__))

    @router.post(
        "/projects/{registration_id}/providers/{profile_id}/credential-environment",
        response_model=Success[ProviderMutationDTO],
        operation_id="attachEnvironmentCredential",
    )
    async def attach_environment(
        registration_id: str,
        profile_id: str,
        body: EnvironmentCredentialRequest,
        response: Response,
    ) -> Success[ProviderMutationDTO]:
        value = await workers.run_sync(
            operations(registration_id).attach_environment,
            profile_id,
            body.environment_name,
            expected_etag=body.expected_etag,
            operation_id=body.operation_id,
        )
        response.headers["ETag"] = f'"{value.profile.view.etag}"'
        return Success(
            data=ProviderMutationDTO(
                operation_id=value.operation_id,
                replayed=value.replayed,
                profile=_profile(value.profile),
            )
        )

    @router.post(
        "/projects/{registration_id}/providers/{profile_id}/credential-os-store",
        response_model=Success[ProviderMutationDTO],
        operation_id="setOSStoreCredential",
    )
    async def set_os_credential(
        registration_id: str,
        profile_id: str,
        body: OSCredentialRequest,
        response: Response,
    ) -> Success[ProviderMutationDTO]:
        value = await workers.run_sync(
            operations(registration_id).set_os_credential,
            profile_id,
            value_factory=lambda: body.credential_value,
            expected_etag=body.expected_etag,
            operation_id=body.operation_id,
        )
        response.headers["ETag"] = f'"{value.profile.view.etag}"'
        return Success(
            data=ProviderMutationDTO(
                operation_id=value.operation_id,
                replayed=value.replayed,
                profile=_profile(value.profile),
            )
        )

    @router.post(
        "/projects/{registration_id}/providers/{profile_id}/credential-forget",
        response_model=Success[ProviderMutationDTO],
        operation_id="forgetProviderCredential",
    )
    async def forget_credential(
        registration_id: str,
        profile_id: str,
        body: ProviderETagRequest,
        response: Response,
    ) -> Success[ProviderMutationDTO]:
        value = await workers.run_sync(
            operations(registration_id).forget_credential,
            profile_id,
            expected_etag=body.expected_etag,
            operation_id=body.operation_id,
        )
        response.headers["ETag"] = f'"{value.profile.view.etag}"'
        return Success(
            data=ProviderMutationDTO(
                operation_id=value.operation_id,
                replayed=value.replayed,
                profile=_profile(value.profile),
            )
        )

    @router.post(
        "/projects/{registration_id}/providers/{profile_id}/models",
        response_model=Success[ModelListDTO],
        operation_id="listProviderModels",
    )
    async def list_models(
        registration_id: str,
        profile_id: str,
        body: VersionRequest,
        timeout_seconds: str = "60",
    ) -> Success[ModelListDTO]:
        del body
        value = await workers.run_async(
            operations(registration_id).list_models,
            profile_id,
            timeout_seconds=decimal(
                timeout_seconds, reason="invalid_timeout", minimum=1, maximum=600
            ),
        )
        return Success(
            data=ModelListDTO(
                profile_id=value.profile_id,
                network_check=value.network_check,
                inference_calls=value.inference_calls,
                models=tuple(ModelDTO(**item.__dict__) for item in value.models),
            )
        )

    @router.get(
        "/projects/{registration_id}/fixtures",
        response_model=Success[FixturePageDTO],
        operation_id="listFixtureSets",
    )
    async def list_fixtures(
        registration_id: str,
        cursor: str | None = None,
        limit: str = "50",
    ) -> Success[FixturePageDTO]:
        page = await workers.run_sync(
            fixtures(registration_id).list,
            cursor=cursor,
            limit=decimal(limit, reason="invalid_page_limit", minimum=1, maximum=500),
        )
        return Success(
            data=FixturePageDTO(
                items=tuple(_fixture(item) for item in page.items),
                total=str(page.total),
                next_cursor=page.next_cursor,
            )
        )

    @router.get(
        "/projects/{registration_id}/fixtures/{fixture_set_id}",
        response_model=Success[FixtureSummaryDTO],
        operation_id="readFixtureSet",
    )
    async def read_fixture(
        registration_id: str,
        fixture_set_id: str,
        response: Response,
        include_requests: str = "false",
    ) -> Success[FixtureSummaryDTO]:
        service = fixtures(registration_id)
        stored = await workers.run_sync(service.read, fixture_set_id)
        summary = await workers.run_sync(
            service.read_summary,
            fixture_set_id,
            include_requests=boolean(include_requests, reason="invalid_include_requests"),
        )
        response.headers["ETag"] = f'"{stored.etag}"'
        return Success(data=_fixture(summary, stored.etag))

    @router.post(
        "/projects/{registration_id}/fixtures",
        response_model=Success[FixtureCreatedDTO],
        operation_id="createFixtureSet",
    )
    async def create_fixture(
        registration_id: str, body: FixtureCreateRequest, response: Response
    ) -> Success[FixtureCreatedDTO]:
        service = fixtures(registration_id)
        stored = await workers.run_sync(
            service.create,
            body.fixture_set_id,
            body.decision_id,
            body.dataset_id,
            body.name,
            body.model_identity,
            body.binding_sources,
            operation_id=body.operation_id,
            note=body.note,
        )
        summary = service.identity_summary(stored)
        response.headers["ETag"] = f'"{stored.etag}"'
        return Success(
            data=FixtureCreatedDTO(
                operation_id=body.operation_id,
                replayed=stored.replayed,
                fixture=_fixture(summary, stored.etag),
            )
        )
