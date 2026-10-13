"""Serve the installed package with offline-only provider ports for M11/M12 browser QA.

This test-side composition deliberately imports only the installed ``deykit`` package.
It can run with Python isolated mode from outside a checkout, so a clean clone does not
depend on ignored qualification helpers or source-tree imports.
"""

from __future__ import annotations

import argparse
import asyncio
import faulthandler
import hashlib
import json
import os
import signal
import socket
import stat
import threading
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
from deykit.storage.source import API_SOURCE_ADMISSION_TIMEOUT_SECONDS

_WITNESS_LOCK = threading.RLock()


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
    lock: Any = field(default_factory=lambda: _WITNESS_LOCK, repr=False)

    def record_dispatch(self, case_id: str) -> None:
        with self.lock:
            self.dispatch_calls += 1
            self.dispatch_by_case[case_id] = self.dispatch_by_case.get(case_id, 0) + 1
        self.changed()

    def record_for_case(self, case_id: str) -> None:
        with self.lock:
            self.for_case_calls += 1
            self.for_case_by_case[case_id] = self.for_case_by_case.get(case_id, 0) + 1
        self.changed()

    def changed(self) -> None:
        with self.lock:
            publish = self.publish
        if publish is not None:
            publish()


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
        self._witness.record_dispatch(self._case_id)
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
        self._witness.record_for_case(case_id)
        return WitnessTransport(self._fixture.for_case(case_id), self._witness, case_id)


class OfflineBackendFactory:
    """Use the production fixture resolver and reject live adapters before credential use."""

    def __init__(
        self,
        source: ApiProjectSource,
        clock: QualificationClock,
        witness_lock: Any | None = None,
    ) -> None:
        self._delegate = ProviderBackends(source, clock)
        self._dispatch = DispatchWitness(lock=witness_lock or _WITNESS_LOCK)

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


