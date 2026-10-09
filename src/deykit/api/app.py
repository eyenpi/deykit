"""Construct the strict Phase A session/assets app; service routes remain gated."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response

from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError

from .config import LocalServerConfig
from .dependencies import ApiDependencies
from .errors import TransportFailure, error_response
from .registry import ProjectRegistry
from .routes.session import register as register_session
from .runtime import TrackedWorkers
from .security import LocalBoundary
from .session import SessionCapability


def create_inner_app(
    config: LocalServerConfig,
    session: SessionCapability,
    dependencies: ApiDependencies,
) -> FastAPI:
    registry = ProjectRegistry(dependencies, max_registrations=config.max_registrations)
    workers = TrackedWorkers()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            session.revoke()
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
    from .routes import projects

    projects.register(router, dependencies, registry, workers)
    app.include_router(router)
    app.state.project_registry = registry
    app.state.dependencies = dependencies
    app.state.workers = workers

    async def asset(request: Request) -> Response:
        name = request.url.path.removeprefix("/") or "index.html"
        entry = config.ui_assets.assets.get(name)
        if entry is None:
            return error_response(TransportFailure(404, "not_found", "route_not_found"))
        return Response(entry.body, headers={"content-type": entry.content_type})

    app.add_route("/", asset, methods=["GET", "HEAD"], include_in_schema=False)
    for name in config.ui_assets.assets:
        app.add_route(f"/{name}", asset, methods=["GET", "HEAD"], include_in_schema=False)
    return app


def create_app(config: LocalServerConfig, dependencies: ApiDependencies) -> LocalBoundary:
    """Construct the loopback boundary without opening resources or starting I/O."""
    if "index.html" not in config.ui_assets.assets:
        raise ServiceFailure(ServiceError(code="preflight_failed", reason="ui_assets_unavailable"))
    session = SessionCapability.create()
    return LocalBoundary(create_inner_app(config, session, dependencies), config, session)
