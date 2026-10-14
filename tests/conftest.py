"""Deny network access while retaining stdlib socketpair IPC on Windows."""

import re
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass

import pytest


@dataclass
class _PairFrame:
    listener: socket.socket | None = None
    endpoint: tuple[str, int] | None = None
    connect_used: bool = False


class _OfflineGuard:
    def __init__(self):
        self.original_pair = socket.socketpair
        self.original_bind = socket.socket.bind
        self.original_connect = socket.socket.connect
        self.local = threading.local()

    def frame(self):
        stack = getattr(self.local, "stack", ())
        return stack[-1] if stack else None

    @staticmethod
    def denied(*args, **kwargs):
        raise AssertionError("ordinary tests must not access the network")

    @staticmethod
    def endpoint(sock, address):
        if not isinstance(address, tuple) or len(address) < 2:
            return None
        host, port = address[:2]
        if type(port) is not int:
            return None
        if sock.family == socket.AF_INET and len(address) == 2 and host == "127.0.0.1":
            return host, port
        if sock.family == socket.AF_INET6 and host == "::1" and 2 <= len(address) <= 4:
            if all(type(field) is int and field == 0 for field in address[2:]):
                return host, port
        return None

    def pair(self, *args, **kwargs):
        stack = getattr(self.local, "stack", None)
        if stack is None:
            stack = self.local.stack = []
        frame = _PairFrame()
        stack.append(frame)
        try:
            return self.original_pair(*args, **kwargs)
        finally:
            assert stack.pop() is frame

    def bind(self, sock, address):
        result = self.original_bind(sock, address)
        frame = self.frame()
        if (
            frame is not None
            and frame.listener is None
            and sock.type == socket.SOCK_STREAM
            and self.endpoint(sock, address) in (("127.0.0.1", 0), ("::1", 0))
        ):
            frame.listener = sock
            frame.endpoint = self.endpoint(sock, sock.getsockname())
        return result

    def connect(self, sock, address):
        frame = self.frame()
        if frame is not None and frame.listener is not None:
            listener = frame.listener
            if (
                not frame.connect_used
                and listener.fileno() != -1
                and sock is not listener
                and sock.family == listener.family
                and sock.type == listener.type == socket.SOCK_STREAM
                and sock.proto == listener.proto
                and frame.endpoint is not None
                and self.endpoint(sock, address) == frame.endpoint
                and self.endpoint(listener, listener.getsockname()) == frame.endpoint
            ):
                frame.connect_used = True
                return self.original_connect(sock, address)
        return self.denied()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    guard = _OfflineGuard()

    # Plain functions preserve the socket instance supplied by method dispatch.
    def bind(sock, address):
        return guard.bind(sock, address)

    def connect(sock, address):
        return guard.connect(sock, address)

    monkeypatch.setattr(socket, "socketpair", guard.pair)
    monkeypatch.setattr(socket.socket, "bind", bind)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guard.denied)
    for name in (
        "create_connection",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
        "gethostbyaddr",
    ):
        monkeypatch.setattr(socket, name, guard.denied)
    return guard


@pytest.fixture
def plain_terminal_text() -> Callable[[str], str]:
    def strip_styles(text: str) -> str:
        return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)

    return strip_styles
