"""Native Windows calls, isolated here; imports are safe on non-Windows hosts.

HANDLEs never become CRT descriptors. All structures use Windows fixed-width fields,
including when imported by POSIX static checks. See architecture/storage.md for sources.
"""

from __future__ import annotations

import ctypes as c
import errno
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from deykit.storage.errors import fail

_windows_ctypes: Any = c

DWORD = c.c_uint32
HANDLE = c.c_void_p
DELETE = 0x10000
READ = 0x80000000
WRITE = 0x40000000
DIRECTORY_ACCESS = 0x100081  # SYNCHRONIZE | FILE_READ_ATTRIBUTES | FILE_LIST_DIRECTORY
SHARE_RW = 3
SHARE_ALL = 7
OPEN = 1
CREATE = 2
OPEN_IF = 3


class _UnicodeString(c.Structure):
    _fields_ = [("length", c.c_uint16), ("maximum", c.c_uint16), ("buffer", c.c_void_p)]


class _ObjectAttributes(c.Structure):
    _fields_ = [
        ("length", DWORD),
        ("root", HANDLE),
        ("name", c.POINTER(_UnicodeString)),
        ("attributes", DWORD),
        ("security", c.c_void_p),
        ("quality", c.c_void_p),
    ]


class _IoStatus(c.Structure):
    _fields_ = [("status", c.c_void_p), ("information", c.c_size_t)]


class _FileInfo(c.Structure):
    _fields_ = [
        ("attributes", DWORD),
        ("times", DWORD * 6),
        ("volume", DWORD),
        ("size_high", DWORD),
        ("size_low", DWORD),
        ("links", DWORD),
        ("index_high", DWORD),
        ("index_low", DWORD),
    ]


class _Rename(c.Structure):
    _fields_ = [
        ("replace", DWORD),
        ("root", HANDLE),
        ("length", DWORD),
        ("name", c.c_uint16 * 1),
    ]


class _Overlapped(c.Structure):
    _fields_ = [
        ("internal", c.c_size_t),
        ("internal_high", c.c_size_t),
        ("offset", DWORD),
        ("offset_high", DWORD),
        ("event", HANDLE),
    ]


@dataclass(frozen=True)
class FileInfo:
    directory: bool
    size: int


