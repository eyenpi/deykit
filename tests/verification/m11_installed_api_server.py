"""Serve the installed package with offline-only provider ports for M11/M12 browser QA.

This test-side composition deliberately imports only the installed ``deykit`` package.
It can run with Python isolated mode from outside a checkout, so a clean clone does not
depend on ignored qualification helpers or source-tree imports.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import socket
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import uvicorn

from deykit.api.app import create_app
from deykit.api.assets import AssetCatalog
from deykit.api.config import LocalServerConfig
from deykit.api.dependencies import ApiDependencies, ApiProjectSource
from deykit.api.recent import RecentProjectsStore
from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError
from deykit.contracts.ports import ChoiceCompiler, ProviderTransport, StoredRecord
from deykit.contracts.provider_configuration import ModelDescription
from deykit.contracts.records import (
    ChoiceDefinition,
    CompiledRequest,
    DispatchOutcome,
    ProviderProfile,
)
from deykit.providers.configuration import create_provider_operations
from deykit.providers.credentials import SecretStore
from deykit.runner.backends import FixtureBackend, ProviderBackends
from deykit.runner.ports import Backend, BackendFactory
from deykit.storage import FileProjectSource
from deykit.storage.demo_destination import FileDemoDestinationFactory
from deykit.storage.demo_staging import DemoStagingSource


class QualificationClock:
    """Stable timestamps with a real monotonic clock for worker deadlines."""

    def utc_now(self) -> str:
        return "2026-10-09T12:00:00Z"

    def monotonic(self) -> float:
        return time.monotonic()


class QualificationIds:
    """Produce deterministic-looking, collision-resistant IDs in a test namespace."""

    def __init__(self) -> None:
        self._namespace = uuid4().hex[:12]
        self._counter = 0

    def __call__(self) -> str:
        self._counter += 1
        return f"qualification-m10-{self._namespace}-{self._counter:06d}"


class FakeSecretStore(SecretStore):
    """In-memory credential port; never calls the OS keychain."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], str] = {}
        self.get_calls = 0
        self.set_calls = 0
        self.delete_calls = 0

    def get_password(self, service: str, username: str) -> str | None:
        self.get_calls += 1
        return self._values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.set_calls += 1
        self._values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.delete_calls += 1
        self._values.pop((service, username), None)


class FakeModelLister:
    """A single fake model-list response for the explicit no-inference check."""

    def __init__(self) -> None:
        self.calls = 0
        self.timeouts: list[float] = []

    async def models(
        self, profile: ProviderProfile, *, timeout_seconds: float
    ) -> tuple[ModelDescription, ...]:
        self.calls += 1
        self.timeouts.append(timeout_seconds)
        return (ModelDescription("fake-offline-model", "Qualification fixture", "2026-01-01"),)


@dataclass
class DispatchWitness:
    for_case_calls: int = 0
    dispatch_calls: int = 0
    for_case_by_case: dict[str, int] = field(default_factory=dict)
    dispatch_by_case: dict[str, int] = field(default_factory=dict)
    publish: Callable[[], None] | None = None

    def changed(self) -> None:
        if self.publish is not None:
            self.publish()


class WitnessTransport:
    """Count fixture dispatch and optionally hold its settlement at a test-only file barrier."""

    def __init__(
        self, transport: ProviderTransport, witness: DispatchWitness, case_id: str
    ) -> None:
        self._transport = transport
        self._witness = witness
        self._case_id = case_id

    async def dispatch(
        self, request: CompiledRequest, *, timeout_seconds: float
    ) -> DispatchOutcome:
        self._witness.dispatch_calls += 1
        self._witness.dispatch_by_case[self._case_id] = (
            self._witness.dispatch_by_case.get(self._case_id, 0) + 1
        )
        self._witness.changed()
        control = os.environ.get("DEYKIT_FIXTURE_CONTROL_DIRECTORY")
        if control is not None:
            directory = Path(control)
            hold = directory / (self._case_id + ".hold")
            if hold.is_file():
                (directory / (self._case_id + ".entered")).write_text("fixture\n")
                deadline = time.monotonic() + 20
                while hold.exists():
                    if time.monotonic() >= deadline:
                        raise RuntimeError("qualification_fixture_barrier_timeout")
                    await asyncio.sleep(0.05)
        return await self._transport.dispatch(request, timeout_seconds=timeout_seconds)


