"""Versioned, bounded binary framing of exact record bytes inside durable operations."""

import struct
from typing import Literal

from pydantic import Field

from deykit.contracts.base import Record
from deykit.contracts.codec import dump_record, record_limits
from deykit.contracts.identities import ContentHash, ResourceId
from deykit.contracts.json_value import RECORD_LIMITS, JsonError, bytes_hash, parse_json
from deykit.contracts.ports import Collection
from deykit.storage.errors import fail
from deykit.storage.journal import JournalEntry, JournalManifest
from deykit.storage.records import TYPES

COMPACT_COLLECTIONS: frozenset[Collection] = frozenset(
    {"attempts", "attempt_events", "run_events", "prepared_cases"}
)
_MAGIC = b"DEYKIT-BLOBS\x00\x01"
_FRAME = struct.Struct(">IBI")
_TARGET_BYTES = 4 * 1024 * 1024
CHUNK_LIMIT = 48 * 1024 * 1024


class ChunkManifest(JournalManifest):
    body_format: Literal["chunks-v1", "chunks-v2"] = "chunks-v1"
    blob_chunks: tuple[ContentHash, ...] = Field(min_length=1)


class ChunkReference(Record):
    operation_id: ResourceId
    manifest_hash: ContentHash
    sequence: int = Field(gt=0)


def reference_body(manifest: ChunkManifest, raw: bytes) -> bytes:
    return dump_record(
        ChunkReference(
            operation_id=manifest.operation_id,
            manifest_hash=bytes_hash(raw),
            sequence=manifest.sequence,
        )
    )


def reference_path(operation_id: str) -> tuple[str, ...]:
    return ("source", "_chunks", operation_id + ".json")


def manifest_kind(body: bytes) -> type[JournalManifest]:
    value = parse_json(body, RECORD_LIMITS)
    if isinstance(value, dict) and "body_format" in value:
        if value["body_format"] not in ("chunks-v1", "chunks-v2"):
            raise JsonError("invalid_record")
        return ChunkManifest
    return JournalManifest


def compact_entry(manifest: JournalManifest, entry: JournalEntry) -> bool:
    return isinstance(manifest, ChunkManifest) and (
        entry.collection in COMPACT_COLLECTIONS
        or (manifest.body_format == "chunks-v2" and entry.collection == "cases")
    )


def chunk_name(index: int) -> str:
    return f"chunk-{index}.pack"


def create_chunk_count(bodies: tuple[bytes, ...]) -> int:
    """Count the packs for create-only bodies without copying their contents."""
    count = 0
    size = len(_MAGIC)
    for body in bodies:
        frame_size = _FRAME.size + len(body)
        if size > len(_MAGIC) and size + frame_size > _TARGET_BYTES:
            count += 1
            size = len(_MAGIC)
        size += frame_size
    return count + (size > len(_MAGIC))


def encode_chunks(blobs: tuple[tuple[int, bool, bytes], ...]) -> tuple[bytes, ...]:
    chunks: list[bytes] = []
    current = bytearray(_MAGIC)
    for index, old, body in blobs:
        frame = _FRAME.pack(index, 0 if old else 1, len(body))
        if len(current) > len(_MAGIC) and len(current) + len(frame) + len(body) > _TARGET_BYTES:
            chunks.append(bytes(current))
            current = bytearray(_MAGIC)
        current.extend(frame)
        current.extend(body)
    if len(current) > len(_MAGIC):
        chunks.append(bytes(current))
    return tuple(chunks)


def decode_chunks(
    manifest: ChunkManifest, chunks: tuple[bytes, ...]
) -> dict[tuple[int, bool], bytes]:
    if len(chunks) != len(manifest.blob_chunks):
        fail("journal_integrity_error", "conflict")
    result: dict[tuple[int, bool], bytes] = {}
    for chunk, digest in zip(chunks, manifest.blob_chunks, strict=True):
        if len(chunk) > CHUNK_LIMIT or bytes_hash(chunk) != digest or not chunk.startswith(_MAGIC):
            fail("journal_integrity_error", "conflict")
        offset = len(_MAGIC)
        if offset == len(chunk):
            fail("journal_integrity_error", "conflict")
        while offset < len(chunk):
            if offset + _FRAME.size > len(chunk):
                fail("journal_integrity_error", "conflict")
            index, kind, length = _FRAME.unpack_from(chunk, offset)
            offset += _FRAME.size
            if (
                kind not in (0, 1)
                or index >= len(manifest.entries)
                or length > record_limits(TYPES[manifest.entries[index].collection]).max_bytes
                or offset + length > len(chunk)
            ):
                fail("journal_integrity_error", "conflict")
            identity = (index, kind == 0)
            body = chunk[offset : offset + length]
            offset += length
            entry = manifest.entries[index]
            expected = entry.old_hash if kind == 0 else entry.new_hash
            if identity in result or expected is None or bytes_hash(body) != expected:
                fail("journal_integrity_error", "conflict")
            result[identity] = body
    expected_ids = {
        (i, old)
        for i, entry in enumerate(manifest.entries)
        for old, digest in ((True, entry.old_hash), (False, entry.new_hash))
        if digest is not None
    }
    if set(result) != expected_ids:
        fail("journal_integrity_error", "conflict")
    return result


def expected_files(manifest: JournalManifest) -> set[str]:
    if isinstance(manifest, ChunkManifest):
        return {
            "manifest.json",
            "commit.json",
            *(chunk_name(i) for i in range(len(manifest.blob_chunks))),
        }
    return {
        "manifest.json",
        "commit.json",
        *(
            f"{kind}-{i}.json"
            for i, entry in enumerate(manifest.entries)
            for kind, digest in (("old", entry.old_hash), ("new", entry.new_hash))
            if digest is not None
        ),
    }
