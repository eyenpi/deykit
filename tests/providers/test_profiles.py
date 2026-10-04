from contextlib import nullcontext
from hashlib import sha256

import pytest
from test_jev import profile

from deykit.contracts.ports import CommitReceipt, StoredRecord
from deykit.providers.profiles import ProviderProfiles


class Source:
    def __init__(self):
        self.records = {}
        self.operations = []

    def read(self, key):
        return self.records.get(key)

    def list_ids(self, collection, scope=()):
        return sorted(
            key.resource_id
            for key in self.records
            if key.collection == collection and key.scope == scope
        )

    def consistent_read(self):
        return nullcontext(self)

    def commit(self, operation_id, changes):
        for change in changes:
            current = self.read(change.key)
            if change.expected_etag != (current.etag if current else None):
                raise ValueError("conflict")
        stored = tuple(
            StoredRecord(change.key, change.body, sha256(change.body).hexdigest())
            for change in changes
        )
        self.records.update({item.key: item for item in stored})
        self.operations.append(operation_id)
        return CommitReceipt(operation_id, stored, False)


def test_a30_configuration_reads_writes_have_no_network_or_credential_dependency():
    source = Source()
    profiles = ProviderProfiles(source)
    saved = profiles.configure(profile(), expected_etag=None, operation_id="configure-one")
    assert profiles.read("local") == profile()
    assert profiles.list() == (profile(),)
    assert source.operations == ["configure-one"]
    assert b"env:OFFLINE_KEY" in saved.changes[0].body
    with pytest.raises(ValueError, match="conflict"):
        profiles.configure(profile(), expected_etag=None, operation_id="configure-two")
    updated = profile().model_copy(update={"requested_model": "jev-latest"})
    profiles.configure(updated, expected_etag=saved.changes[0].etag, operation_id="configure-three")
    assert profiles.read("local").requested_model == "jev-latest"
