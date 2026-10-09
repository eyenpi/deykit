"""Serve the packaged local workspace on one explicit loopback socket."""

from __future__ import annotations

import asyncio
import signal
import socket
import threading
import webbrowser
from pathlib import Path
from typing import Annotated, cast

import typer
import uvicorn
from fastapi import FastAPI

from deykit.api.app import create_app
from deykit.api.assets import AssetCatalog
from deykit.api.config import LocalServerConfig
from deykit.api.dependencies import ApiDependencies
from deykit.api.recent import RecentProjectsStore
from deykit.api.runtime import SystemClock, new_id
from deykit.cli.context import CliState
from deykit.storage import FileProjectSource
from deykit.storage.demo_staging import DemoStagingSource


def register(root: typer.Typer) -> None:
    root.command("serve")(serve)


class _ReadyServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config, ready: threading.Event) -> None:
        super().__init__(config)
        self._ready = ready

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        self._ready.set()


def launch_local_server(
    project_path: Path | None,
    *,
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("invalid_local_port")
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(128)
        actual_port = listener.getsockname()[1]
        authority = f"127.0.0.1:{actual_port}"
        origin = f"http://{authority}"
        clock = SystemClock()
        dependencies = ApiDependencies(
            clock=clock,
            id_factory=new_id,
            source_factory=lambda path, create: FileProjectSource(path, create=create),
            recent_store=RecentProjectsStore(clock),
            demo_staging_factory=DemoStagingSource,
        )
        app = create_app(
            LocalServerConfig(authority, origin, AssetCatalog.from_package()), dependencies
        )
    except BaseException:
        listener.close()
        raise

    registry = cast(FastAPI, app.app).state.project_registry
    try:
        if project_path is not None:
            registry.register(
                "open",
                str(project_path.absolute()),
                name=None,
                operation_id=new_id(),
            )
    except BaseException:
        listener.close()
        registry.close_all()
        raise

    ready = threading.Event()
    config = uvicorn.Config(
        app,
        workers=1,
        reload=False,
        proxy_headers=False,
        forwarded_allow_ips="",
        http="h11",
        h11_max_incomplete_event_size=65536,
        ws="none",
        loop="asyncio",
        lifespan="on",
        access_log=False,
        timeout_graceful_shutdown=10,
        log_level="warning",
    )
    server = _ReadyServer(config, ready)
    failure: list[BaseException] = []

    def run() -> None:
        try:
            asyncio.run(server.serve(sockets=[listener]))
        except BaseException as error:
            failure.append(error)
            ready.set()

    thread = threading.Thread(target=run, name="deykit-local-api", daemon=True)
    previous_sigterm = None
    if threading.current_thread() is threading.main_thread():
        previous_sigterm = signal.getsignal(signal.SIGTERM)

        def stop_on_sigterm(_signum: int, _frame: object) -> None:
            server.should_exit = True

        signal.signal(signal.SIGTERM, stop_on_sigterm)
    try:
        thread.start()
        while not ready.wait(0.1):
            if not thread.is_alive():
                break
        if failure:
            raise failure[0]
        if not server.started:
            raise RuntimeError("local_server_start_failed")
        typer.echo(f"Deykit local workspace: {origin}")
        if open_browser:
            webbrowser.open(origin, new=2)
        while thread.is_alive():
            thread.join(timeout=0.25)
    except KeyboardInterrupt:
        server.should_exit = True
        thread.join()
    finally:
        listener.close()
        if thread.is_alive():
            server.should_exit = True
            thread.join()
        if not server.started:
            registry.close_all()
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
    if failure:
        raise failure[0]


def serve(
    ctx: typer.Context,
    port: Annotated[int, typer.Option("--port", min=0, max=65535)] = 8765,
    no_open: Annotated[bool, typer.Option("--no-open")] = False,
) -> None:
    state = ctx.find_root().obj
    if not isinstance(state, CliState):
        raise RuntimeError("CLI state unavailable")
    launch_local_server(state.explicit_project, port=port, open_browser=not no_open)