class WitnessBackend:
    """Forward only actual authored fixture transports; never construct a live adapter."""

    def __init__(self, fixture: FixtureBackend, witness: DispatchWitness) -> None:
        self._fixture = fixture
        self._witness = witness

    @property
    def compiler(self) -> ChoiceCompiler:
        return self._fixture.compiler

    def preflight(
        self,
        decision_id: str,
        dataset_id: str,
        definition: ChoiceDefinition | None = None,
    ) -> ServiceError | None:
        return self._fixture.preflight(decision_id, dataset_id, definition)

    def for_case(self, case_id: str) -> ProviderTransport:
        self._witness.for_case_calls += 1
        self._witness.for_case_by_case[case_id] = (
            self._witness.for_case_by_case.get(case_id, 0) + 1
        )
        self._witness.changed()
        return WitnessTransport(self._fixture.for_case(case_id), self._witness, case_id)


class OfflineBackendFactory:
    """Use the production fixture resolver and reject live adapters before credential use."""

    def __init__(self, source: ApiProjectSource, clock: QualificationClock) -> None:
        self._delegate = ProviderBackends(source, clock)
        self._dispatch = DispatchWitness()

    @property
    def witness(self) -> DispatchWitness:
        return self._dispatch

    def profile(self, provider_id: str | None, fixture_set_id: str | None) -> ProviderProfile:
        return self._delegate.profile(provider_id, fixture_set_id)

    def profile_captured(
        self,
        provider_id: str | None,
        fixture_set_id: str | None,
        records: tuple[StoredRecord, ...],
    ) -> ProviderProfile:
        return self._delegate.profile_captured(provider_id, fixture_set_id, records)

    @staticmethod
    def _reject_live(profile: ProviderProfile, fixture_set_id: str | None) -> None:
        if fixture_set_id is None or profile.adapter != "fixture":
            raise ServiceFailure(
                ServiceError(code="preflight_failed", reason="qualification_live_backend_forbidden")
            )

    def resolve(self, profile: ProviderProfile, fixture_set_id: str | None) -> Backend:
        self._reject_live(profile, fixture_set_id)
        backend = self._delegate.resolve(profile, fixture_set_id)
        if not isinstance(backend, FixtureBackend):
            raise ServiceFailure(
                ServiceError(code="preflight_failed", reason="qualification_live_backend_forbidden")
            )
        return WitnessBackend(backend, self._dispatch)

    def resolve_captured(
        self,
        profile: ProviderProfile,
        fixture_set_id: str | None,
        records: tuple[StoredRecord, ...],
    ) -> Backend:
        self._reject_live(profile, fixture_set_id)
        backend = self._delegate.resolve_captured(profile, fixture_set_id, records)
        if not isinstance(backend, FixtureBackend):
            raise ServiceFailure(
                ServiceError(code="preflight_failed", reason="qualification_live_backend_forbidden")
            )
        return WitnessBackend(backend, self._dispatch)


class LifespanWitness:
    """Observe the ASGI lifespan protocol without changing its behavior."""

    def __init__(self, app: Any) -> None:
        self._app = app
        self.startup_completed = False
        self.startup_error: str | None = None
        self.shutdown_completed = False
        self.shutdown_error: str | None = None

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "lifespan":
            await self._app(scope, receive, send)
            return

        async def observe(message: dict[str, Any]) -> None:
            message_type = message.get("type")
            if message_type == "lifespan.startup.complete":
                self.startup_completed = True
            elif message_type == "lifespan.startup.failed":
                self.startup_error = "lifespan.startup.failed"
            elif message_type == "lifespan.shutdown.complete":
                self.shutdown_completed = True
            elif message_type == "lifespan.shutdown.failed":
                self.shutdown_error = "lifespan.shutdown.failed"
            await send(message)

        try:
            await self._app(scope, receive, observe)
        except BaseException as error:
            phase = "shutdown" if self.startup_completed else "startup"
            error_type = type(error).__name__
            if phase == "startup":
                self.startup_error = error_type
            else:
                self.shutdown_error = error_type
            raise


