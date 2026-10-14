"""Binding-level byte/quota regressions; native Windows evidence is separate."""

import ctypes as c

import pytest

from deykit.application.errors import ServiceFailure
from deykit.storage._win32 import DWORD, FileInfo, Handle, Native


class ReadFixture(Native):
    def __init__(self, body: bytes, *, observed_size: int | None = None, short_read: int = 0):
        self.body = body
        self.observed_size = len(body) if observed_size is None else observed_size
        self.short_read = short_read
        self.offset = 0
        self.requests: list[int] = []
        self._read = self.read_chunk

    def inspect(self, handle, *, directory):
        assert not directory
        return FileInfo(False, self.observed_size)

    def read_chunk(self, _handle, buffer, size, count, _overlapped):
        self.requests.append(size)
        chunk = self.body[self.offset : self.offset + (min(size, self.short_read) or size)]
        if chunk:
            c.memmove(buffer, chunk, len(chunk))
        c.cast(count, c.POINTER(DWORD))[0] = len(chunk)
        self.offset += len(chunk)
        return True


@pytest.mark.parametrize("body", [b"", b"tiny\x00record", b"x" * 131073])
def test_read_retains_every_byte_including_nuls_and_short_reads(body):
    api = ReadFixture(body, short_read=313)
    assert api.read(Handle(api, 1), len(body)) == body
    assert api.offset == len(body)


def test_small_records_use_one_small_scratch_buffer(monkeypatch):
    allocations = []
    original = c.create_string_buffer

    def record_allocation(size):
        allocations.append(size)
        return original(size)

    monkeypatch.setattr(c, "create_string_buffer", record_allocation)
    api = ReadFixture(b'{"schema_version":1}')
    assert api.read(Handle(api, 1), 16 * 1024 * 1024) == api.body
    assert len(allocations) == 1
    assert allocations[0] <= 8192


def test_observed_oversize_fails_before_read():
    api = ReadFixture(b"x" * 17)
    with pytest.raises(ServiceFailure) as failure:
        api.read(Handle(api, 1), 16)
    assert failure.value.error.reason == "record_resource_limit"
    assert api.requests == []


def test_growth_after_inspection_still_fails_at_limit():
    api = ReadFixture(b"x" * 17, observed_size=2, short_read=3)
    with pytest.raises(ServiceFailure) as failure:
        api.read(Handle(api, 1), 16)
    assert failure.value.error.reason == "record_resource_limit"
    assert api.offset == 17


def test_impossible_native_count_cannot_read_past_the_buffer():
    api = ReadFixture(b"small")

    def corrupt_count(_handle, _buffer, size, count, _overlapped):
        c.cast(count, c.POINTER(DWORD))[0] = size + 1
        return True

    api._read = corrupt_count
    with pytest.raises(OSError, match="Invalid storage read count"):
        api.read(Handle(api, 1), 32)
