"""Disposable SQLite index, constructed entirely from authoritative records."""

import json
import sqlite3
from threading import RLock

from deykit.contracts.ports import ResourceKey, StoredRecord
from deykit.storage.filesystem import SafeFiles


class SourceIndex:
    def __init__(self, files: SafeFiles) -> None:
        self.files = files
        self.connection: sqlite3.Connection | None = None
        self.rows: dict[ResourceKey, str] = {}
        self.vector: tuple[StoredRecord, ...] | None = None
        self.mutex = RLock()

    def rebuild(
        self,
        records: tuple[StoredRecord, ...],
        *,
        previous: tuple[StoredRecord, ...] | None = None,
        changes: tuple[StoredRecord, ...] | None = None,
        deleted_keys: tuple[ResourceKey, ...] = (),
    ) -> None:
        with self.mutex:
            incremental = previous is not None and self.vector == previous and changes is not None
            if incremental and changes is not None:
                current = dict(self.rows)
                for key in deleted_keys:
                    current.pop(key, None)
                current.update((r.key, r.etag) for r in changes)
            else:
                current = {record.key: record.etag for record in records}
            if len(current) != len(records):
                raise ValueError("duplicate_index_key")
            # SQLite never opens a filesystem path. Its private connection can move
            # between joined source workers, with access serialized by this mutex.
            if self.connection is None:
                self.connection = sqlite3.connect(":memory:", check_same_thread=False)
                self.connection.execute(
                    "CREATE TABLE records (collection TEXT, scope TEXT, id TEXT, "
                    "etag TEXT, PRIMARY KEY(collection, scope, id))"
                )
            connection = self.connection
            with connection:
                connection.executemany(
                    "DELETE FROM records WHERE collection=? AND scope=? AND id=?",
                    [
                        (key.collection, json.dumps(key.scope), key.resource_id)
                        for key in (
                            deleted_keys if incremental else self.rows.keys() - current.keys()
                        )
                    ],
                )
                connection.executemany(
                    "INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?)",
                    [
                        (key.collection, json.dumps(key.scope), key.resource_id, etag)
                        for key, etag in (
                            ((r.key, r.etag) for r in changes)
                            if incremental and changes is not None
                            else current.items()
                        )
                        if self.rows.get(key) != etag
                    ],
                )
            self.rows = current
            self.vector = records
            image = connection.serialize()
            if len(current) > 131_072:
                self.close()
            self.files.replace((".deykit", "index.sqlite3"), image)

    def close(self) -> None:
        with self.mutex:
            if self.connection is not None:
                self.connection.close()
                self.connection = None
            self.rows.clear()
            self.vector = None