class ResumeObservation:
    """Persist a bounded, private trace for the two G resume requests."""

    def __init__(self, control_directory: Path, *, enabled: bool) -> None:
        self.enabled = enabled
        self.started_at = time.monotonic()
        self.events: list[dict[str, Any]] = []
        self.ordinal = 0
        self.dump_arms = 0
        self.terminal_events: list[dict[str, Any]] = []
        self.worker_snapshots: list[dict[str, Any]] = []
        self._boundary_app: Any | None = None
        self._future_refs: dict[int, dict[str, Any]] = {}
        self._worker_future_ids: set[int] = set()
        self._owner_future_ids: set[int] = set()
        self._closed = False
        self._trace_path: Path | None = None
        self._temporary_trace_path: Path | None = None
        self._stack_file: Any | None = None
        if not enabled:
            return

        directory = control_directory.lstat()
        getuid = getattr(os, "getuid", None)
        if (
            not stat.S_ISDIR(directory.st_mode)
            or (getuid is not None and directory.st_uid != getuid())
            or stat.S_IMODE(directory.st_mode) != 0o700
        ):
            raise RuntimeError("resume_observation_directory_unsafe")

        nofollow = getattr(os, "O_NOFOLLOW", 0)
        trace_path = control_directory / "resume-observation.json"
        temporary_trace_path = control_directory / "resume-observation.json.tmp"
        stack_path = control_directory / "resume-observation-stack.private"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow
        try:
            stack_fd = os.open(stack_path, flags, 0o600)
            os.fchmod(stack_fd, 0o600)
            self._stack_file = os.fdopen(stack_fd, "wb", buffering=0)
            self._trace_path = trace_path
            self._temporary_trace_path = temporary_trace_path
            self._persist()
        except BaseException:
            if self._stack_file is not None:
                self._stack_file.close()
                self._stack_file = None
            raise

    def admit(self) -> int | None:
        if not self.enabled or self.ordinal >= 2:
            return None
        self.ordinal += 1
        ordinal = self.ordinal
        self._record(ordinal, "admitted")
        if self.dump_arms < 2 and self._stack_file is not None:
            faulthandler.dump_traceback_later(
                8,
                repeat=False,
                file=self._stack_file,
            )
            self.dump_arms += 1
        return ordinal

    def response_started(self, ordinal: int, status: int) -> None:
        self._record(ordinal, "response_started", status=status)

    def body_complete(self, ordinal: int, digest: str) -> None:
        self._record(ordinal, "body_complete", sha256=digest)

    def bind_boundary(self, app: Any) -> None:
        self._boundary_app = app

    def capture_workers(
        self,
        app: Any,
        *,
        ordinal: int | None,
        checkpoint: str,
        scope_path: Any = None,
    ) -> None:
        if not self.enabled or self._closed:
            return
        if checkpoint == "shutdown":
            self._snapshot_retained(ordinal=None, checkpoint=checkpoint)
            return
        inner = getattr(app, "app", None)
        state = getattr(inner, "state", None)
        supervisor = getattr(state, "execution_supervisor", None)
        workers = getattr(state, "workers", None)
        registration_id: str | None = None
        group_id: str | None = None
        if ordinal is not None:
            # The request path is used only to look up the supervisor's private owner.
            # It is never copied into the evidence file.
            if isinstance(scope_path, str):
                segments = scope_path.split("/")
                if len(segments) == 8 and _is_diagnostic_resume_path(scope_path):
                    registration_id, group_id = segments[4], segments[6]

        owner = None
        if supervisor is not None and registration_id and group_id:
            owner = getattr(supervisor, "_group_tasks", {}).get((registration_id, group_id))
        if owner is not None and id(owner) not in self._owner_future_ids:
            if len(self._owner_future_ids) < 2:
                self._owner_future_ids.add(id(owner))
                self._observe_future(owner, ordinal=ordinal, owner=True, worker_index=None)

        worker_list: tuple[Any, ...] | None = None
        if workers is not None:
            try:
                worker_list = tuple(workers._tasks)
            except (AttributeError, TypeError):
                worker_list = None
        available_slots = max(0, 16 - len(self._worker_future_ids))
        worker_overflow = 0
        if worker_list is not None:
            for future in worker_list:
                identity = id(future)
                if identity in self._worker_future_ids:
                    continue
                if available_slots == 0:
                    worker_overflow += 1
                    continue
                self._worker_future_ids.add(identity)
                worker_index = len(self._worker_future_ids)
                self._observe_future(
                    future,
                    ordinal=ordinal,
                    owner=False,
                    worker_index=worker_index,
                )
                available_slots -= 1

        owner_identity = id(owner) if owner is not None else None
        known_refs = [
            {
                "owner": bool(item["owner"]),
                "worker_index": item["worker_index"],
                "state": self._future_state(item["future"]),
            }
            for item in self._future_refs.values()
        ]
        snapshot: dict[str, Any] = {
            "checkpoint": checkpoint,
            "ordinal": ordinal,
            "owner_lookup": "available" if supervisor is not None else "unavailable",
            "owner_present": None if supervisor is None else owner is not None,
            "owner_observed": (
                None
                if supervisor is None
                else owner_identity in self._owner_future_ids
                if owner_identity is not None
                else False
            ),
            "worker_list": "available" if worker_list is not None else "unavailable",
            "worker_count": len(worker_list) if worker_list is not None else None,
            "worker_overflow_count": worker_overflow if worker_list is not None else None,
            "elapsed_ms": max(0, round((time.monotonic() - self.started_at) * 1000)),
            "futures": known_refs,
        }
        if len(self.worker_snapshots) < 3:
            self.worker_snapshots.append(snapshot)
            self._persist()

    def _snapshot_retained(self, *, ordinal: int | None, checkpoint: str) -> None:
        snapshot: dict[str, Any] = {
            "checkpoint": checkpoint,
            "ordinal": ordinal,
            "owner_lookup": "unrequested",
            "owner_present": None,
            "owner_observed": None,
            "worker_list": "unrequested",
            "worker_count": None,
            "worker_overflow_count": None,
            "elapsed_ms": max(0, round((time.monotonic() - self.started_at) * 1000)),
            "futures": [
                {
                    "owner": bool(item["owner"]),
                    "worker_index": item["worker_index"],
                    "state": self._future_state(item["future"]),
                }
                for item in self._future_refs.values()
            ],
        }
        if len(self.worker_snapshots) < 3:
            self.worker_snapshots.append(snapshot)
            self._persist()

    def _observe_future(
        self,
        future: Any,
        *,
        ordinal: int | None,
        owner: bool,
        worker_index: int | None,
    ) -> None:
        identity = id(future)
        existing = self._future_refs.get(identity)
        if existing is not None:
            if worker_index is not None and existing["worker_index"] is None:
                existing["worker_index"] = worker_index
            existing["owner"] = existing["owner"] or owner
            return
        self._future_refs[identity] = {
            "future": future,
            "ordinal": ordinal,
            "owner": owner,
            "worker_index": worker_index,
        }
        future.add_done_callback(lambda completed: self._future_done(identity, completed))

    @staticmethod
    def _future_state(future: Any) -> str:
        try:
            if not future.done():
                return "pending"
            if future.cancelled():
                return "cancelled"
            error = future.exception()
        except asyncio.CancelledError:
            return "cancelled"
        except BaseException:
            return "unclassified_failure"
        if error is None:
            return "returned"
        if isinstance(error, asyncio.CancelledError):
            return "cancelled"
        if isinstance(error, ServiceFailure):
            return "service_failure"
        return "unclassified_failure"

    def _future_done(self, identity: int, future: Any) -> None:
        if self._closed or len(self.terminal_events) >= 18:
            return
        observed = self._future_refs.get(identity)
        if observed is None:
            return
        event: dict[str, Any] = {
            "ordinal": observed["ordinal"],
            "owner": bool(observed["owner"]),
            "worker_index": observed["worker_index"],
            "state": self._future_state(future),
            "elapsed_ms": max(0, round((time.monotonic() - self.started_at) * 1000)),
        }
        self.terminal_events.append(event)
        self._persist()

    def _record(
        self,
        ordinal: int,
        stage: str,
        *,
        status: int | None = None,
        sha256: str | None = None,
    ) -> None:
        if len(self.events) >= 6:
            return
        event: dict[str, Any] = {
            "ordinal": ordinal,
            "stage": stage,
            "elapsed_ms": max(0, round((time.monotonic() - self.started_at) * 1000)),
        }
        if status is not None:
            event["status"] = status
        if sha256 is not None:
            event["sha256"] = sha256
        self.events.append(event)
        self._persist()

    def _persist(self) -> None:
        if self._trace_path is None or self._temporary_trace_path is None:
            return
        payload = json.dumps(
            {
                "schema_version": 1,
                "events": self.events,
                "worker_snapshots": self.worker_snapshots,
                "terminal_events": self.terminal_events,
            },
            separators=(",", ":"),
        ).encode("ascii")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self._temporary_trace_path, flags, 0o600)
        try:
            os.fchmod(fd, 0o600)
            offset = 0
            while offset < len(payload):
                offset += os.write(fd, payload[offset:])
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(self._temporary_trace_path, self._trace_path)

    def close(self) -> None:
        if self._closed:
            return
        if self._boundary_app is not None:
            self.capture_workers(self._boundary_app, ordinal=None, checkpoint="shutdown")
        self._closed = True
        if self._stack_file is not None:
            faulthandler.cancel_dump_traceback_later()
            self._stack_file.close()
            self._stack_file = None