class QualificationServer(uvicorn.Server):
    """Own one socket and publish lifecycle evidence after the app has shut down."""

    def __init__(
        self,
        config: uvicorn.Config,
        *,
        listener: socket.socket,
        ready_file: Path,
        origin: str,
        boundary: Any,
        lifespan: LifespanWitness,
        secret_store: FakeSecretStore,
        model_lister: FakeModelLister,
        backends: list[OfflineBackendFactory],
    ) -> None:
        super().__init__(config)
        self._listener = listener
        self._ready_file = ready_file
        self._origin = origin
        self._boundary = boundary
        self._lifespan = lifespan
        self._secret_store = secret_store
        self._model_lister = model_lister
        self._backends = backends

    def install_signal_handlers(self) -> None:
        # SIGTERM is handled explicitly below, keeping Uvicorn from replacing it.
        return

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        if self.started:
            _write_json(self._ready_file, {"origin": self._origin})

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        await super().shutdown(sockets=sockets)
        inner = self._boundary.app
        registry = inner.state.project_registry
        workers = inner.state.workers
        supervisor = inner.state.execution_supervisor
        pending = getattr(registry, "_pending", None)
        supervisor_sets = {
            "supervisor_tasks_empty": not supervisor._tasks,
            "supervisor_preparing_empty": not supervisor._preparing,
            "supervisor_runs_empty": not supervisor._runs,
            "supervisor_groups_empty": not supervisor._groups,
            "supervisor_run_tasks_empty": not supervisor._run_tasks,
            "supervisor_group_tasks_empty": not supervisor._group_tasks,
        }
        fixture_dispatch_by_case: Counter[str] = Counter()
        for_case_by_case: Counter[str] = Counter()
        for item in self._backends:
            fixture_dispatch_by_case.update(item.witness.dispatch_by_case)
            for_case_by_case.update(item.witness.for_case_by_case)
        witness = {
            "lifespan_startup_completed": self._lifespan.startup_completed,
            "lifespan_startup_error": self._lifespan.startup_error,
            "lifespan_shutdown_completed": self._lifespan.shutdown_completed,
            "lifespan_shutdown_error": self._lifespan.shutdown_error,
            "capability_active": self._boundary.session.active,
            "registry_empty": len(registry.list()) == 0,
            "registry_pending_empty": None if pending is None else pending == 0,
            "workers_idle": len(workers._tasks) == 0,
            "supervisor_idle": all(supervisor_sets.values()) and not supervisor._admitting,
            **supervisor_sets,
            "supervisor_admitting": supervisor._admitting,
            "supervisor_admission_closed": not supervisor._admitting,
            "lifespan_completed": self._lifespan.shutdown_completed,
            "capability_revoked": not self._boundary.session.active,
            "root_registry_empty": len(registry.list()) == 0,
            "root_registry_count": len(registry.list()),
            "worker_count": len(workers._tasks),
            "secret_store_get_calls": self._secret_store.get_calls,
            "secret_store_set_calls": self._secret_store.set_calls,
            "secret_store_delete_calls": self._secret_store.delete_calls,
            "model_list_calls": self._model_lister.calls,
            "model_timeouts": self._model_lister.timeouts,
            "model_list_inference_calls_contract": 0,
            "model_list_timeouts": self._model_lister.timeouts,
            "fixture_dispatch_calls": sum(item.witness.dispatch_calls for item in self._backends),
            "fixture_dispatch_by_case": dict(sorted(fixture_dispatch_by_case.items())),
            "live_dispatch_calls": 0,
            "all_resolved_backends_fixture_only": True,
            "for_case_calls": sum(item.witness.for_case_calls for item in self._backends),
            "for_case_by_case": dict(sorted(for_case_by_case.items())),
            "jev_api_key_present": "JEV_API_KEY" in os.environ,
        }
        _write_json(self._ready_file.with_suffix(".stopped.json"), witness)


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _dependencies(
    workspace: Path,
) -> tuple[ApiDependencies, FakeSecretStore, FakeModelLister, list[OfflineBackendFactory]]:
    clock = QualificationClock()
    ids = QualificationIds()
    secret_store = FakeSecretStore()
    model_lister = FakeModelLister()
    backend_factories: list[OfflineBackendFactory] = []

    def publish_counts() -> None:
        control = os.environ.get("DEYKIT_FIXTURE_CONTROL_DIRECTORY")
        if control is not None:
            path = Path(control) / "counts.json"
            temporary = path.with_suffix(".tmp")
            fixture_dispatch_by_case: Counter[str] = Counter()
            for_case_by_case: Counter[str] = Counter()
            for factory in backend_factories:
                fixture_dispatch_by_case.update(factory.witness.dispatch_by_case)
                for_case_by_case.update(factory.witness.for_case_by_case)
            _write_json(
                temporary,
                {
                    "fixture_dispatch_calls": sum(
                        f.witness.dispatch_calls for f in backend_factories
                    ),
                    "for_case_calls": sum(f.witness.for_case_calls for f in backend_factories),
                    "fixture_dispatch_by_case": dict(
                        sorted(fixture_dispatch_by_case.items())
                    ),
                    "for_case_by_case": dict(sorted(for_case_by_case.items())),
                    "live_dispatch_calls": 0,
                },
            )
            temporary.replace(path)

    def backend_factory(source: ApiProjectSource, selected_clock: Any) -> BackendFactory:
        factory = OfflineBackendFactory(source, selected_clock)
        backend_factories.append(factory)
        factory.witness.publish = publish_counts
        publish_counts()
        return factory

    publish_counts()

    dependencies = ApiDependencies(
        clock=clock,
        id_factory=ids,
        source_factory=lambda path, create: FileProjectSource(path, create=create),
        recent_store=RecentProjectsStore(clock, workspace / "recent-projects.json"),
        demo_staging_factory=DemoStagingSource,
        demo_destination_factory=FileDemoDestinationFactory(),
        provider_operations_factory=lambda source: create_provider_operations(
            source,
            environment={"M08_FAKE_ENV": "nonsecret-fake-environment-value"},
            os_store_factory=lambda: secret_store,
            model_lister=model_lister,
        ),
        backends_factory=backend_factory,
    )
    return dependencies, secret_store, model_lister, backend_factories


