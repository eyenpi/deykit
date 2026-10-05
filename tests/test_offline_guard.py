"""Offline guard oracles use real sockets, including the default Windows loop."""

import asyncio
import socket
import threading

import pytest

MESSAGE = "ordinary tests must not access the network"


def denied(call):
    with pytest.raises(AssertionError, match=MESSAGE):
        call()


def test_default_asyncio_and_cancellation_cleanup():
    async def value():
        return "authored"

    assert asyncio.run(value()) == "authored"
    assert asyncio.run(value()) == "authored"
    cleaned = []

    async def child():
        try:
            await asyncio.Future()
        finally:
            cleaned.append("closed")

    async def cancel():
        task = asyncio.create_task(child())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel())
    assert cleaned == ["closed"]


def test_real_pair_bidirectional_and_no_leaked_allowance():
    left, right = socket.socketpair()
    try:
        left.settimeout(2)
        right.settimeout(2)
        left.sendall(b"left")
        assert right.recv(4) == b"left"
        right.sendall(b"right")
        assert left.recv(5) == b"right"
    finally:
        left.close()
        right.close()
    with socket.socket() as client:
        denied(lambda: client.connect(("127.0.0.1", 9)))


def test_all_network_routes_denied_before_forwarding(no_network):
    forwarded = []
    no_network.original_connect = lambda *args: forwarded.append(args)
    for address in (("192.0.2.1", 443), ("127.0.0.1", 9), ("localhost", 9)):
        with socket.socket() as client:
            denied(lambda address=address: client.connect(address))
            denied(lambda address=address: client.connect_ex(address))
    if socket.has_ipv6:
        with socket.socket(socket.AF_INET6) as client:
            denied(lambda: client.connect(("2001:db8::1", 443)))
            denied(lambda: client.connect(("::1", 9)))
    denied(lambda: socket.create_connection(("127.0.0.1", 9)))
    denied(lambda: socket.getaddrinfo("example.invalid", 443))
    denied(lambda: socket.gethostbyname("example.invalid"))
    denied(lambda: socket.gethostbyname_ex("example.invalid"))
    denied(lambda: socket.gethostbyaddr("192.0.2.1"))
    assert forwarded == []


def test_direct_listener_and_different_pair_listener_denied(no_network):
    with socket.socket() as unrelated:
        unrelated.bind(("127.0.0.1", 0))
        unrelated.listen()
        with socket.socket() as client:
            denied(lambda: client.connect(unrelated.getsockname()))

        def injected():
            with socket.socket() as listener, socket.socket() as client:
                listener.bind(("127.0.0.1", 0))
                listener.listen()
                denied(lambda: client.connect(unrelated.getsockname()))
                client.connect(listener.getsockname())
                peer, _ = listener.accept()
                peer.close()
                denied(lambda: client.connect(listener.getsockname()))
            return "injected"

        no_network.original_pair = injected
        assert socket.socketpair() == "injected"


@pytest.mark.parametrize("family", [socket.AF_INET, socket.AF_INET6])
def test_fallback_exact_endpoint_and_socket_constraints(no_network, family):
    if family == socket.AF_INET6 and not socket.has_ipv6:
        pytest.skip("IPv6 sockets unavailable")
    host = "127.0.0.1" if family == socket.AF_INET else "::1"

    def fallback():
        with socket.socket(family) as listener, socket.socket(family) as client:
            listener.bind((host, 0))
            listener.listen()
            endpoint = listener.getsockname()
            denied(lambda: listener.connect(endpoint))
            denied(lambda: client.connect((host, endpoint[1] + 1)))
            if family == socket.AF_INET6:
                denied(lambda: client.connect((host, endpoint[1], 0, 1)))
            with socket.socket(family, socket.SOCK_DGRAM) as datagram:
                denied(lambda: datagram.connect(endpoint))
            client.connect((host, endpoint[1]))
            peer, _ = listener.accept()
            peer.close()
            denied(lambda: client.connect(endpoint))

    no_network.original_pair = fallback
    socket.socketpair()


def test_connect_allowance_consumed_before_exception(no_network):
    calls = []

    def fail(*args):
        calls.append(args)
        raise BlockingIOError()

    no_network.original_connect = fail

    def fallback():
        with socket.socket() as listener, socket.socket() as client:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            with pytest.raises(BlockingIOError):
                client.connect(listener.getsockname())
            denied(lambda: client.connect(listener.getsockname()))

    no_network.original_pair = fallback
    socket.socketpair()
    assert len(calls) == 1


def test_nested_baseexception_cleanup_restores_parent(no_network):
    class Stop(BaseException):
        pass

    def failing():
        with socket.socket() as nested:
            nested.bind(("127.0.0.1", 0))
            raise Stop()

    def outer():
        with socket.socket() as listener, socket.socket() as client:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            no_network.original_pair = failing
            with pytest.raises(Stop):
                socket.socketpair()
            client.connect(listener.getsockname())
            peer, _ = listener.accept()
            peer.close()
        raise Stop()

    no_network.original_pair = outer
    with pytest.raises(Stop):
        socket.socketpair()
    with socket.socket() as client:
        denied(lambda: client.connect(("127.0.0.1", 9)))
        denied(lambda: client.connect(("192.0.2.1", 443)))
    denied(lambda: socket.getaddrinfo("example.invalid", 80))


def test_listener_retained_and_first_binding_only(no_network):
    def fallback():
        with socket.socket() as first, socket.socket() as second, socket.socket() as client:
            first.bind(("127.0.0.1", 0))
            second.bind(("127.0.0.1", 0))
            denied(lambda: client.connect(second.getsockname()))
            endpoint = first.getsockname()
            first.close()
            denied(lambda: client.connect(endpoint))

    no_network.original_pair = fallback
    socket.socketpair()


def test_other_thread_denied_while_pair_constructs(no_network):
    ready, release = threading.Event(), threading.Event()
    failures = []
    endpoints = []

    def constructing():
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            endpoints.append(listener.getsockname())
            ready.set()
            assert release.wait(5)

    def worker():
        try:
            socket.socketpair()
        except BaseException as error:
            failures.append(error)

    no_network.original_pair = constructing
    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert ready.wait(5)
        with socket.socket() as client:
            denied(lambda: client.connect(endpoints[0]))
            denied(lambda: client.connect(("192.0.2.1", 443)))
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and failures == []