class ResumeObservationApp:
    """Observe only two diagnostic resume responses without changing app behavior."""

    def __init__(self, app: Any, observation: ResumeObservation) -> None:
        self._app = app
        self._observation = observation
        self._observation.bind_boundary(app)

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if (
            not self._observation.enabled
            or scope.get("type") != "http"
            or scope.get("method") != "POST"
            or not _is_diagnostic_resume_path(scope.get("path"))
        ):
            await self._app(scope, receive, send)
            return

        ordinal = self._observation.admit()
        if ordinal is None:
            await self._app(scope, receive, send)
            return

        digest = hashlib.sha256()

        async def observe(message: dict[str, Any]) -> None:
            message_type = message.get("type")
            if message_type == "http.response.start":
                status = message.get("status")
                await send(message)
                if isinstance(status, int) and 100 <= status <= 599:
                    self._observation.response_started(ordinal, status)
                    self._observation.capture_workers(
                        self._app,
                        ordinal=ordinal,
                        checkpoint="response_boundary",
                        scope_path=scope.get("path"),
                    )
                return
            if message_type == "http.response.body":
                body = message.get("body", b"")
                if isinstance(body, bytes):
                    digest.update(body)
                body_complete = not message.get("more_body", False)
                await send(message)
                if body_complete:
                    self._observation.body_complete(ordinal, digest.hexdigest())
                return
            await send(message)

        await self._app(scope, receive, observe)