def serve_installed_api(workspace: Path, ready_file: Path) -> None:
    """Run the packaged app on one loopback listener until SIGTERM."""
    if "JEV_API_KEY" in os.environ:
        raise RuntimeError("qualification_refuses_live_provider_environment")
    workspace.mkdir(parents=True, exist_ok=True)
    ready_file.parent.mkdir(parents=True, exist_ok=True)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    listener.setblocking(False)
    host, port = listener.getsockname()
    authority = f"{host}:{port}"
    origin = f"http://{authority}"

    dependencies, secret_store, model_lister, backend_factories = _dependencies(workspace)
    boundary = create_app(
        LocalServerConfig(authority, origin, AssetCatalog.from_package()), dependencies
    )
    lifespan = LifespanWitness(boundary)
    config = uvicorn.Config(
        lifespan,
        host=host,
        port=port,
        workers=1,
        reload=False,
        proxy_headers=False,
        http="h11",
        ws=None,
        loop="asyncio",
        lifespan="on",
        access_log=False,
        timeout_graceful_shutdown=10,
        log_level="warning",
    )
    server = QualificationServer(
        config,
        listener=listener,
        ready_file=ready_file,
        origin=origin,
        boundary=boundary,
        lifespan=lifespan,
        secret_store=secret_store,
        model_lister=model_lister,
        backends=backend_factories,
    )

    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def stop_server(_signum: int, _frame: Any) -> None:
        server.should_exit = True

    signal.signal(signal.SIGTERM, stop_server)
    try:
        server.run(sockets=[listener])
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
        listener.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    args = parser.parse_args()
    serve_installed_api(args.workspace, args.ready_file)


if __name__ == "__main__":
    main()