class Handle:
    def __init__(self, api: Native, value: int) -> None:
        self._api = api
        self._value: int | None = value

    @property
    def value(self) -> int:
        if self._value is None:
            raise OSError(errno.EBADF, "Closed storage handle")
        return self._value

    def close(self) -> None:
        if self._value is not None:
            value, self._value = self._value, None
            self._api.close(value)

    def __enter__(self) -> Handle:
        _ = self.value
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class Native:
    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("Windows storage is unavailable on this platform")
        self._kernel = _windows_ctypes.WinDLL("kernel32", use_last_error=True)
        self._nt = _windows_ctypes.WinDLL("ntdll", use_last_error=True)
        # Dynamic ctypes functions are confined to this typed adapter.
        self._create = self._bind(
            self._kernel,
            "CreateFileW",
            HANDLE,
            [c.c_wchar_p, DWORD, DWORD, c.c_void_p, DWORD, DWORD, HANDLE],
        )
        self._close = self._bind(self._kernel, "CloseHandle", c.c_int, [HANDLE])
        self._duplicate = self._bind(
            self._kernel,
            "DuplicateHandle",
            c.c_int,
            [HANDLE, HANDLE, HANDLE, c.POINTER(HANDLE), DWORD, c.c_int, DWORD],
        )
        self._process = self._bind(self._kernel, "GetCurrentProcess", HANDLE, [])
        self._info = self._bind(
            self._kernel, "GetFileInformationByHandle", c.c_int, [HANDLE, c.POINTER(_FileInfo)]
        )
        self._final = self._bind(
            self._kernel, "GetFinalPathNameByHandleW", DWORD, [HANDLE, c.c_wchar_p, DWORD, DWORD]
        )
        self._type = self._bind(self._kernel, "GetFileType", DWORD, [HANDLE])
        self._get = self._bind(
            self._kernel,
            "GetFileInformationByHandleEx",
            c.c_int,
            [HANDLE, c.c_int, c.c_void_p, DWORD],
        )
        self._set = self._bind(
            self._kernel,
            "SetFileInformationByHandle",
            c.c_int,
            [HANDLE, c.c_int, c.c_void_p, DWORD],
        )
        self._read = self._bind(
            self._kernel,
            "ReadFile",
            c.c_int,
            [HANDLE, c.c_void_p, DWORD, c.POINTER(DWORD), c.c_void_p],
        )
        self._write = self._bind(
            self._kernel,
            "WriteFile",
            c.c_int,
            [HANDLE, c.c_void_p, DWORD, c.POINTER(DWORD), c.c_void_p],
        )
        self._flush = self._bind(self._kernel, "FlushFileBuffers", c.c_int, [HANDLE])
        self._lock = self._bind(
            self._kernel,
            "LockFileEx",
            c.c_int,
            [HANDLE, DWORD, DWORD, DWORD, DWORD, c.POINTER(_Overlapped)],
        )
        self._unlock = self._bind(
            self._kernel,
            "UnlockFileEx",
            c.c_int,
            [HANDLE, DWORD, DWORD, DWORD, c.POINTER(_Overlapped)],
        )
        self._nt_create = self._bind(
            self._nt,
            "NtCreateFile",
            c.c_int32,
            [
                c.POINTER(HANDLE),
                DWORD,
                c.POINTER(_ObjectAttributes),
                c.POINTER(_IoStatus),
                c.c_void_p,
                DWORD,
                DWORD,
                DWORD,
                DWORD,
                c.c_void_p,
                DWORD,
            ],
        )
        self._nt_set = self._bind(
            self._nt,
            "NtSetInformationFile",
            c.c_int32,
            [HANDLE, c.POINTER(_IoStatus), c.c_void_p, DWORD, c.c_int],
        )
        self._dos_error = self._bind(self._nt, "RtlNtStatusToDosError", DWORD, [c.c_int32])

    @staticmethod
    def _bind(dll: Any, name: str, result: Any, args: list[Any]) -> Any:
        function = getattr(dll, name)
        function.restype = result
        function.argtypes = args
        return function

    @staticmethod
    def _last_error() -> int:
        return int(_windows_ctypes.get_last_error())

    @staticmethod
    def _error(code: int) -> OSError:
        return cast(OSError, _windows_ctypes.WinError(code))

    def _check(self, result: object) -> None:
        if not result:
            raise self._error(self._last_error())

    def close(self, value: int) -> None:
        self._check(self._close(value))

    def duplicate(self, handle: Handle) -> Handle:
        result = HANDLE()
        process = self._process()
        self._check(self._duplicate(process, handle.value, process, c.byref(result), 0, False, 2))
        assert result.value is not None
        return Handle(self, result.value)

    def root(self, path: Path) -> Handle:
        absolute = os.path.abspath(path)
        # Extended syntax is applied only to the explicit user-selected root.
        if not absolute.startswith("\\\\?\\"):
            absolute = (
                "\\\\?\\UNC\\" + absolute[2:]
                if absolute.startswith("\\\\")
                else "\\\\?\\" + absolute
            )
        value = self._create(
            absolute, DIRECTORY_ACCESS, SHARE_RW, None, 3, 0x02000000 | 0x00200000, None
        )  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
        if value == HANDLE(-1).value:
            raise self._error(self._last_error())
        handle = Handle(self, int(value))
        try:
            if not self.inspect(handle).directory:
                raise NotADirectoryError(errno.ENOTDIR, "Project root is not a directory")
            return handle
        except BaseException:
            handle.close()
            raise

    def open(
        self,
        parent: Handle,
        name: str,
        *,
        directory: bool | None = False,
        access: int = READ,
        share: int = SHARE_ALL,
        disposition: int = OPEN,
    ) -> Handle:
        encoded = name.encode("utf-16-le")
        if len(encoded) > 65532:
            fail("unsafe_source_path")
        buffer = c.create_string_buffer(encoded + b"\0\0")
        text = _UnicodeString(len(encoded), len(encoded) + 2, c.addressof(buffer))
        # No OBJ_INHERIT and no case-insensitive alias lookup. OBJ_DONT_REPARSE.
        attrs = _ObjectAttributes(
            c.sizeof(_ObjectAttributes), parent.value, c.pointer(text), 0x1000, None, None
        )
        status = _IoStatus()
        result = HANDLE()
        options = 0x00200000 | 0x20  # OPEN_REPARSE_POINT | SYNCHRONOUS_IO_NONALERT
        options |= 1 if directory is True else (0x40 if directory is False else 0)
        code = self._nt_create(
            c.byref(result),
            access | 0x100000 | 0x80,
            c.byref(attrs),
            c.byref(status),
            None,
            0x80,
            share,
            disposition,
            options,
            None,
            0,
        )
        if code < 0:
            if code & 0xFFFFFFFF in {0xC000050B, 0xC0000279, 0xC0000280}:
                fail("unsafe_source_path")
            raise self._error(int(self._dos_error(code)))
        assert result.value is not None
        handle = Handle(self, result.value)
        try:
            self.inspect(handle, directory=directory)
            if self.final_component(handle) != name:
                fail("casefold_collision", "conflict")
            return handle
        except BaseException:
            handle.close()
            raise

    def final_component(self, handle: Handle) -> str:
        # Query the opened object's normalized long name, never reopen this pathname.
        size = int(self._final(handle.value, None, 0, 0))
        self._check(size)
        buffer = c.create_unicode_buffer(size + 1)
        count = int(self._final(handle.value, buffer, len(buffer), 0))
        self._check(count)
        if count >= len(buffer):
            raise OSError("Unstable file name")
        return buffer.value.rsplit("\\", 1)[-1]

    def inspect(self, handle: Handle, *, directory: bool | None = None) -> FileInfo:
        if self._type(handle.value) != 1:  # FILE_TYPE_DISK; never read pipes/devices.
            fail("unsafe_source_path")
        info = _FileInfo()
        self._check(self._info(handle.value, c.byref(info)))
        is_directory = bool(info.attributes & 0x10)
        if (
            info.attributes & 0x400
            or (directory is not None and is_directory != directory)
            or (not is_directory and info.links != 1)
        ):
            fail("unsafe_source_path")
        return FileInfo(is_directory, (int(info.size_high) << 32) | int(info.size_low))

    def names(self, handle: Handle) -> tuple[str, ...]:
        names: list[str] = []
        restart = True
        while True:
            buffer = c.create_string_buffer(65536)
            if not self._get(handle.value, 11 if restart else 10, buffer, len(buffer)):
                error = self._last_error()
                if error == 18:  # ERROR_NO_MORE_FILES
                    return tuple(sorted(names))
                raise self._error(error)
            restart = False
            raw = buffer.raw
            offset = 0
            while True:
                next_offset = struct.unpack_from("<I", raw, offset)[0]
                length = struct.unpack_from("<I", raw, offset + 60)[0]
                end = offset + 104 + length
                if length % 2 or end > len(raw):
                    raise OSError("Invalid directory information")
                name = raw[offset + 104 : end].decode("utf-16-le")
                if name not in {".", ".."}:
                    names.append(name)
                if not next_offset:
                    break
                if next_offset < 104 + length or offset + next_offset + 104 > len(raw):
                    raise OSError("Invalid directory information")
                offset += next_offset

    def read(self, handle: Handle, limit: int) -> bytes:
        if self.inspect(handle, directory=False).size > limit:
            fail("record_resource_limit")
        result = bytearray()
        while len(result) <= limit:
            size = min(1048576, limit + 1 - len(result))
            buffer = c.create_string_buffer(size)
            count = DWORD()
            self._check(self._read(handle.value, buffer, size, c.byref(count), None))
            if not count.value:
                return bytes(result)
            result.extend(buffer.raw[: count.value])
        fail("record_resource_limit")

    def write(self, handle: Handle, body: bytes) -> None:
        offset = 0
        while offset < len(body):
            chunk = body[offset : offset + 1048576]
            count = DWORD()
            self._check(self._write(handle.value, chunk, len(chunk), c.byref(count), None))
            if not count.value:
                raise OSError("Storage write made no progress")
            offset += count.value

    def flush(self, handle: Handle) -> None:
        self._check(self._flush(handle.value))

    def rename(self, handle: Handle, parent: Handle, name: str, *, replace: bool) -> None:
        encoded = name.encode("utf-16-le")
        size = c.sizeof(_Rename) + len(encoded)
        buffer = c.create_string_buffer(size)
        info = _Rename.from_buffer(buffer)
        info.replace, info.root, info.length = int(replace), parent.value, len(encoded)
        c.memmove(c.addressof(buffer) + _Rename.name.offset, encoded, len(encoded))
        status = _IoStatus()
        # The native information class preserves the relative destination anchor.
        # The Win32 wrapper rejected our RootDirectory form on Windows Server CI.
        code = self._nt_set(handle.value, c.byref(status), buffer, size, 10)
        if code < 0:
            raise self._error(int(self._dos_error(code)))

    def delete(self, handle: Handle) -> None:
        delete = c.c_uint8(1)
        self._check(self._set(handle.value, 4, c.byref(delete), c.sizeof(delete)))

    def lock(self, handle: Handle) -> bool:
        overlapped = _Overlapped()
        if self._lock(handle.value, 3, 0, 1, 0, c.byref(overlapped)):
            return True
        error = self._last_error()
        if error == 33:  # ERROR_LOCK_VIOLATION, not access denied or invalid handle.
            return False
        raise self._error(error)

    def unlock(self, handle: Handle) -> None:
        overlapped = _Overlapped()
        self._check(self._unlock(handle.value, 0, 1, 0, c.byref(overlapped)))
