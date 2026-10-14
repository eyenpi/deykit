"""Construct the strict headless local API and session boundary."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from .config import LocalServerConfig
from .dependencies import ApiDependencies
from .errors import TransportFailure, error_response
from .registry import ProjectRegistry
from .routes.session import register as register_session
from .runtime import TrackedWorkers
from .security import LocalBoundary
from .session import SessionCapability
from .supervisor import ExecutionSupervisor


def create_inner_app(
    config: LocalServerConfig,
    session: SessionCapability,
    dependencies: ApiDependencies,
) -> FastAPI:
    registry = ProjectRegistry(dependencies, max_registrations=config.max_registrations)
    workers = TrackedWorkers()
    supervisor = ExecutionSupervisor(workers)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            session.revoke()
            await supervisor.stop_admission()
            try:
                await supervisor.shutdown()
            finally:
                await workers.wait_idle()
                registry.close_all()

    app = FastAPI(
        lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return error_response(TransportFailure(422, "validation_error", "invalid_request"))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        if error.status_code == 405:
            return error_response(TransportFailure(405, "method_not_allowed", "unsupported_method"))
        return error_response(TransportFailure(404, "not_found", "route_not_found"))

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception) -> JSONResponse:
        return error_response(error)

    router = APIRouter(prefix="/api/v1")
    register_session(router, session, config.origin)
    from .routes import (
        authoring,
        checks,
        comparisons,
        data,
        diagnostics,
        execution,
        labels,
        previews,
        projects,
        providers,
        regressions,
        reports,
        results,
    )

    projects.register(router, dependencies, registry, workers)
    authoring.register(router, dependencies, registry, workers)
    data.register(router, dependencies, registry, workers)
    labels.register(router, dependencies, registry, workers)
    previews.register(router, dependencies, registry, workers)
    providers.register(router, dependencies, registry, workers)
    execution.register(router, dependencies, registry, workers, supervisor)
    diagnostics.register(router, dependencies, registry, workers, supervisor)
    checks.register(router, dependencies, registry, workers, supervisor)
    results.register(router, dependencies, registry, workers)
    reports.register(router, dependencies, registry, workers)
    comparisons.register(router, dependencies, registry, workers)
    regressions.register(router, dependencies, registry, workers)
    app.include_router(router)
    app.state.project_registry = registry
    app.state.dependencies = dependencies
    app.state.workers = workers
    app.state.execution_supervisor = supervisor

    return app


def create_app(config: LocalServerConfig, dependencies: ApiDependencies) -> LocalBoundary:
    """Construct the loopback boundary without opening resources or starting I/O."""
    session = SessionCapability.create()
    return LocalBoundary(create_inner_app(config, session, dependencies), config, session)
