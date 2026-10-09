"""Actual h11 parsing and exact-authority enforcement over the fixture's sole port."""

import json
import socket

import pytest


def exchange(address: tuple[str, int], request: bytes) -> tuple[int, bytes]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        connection.connect(address)
        connection.sendall(request)
        chunks = []
        while chunk := connection.recv(65536):
            chunks.append(chunk)
    response = b"".join(chunks)
    return int(response.split(b" ", 2)[1]), response


@pytest.mark.parametrize(
    "host,status",
    [
        (b"", 400),
        (b"Host: evil.example\r\n", 403),
        (b"Host: 127.0.0.1:9\r\n", 403),
        (b"Host: u@host\r\n", 400),
        (b"Host: localhost.\r\n", 403),
    ],
)
def test_real_host_parser(local_server: tuple[str, int], host: bytes, status: int) -> None:
    actual, response = exchange(
        local_server,
        b"GET /api/v1/projects/recent HTTP/1.1\r\n" + host + b"Connection: close\r\n\r\n",
    )
    assert actual == status
    assert b"<html" not in response


def test_duplicate_host_and_bootstrap(local_server: tuple[str, int]) -> None:
    authority = f"127.0.0.1:{local_server[1]}".encode()
    host = b"Host: " + authority + b"\r\n"
    assert (
        exchange(local_server, b"GET / HTTP/1.1\r\n" + host + host + b"Connection: close\r\n\r\n")[
            0
        ]
        == 400
    )
    body = b'{"schema_version":1}'
    request = (
        b"POST /api/v1/session/bootstrap HTTP/1.1\r\n"
        + host
        + b"Origin: http://"
        + authority
        + b"\r\nX-Deykit-Bootstrap: 1\r\nContent-Type: application/json\r\n"
        + b"Content-Length: 20\r\nConnection: close\r\n\r\n"
        + body
    )
    status, response = exchange(local_server, request)
    assert status == 200
    envelope = json.loads(response.partition(b"\r\n\r\n")[2])
    token = envelope["data"]["capability"].encode()
    assert len(token) == 43
    protected = (
        b"GET /api/v1/projects/recent HTTP/1.1\r\n"
        + host
        + (b"X-Deykit-Capability: " + token + b"\r\nConnection: close\r\n\r\n")
    )
    assert exchange(local_server, protected)[0] == 200
    # Forwarded headers cannot override the singleton bound authority.
    bad = protected.replace(host, b"Host: evil.example\r\nForwarded: host=" + authority + b"\r\n")
    assert exchange(local_server, bad)[0] == 403


def test_local_fixture_preserves_outbound_guard(local_server: tuple[str, int]) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        with pytest.raises(AssertionError, match="ordinary tests"):
            connection.connect(("127.0.0.1", 1))
        with pytest.raises(AssertionError, match="ordinary tests"):
            connection.connect(("192.0.2.1", local_server[1]))
    with pytest.raises(AssertionError, match="ordinary tests"):
        socket.create_connection(local_server)
