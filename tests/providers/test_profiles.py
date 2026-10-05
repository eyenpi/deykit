from contextlib import nullcontext
from hashlib import sha256

import pytest
from test_jev import profile

from deykit.contracts.ports import CommitReceipt, StoredRecord
from deykit.contracts.records import ProviderProfile
from deykit.providers.fixtures import FIXTURE_DESTINATION
from deykit.providers.profiles import ProviderProfiles


class Source:
    def __init__(self):
        self.records = {}
        self.operations = []
        self.receipts = {}

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

    def operation_receipt(self, operation_id, *, intent_hash):
        existing = self.receipts.get(operation_id)
        if existing is None:
            return None
        digest, receipt = existing
        if digest != intent_hash:
            raise ValueError("operation_intent_conflict")
        return CommitReceipt(operation_id, receipt.changes, True)

    def commit(self, operation_id, changes, *, intent_hash):
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
        receipt = CommitReceipt(operation_id, stored, False)
        self.receipts[operation_id] = (intent_hash, receipt)
        return receipt


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


def test_profiles_include_fixture_views_and_replay_original_receipt_after_update():
    source = Source()
    profiles = ProviderProfiles(source)
    fixture = ProviderProfile(
        id="authored",
        adapter="fixture",
        requested_model="authored-demo",
        destination=FIXTURE_DESTINATION,
    )
    created = profiles.configure(fixture, expected_etag=None, operation_id="fixture-one")
    assert profiles.read("authored") == fixture
    assert profiles.view("authored").etag == created.changes[0].etag
    assert profiles.list_views(limit=1).items[0].profile.id == "authored"
    next_profile = fixture.model_copy(update={"requested_model": "authored-next"})
    profiles.configure(
        next_profile,
        expected_etag=created.changes[0].etag,
        operation_id="fixture-two",
    )
    replay = profiles.configure(fixture, expected_etag=None, operation_id="fixture-one")
    assert replay.replayed is True
    assert replay.changes == created.changes
    with pytest.raises(ValueError, match="operation_intent_conflict"):
        profiles.configure(next_profile, expected_etag=None, operation_id="fixture-one")
