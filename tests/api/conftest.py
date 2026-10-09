"""Permit a single explicitly bound numeric loopback port only during its fixture."""

import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
import uvicorn

from deykit.api.app import create_app
from deykit.api.assets import AssetCatalog
from deykit.api.config import LocalServerConfig
from deykit.api.dependencies import ApiDependencies
from deykit.api.recent import RecentProject
from deykit.api.runtime import SystemClock, new_id
from deykit.contracts.ports import Clock
from deykit.storage.demo_staging import DemoStagingSource
from deykit.storage.demo_destination import FileDemoDestinationFactory

# Captured at collection, before the root autouse fixture installs its network denial.
# This is never a blanket restore: admission below compares exact family and address.
_SOCKET_CONNECT = socket.socket.connect


class EmptyRecentProjects:
    last_warning: str | None = None

    def list(self) -> tuple[RecentProject, ...]:
        return ()

    def remember(self, path: str, project_id: str, name: str) -> str | None:
        return None


def api_dependencies() -> ApiDependencies:
    clock: Clock = SystemClock()

    def forbidden_source(path, create):
        raise AssertionError("security-only socket tests must not open projects")

    return ApiDependencies(
        clock=clock,
        id_factory=new_id,
        source_factory=forbidden_source,
        recent_store=EmptyRecentProjects(),
        demo_staging_factory=DemoStagingSource,
        demo_destination_factory=FileDemoDestinationFactory(),
    )


@pytest.fixture
def local_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, int]]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(32)
    listener.setblocking(False)
    port = listener.getsockname()[1]
    address = ("127.0.0.1", port)
    denied = socket.socket.connect

    def connect(sock: socket.socket, target: Any) -> None:
        if sock.family == socket.AF_INET and target == address:
            return _SOCKET_CONNECT(sock, target)
        return denied(sock, target)

    monkeypatch.setattr(socket.socket, "connect", connect)
    config = LocalServerConfig(
        f"127.0.0.1:{port}", f"http://127.0.0.1:{port}", AssetCatalog.from_package()
    )
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(config, api_dependencies()),
            workers=1,
            reload=False,
            proxy_headers=False,
            forwarded_allow_ips="",
            http="h11",
            ws="none",
            loop="asyncio",
            lifespan="on",
            access_log=False,
            log_level="critical",
            timeout_graceful_shutdown=10,
            h11_max_incomplete_event_size=65536,
        )
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    try:
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise AssertionError("local test server did not start")
            time.sleep(0.01)
        yield address
    finally:
        server.should_exit = True
        thread.join(5)
        listener.close()
        assert not thread.is_alive(), "local test server did not settle"
