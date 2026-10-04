"""Disposable SQLite index, constructed entirely from authoritative records."""

import json
import sqlite3

from deykit.contracts.ports import StoredRecord
from deykit.storage.filesystem import SafeFiles


class SourceIndex:
    def __init__(self, files: SafeFiles) -> None:
        self.files = files

    def rebuild(self, records: tuple[StoredRecord, ...]) -> None:
        # Build in memory so SQLite cannot follow a replaced/symlinked cache path.
        with sqlite3.connect(":memory:") as connection:
            connection.execute(
                "CREATE TABLE records (collection TEXT, scope TEXT, id TEXT, "
                "etag TEXT, PRIMARY KEY(collection, scope, id))"
            )
            connection.executemany(
                "INSERT INTO records VALUES (?, ?, ?, ?)",
                [
                    (
                        record.key.collection,
                        json.dumps(record.key.scope),
                        record.key.resource_id,
                        record.etag,
                    )
                    for record in records
                ],
            )
            connection.commit()
            image = connection.serialize()
        self.files.replace((".deykit", "index.sqlite3"), image)