def _is_diagnostic_resume_path(path: Any) -> bool:
    if not isinstance(path, str):
        return False
    segments = path.split("/")
    return (
        len(segments) == 8
        and segments[:3] == ["", "api", "v1"]
        and segments[3] == "projects"
        and bool(segments[4])
        and segments[5] == "diagnostics"
        and bool(segments[6])
        and segments[7] == "resume"
    )


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
        with _WITNESS_LOCK:
            fixture_dispatch_by_case: Counter[str] = Counter()
            for_case_by_case: Counter[str] = Counter()
            fixture_dispatch_calls = 0
            for_case_calls = 0
            for item in self._backends:
                fixture_dispatch_calls += item.witness.dispatch_calls
                for_case_calls += item.witness.for_case_calls
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
            "fixture_dispatch_calls": fixture_dispatch_calls,
            "fixture_dispatch_by_case": dict(sorted(fixture_dispatch_by_case.items())),
            "live_dispatch_calls": 0,
            "all_resolved_backends_fixture_only": True,
            "for_case_calls": for_case_calls,
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
            with _WITNESS_LOCK:
                fixture_dispatch_by_case: Counter[str] = Counter()
                for_case_by_case: Counter[str] = Counter()
                fixture_dispatch_calls = 0
                for_case_calls = 0
                for factory in backend_factories:
                    fixture_dispatch_calls += factory.witness.dispatch_calls
                    for_case_calls += factory.witness.for_case_calls
                    fixture_dispatch_by_case.update(factory.witness.dispatch_by_case)
                    for_case_by_case.update(factory.witness.for_case_by_case)
                snapshot = {
                    "fixture_dispatch_calls": fixture_dispatch_calls,
                    "for_case_calls": for_case_calls,
                    "fixture_dispatch_by_case": dict(sorted(fixture_dispatch_by_case.items())),
                    "for_case_by_case": dict(sorted(for_case_by_case.items())),
                    "live_dispatch_calls": 0,
                }
                _write_json(temporary, snapshot)
                temporary.replace(path)

    def backend_factory(source: ApiProjectSource, selected_clock: Any) -> BackendFactory:
        factory = OfflineBackendFactory(source, selected_clock, _WITNESS_LOCK)
        with _WITNESS_LOCK:
            backend_factories.append(factory)
            factory.witness.publish = publish_counts
        publish_counts()
        return factory

    publish_counts()

    dependencies = ApiDependencies(
        clock=clock,
        id_factory=ids,
        source_factory=lambda path, create: FileProjectSource(
            path,
            create=create,
            admission_timeout_seconds=API_SOURCE_ADMISSION_TIMEOUT_SECONDS,
        ),
        recent_store=RecentProjectsStore(clock, workspace / "recent-projects.json"),
        demo_staging_factory=DemoStagingSource,
        demo_destination_factory=FileDemoDestinationFactory(
            admission_timeout_seconds=API_SOURCE_ADMISSION_TIMEOUT_SECONDS
        ),
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
    observe_resume = os.environ.get("DEYKIT_G_RESUME_OBSERVATION") == "1"
    control_directory = os.environ.get("DEYKIT_FIXTURE_CONTROL_DIRECTORY")
    if observe_resume and not control_directory:
        raise RuntimeError("resume_observation_directory_missing")
    resume_observation = ResumeObservation(
        Path(control_directory) if control_directory else Path("."),
        enabled=observe_resume,
    )
    lifespan = LifespanWitness(ResumeObservationApp(boundary, resume_observation))
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
        resume_observation.close()
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
