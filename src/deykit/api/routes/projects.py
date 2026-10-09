"""Project registration routes retain only explicitly opened local sources."""

from fastapi import APIRouter, Response

from deykit.api.dependencies import ApiDependencies
from deykit.application.datasets import DatasetService
from deykit.application.definitions import DecisionService
from deykit.application.projects import ProjectInfo, ProjectService

from ..dto.common import ErrorDTO, Success, VersionRequest
from ..dto.projects import (
    DemoCreateDTO,
    DemoCreateRequest,
    DemoSummaryDTO,
    ProjectOverviewDTO,
    ProjectRecordDTO,
    RebuildIndexDTO,
    RecentProjectDTO,
    RecentProjectsDTO,
    RegisterProjectRequest,
    RegistrationDTO,
    ResourceSummaryDTO,
)
from ..registry import ProjectRegistry, RegistrationReply
from ..runtime import TrackedWorkers


def _reply(value: RegistrationReply) -> RegistrationDTO:
    return RegistrationDTO(
        registration_id=value.registration_id,
        path=value.path,
        project=ProjectRecordDTO(
            id=value.info.project.id,
            name=value.info.project.name,
            created_at=value.info.project.created_at,
            default_provider_id=value.info.project.default_provider_id,
        ),
        project_etag=value.info.etag,
        execution_active=value.info.execution_active,
        record_count=str(value.info.record_count),
    )


def register(
    router: APIRouter,
    dependencies: ApiDependencies,
    registry: ProjectRegistry,
    workers: TrackedWorkers,
) -> None:
    @router.post(
        "/projects/demo",
        response_model=Success[DemoCreateDTO],
        operation_id="createAuthoredDemo",
    )
    async def create_demo(
        body: DemoCreateRequest, response: Response
    ) -> Success[DemoCreateDTO]:
        registration, demo = await workers.run_sync(
            registry.register_demo,
            body.path,
            body.operation_id,
            staging_factory=dependencies.demo_staging_factory,
        )
        warnings = tuple(
            ErrorDTO(
                code=error.code,
                message=error.message,
                resource_id=error.resource_id,
                row=error.row,
                reason=error.reason,
            )
            for error in registration.warnings
        )
        response.headers["ETag"] = f'"{registration.info.etag}"'
        return Success(
            data=DemoCreateDTO(
                registration=_reply(registration),
                demo=DemoSummaryDTO(
                    operation_id=demo.operation_id,
                    replayed=demo.replayed,
                    evidence_mode=demo.evidence_mode,
                    project_id=demo.project_id,
                    decision_id=demo.decision_id,
                    revision_id=demo.revision_id,
                    dataset_id=demo.dataset_id,
                    profile_id=demo.profile_id,
                    fixture_set_id=demo.fixture_set_id,
                    case_count=str(demo.case_count),
                    binding_count=str(demo.binding_count),
                    label_count=str(demo.label_count),
                ),
            ),
            warnings=warnings,
        )

    @router.get(
        "/projects/recent",
        response_model=Success[RecentProjectsDTO],
        operation_id="listRecentProjects",
    )
    async def recent_projects() -> Success[RecentProjectsDTO]:
        items = await workers.run_sync(dependencies.recent_store.list)
        warnings = (
            (ErrorDTO(code="preflight_failed", message="Recent projects could not be read."),)
            if dependencies.recent_store.last_warning is not None
            else ()
        )
        return Success(
            data=RecentProjectsDTO(
                items=tuple(RecentProjectDTO(**item.__dict__) for item in items)
            ),
            warnings=warnings,
        )

    @router.post(
        "/projects/register",
        response_model=Success[RegistrationDTO],
        operation_id="registerProject",
    )
    async def register_project(
        body: RegisterProjectRequest, response: Response
    ) -> Success[RegistrationDTO]:
        reply = await workers.run_sync(
            registry.register,
            body.action,
            body.path,
            name=body.name,
            operation_id=body.operation_id,
        )
        warnings = tuple(
            ErrorDTO(
                code=error.code,
                message=error.message,
                resource_id=error.resource_id,
                row=error.row,
                reason=error.reason,
            )
            for error in reply.warnings
        )
        response.headers["ETag"] = f'"{reply.info.etag}"'
        return Success(data=_reply(reply), warnings=warnings)

    @router.get(
        "/projects/{registration_id}",
        response_model=Success[RegistrationDTO],
        operation_id="showRegisteredProject",
    )
    async def show_project(registration_id: str, response: Response) -> Success[RegistrationDTO]:
        registration = registry.require(registration_id)
        service = ProjectService(
            dependencies.source_factory,
            dependencies.clock,
            dependencies.id_factory,
        )
        info = await workers.run_sync(service.describe, registration.source)
        response.headers["ETag"] = f'"{info.etag}"'
        return Success(
            data=_reply(
                RegistrationReply(registration.id, registration.display_path, info)
            )
        )

    @router.get(
        "/projects/{registration_id}/overview",
        response_model=Success[ProjectOverviewDTO],
        operation_id="projectOverview",
    )
    async def project_overview(
        registration_id: str, response: Response
    ) -> Success[ProjectOverviewDTO]:
        registration = registry.require(registration_id)
        source = registration.source
        project_service = ProjectService(
            dependencies.source_factory,
            dependencies.clock,
            dependencies.id_factory,
        )

        def read_overview() -> tuple[
            ProjectInfo,
            tuple[ResourceSummaryDTO, ...],
            tuple[ResourceSummaryDTO, ...],
        ]:
            info = project_service.describe(source)
            decisions: list[ResourceSummaryDTO] = []
            datasets: list[ResourceSummaryDTO] = []
            with source.consistent_read():
                cursor = None
                while True:
                    decision_page = DecisionService(
                        source, dependencies.clock, dependencies.id_factory
                    ).list(cursor=cursor, limit=500)
                    decisions.extend(
                        ResourceSummaryDTO(
                            id=item.decision.record.id, name=item.decision.record.name
                        )
                        for item in decision_page.items
                    )
                    if decision_page.next_cursor is None:
                        break
                    cursor = decision_page.next_cursor
                cursor = None
                while True:
                    dataset_page = DatasetService(
                        source, dependencies.clock, dependencies.id_factory
                    ).list(cursor=cursor, limit=500)
                    datasets.extend(
                        ResourceSummaryDTO(id=item.record.id, name=item.record.name)
                        for item in dataset_page.items
                    )
                    if dataset_page.next_cursor is None:
                        break
                    cursor = dataset_page.next_cursor
            return info, tuple(decisions), tuple(datasets)

        info, decisions, datasets = await workers.run_sync(read_overview)
        response.headers["ETag"] = f'"{info.etag}"'
        return Success(
            data=ProjectOverviewDTO(
                registration=_reply(
                    RegistrationReply(registration.id, registration.display_path, info)
                ),
                decisions=decisions,
                datasets=datasets,
            )
        )

    @router.post(
        "/projects/{registration_id}/validate",
        response_model=Success[RegistrationDTO],
        operation_id="validateRegisteredProject",
    )
    async def validate_project(
        registration_id: str, body: VersionRequest, response: Response
    ) -> Success[RegistrationDTO]:
        del body
        registration = registry.require(registration_id)
        service = ProjectService(
            dependencies.source_factory,
            dependencies.clock,
            dependencies.id_factory,
        )
        info = await workers.run_sync(service.validate_opened, registration.source)
        response.headers["ETag"] = f'"{info.etag}"'
        warnings = tuple(
            ErrorDTO(
                code=error.code,
                message=error.message,
                resource_id=error.resource_id,
                row=error.row,
                reason=error.reason,
            )
            for error in info.reference_warnings
        )
        return Success(
            data=_reply(RegistrationReply(registration.id, registration.display_path, info)),
            warnings=warnings,
        )

    @router.post(
        "/projects/{registration_id}/rebuild-index",
        response_model=Success[RebuildIndexDTO],
        operation_id="rebuildRegisteredProjectIndex",
    )
    async def rebuild_index(
        registration_id: str, body: VersionRequest
    ) -> Success[RebuildIndexDTO]:
        del body
        registration = registry.require(registration_id)
        count = await workers.run_sync(registration.source.rebuild_index)
        return Success(data=RebuildIndexDTO(record_count=str(count)))
