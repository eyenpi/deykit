"""Exact-key validation reuse remains inside fresh source read epochs."""

from __future__ import annotations

import pytest

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import CaseRecord, DecisionDraft
from deykit.storage import _body_validation as body_validation
from deykit.storage.source import FileProjectSource

STAMP = "2026-10-05T12:00:00Z"


def _draft(value: str) -> bytes:
    return dump_record(DecisionDraft(decision_id="draft", editor_source=value, updated_at=STAMP))


def _counter(monkeypatch: pytest.MonkeyPatch) -> list[tuple[ResourceKey, bytes]]:
    calls: list[tuple[ResourceKey, bytes]] = []
    original = body_validation.validate_body

    def validate(key: ResourceKey, body: bytes) -> object:
        calls.append((key, body))
        return original(key, body)

    monkeypatch.setattr(body_validation, "validate_body", validate)
    return calls


def test_memo_hits_only_exact_successful_key_and_body(monkeypatch):
    calls = _counter(monkeypatch)
    memo = body_validation._SuccessfulBodyValidationMemo()
    key = ResourceKey("drafts", "draft")
    first = _draft("first")
    changed = _draft("changed")

    memo.validate(key, first)
    memo.validate(key, first)
    memo.validate(key, changed)
    assert calls == [(key, first), (key, changed)]

    with pytest.raises(ServiceFailure):
        memo.validate(ResourceKey("drafts", "foreign"), first)
    assert len(calls) == 3

    scoped_key = ResourceKey("cases", "case", ("dataset",))
    scoped_body = dump_record(
        CaseRecord(
            id="case",
            dataset_id="dataset",
            input_kind="text",
            input_source='"source"',
        )
    )
    memo.validate(scoped_key, scoped_body)
    with pytest.raises(ServiceFailure):
        memo.validate(ResourceKey("cases", "case", ("foreign",)), scoped_body)
    assert len(calls) == 5
    with pytest.raises(ServiceFailure):
        memo.validate(ResourceKey("cases", "case"), scoped_body)
    assert len(calls) == 5


def test_invalid_body_is_never_cached(monkeypatch):
    calls = _counter(monkeypatch)
    memo = body_validation._SuccessfulBodyValidationMemo()
    key = ResourceKey("drafts", "draft")

    for _ in range(2):
        with pytest.raises(ServiceFailure):
            memo.validate(key, b"not a record")

    assert calls == [(key, b"not a record"), (key, b"not a record")]
    assert not memo._entries


def test_limits_evict_lru_and_skip_oversized_entries(monkeypatch):
    calls = _counter(monkeypatch)
    memo = body_validation._SuccessfulBodyValidationMemo()
    first_key = ResourceKey("drafts", "draft")
    second_key = ResourceKey("drafts", "other")
    first = _draft("same-size")
    second = dump_record(
        DecisionDraft(decision_id="other", editor_source="same-size", updated_at=STAMP)
    )

    monkeypatch.setattr(body_validation, "_MAX_ENTRIES", 1)
    memo.validate(first_key, first)
    memo.validate(second_key, second)
    memo.validate(first_key, first)
    assert len(calls) == 3

    memo.clear()
    calls.clear()
    monkeypatch.setattr(body_validation, "_MAX_ENTRIES", 10)
    first_weight = len(first) + len("drafts") + len("draft") + 8 * 2
    second_weight = len(second) + len("drafts") + len("other") + 8 * 2
    monkeypatch.setattr(
        body_validation,
        "_MAX_RETAINED_KEY_BYTES",
        max(first_weight, second_weight),
    )
    memo.validate(first_key, first)
    memo.validate(second_key, second)
    memo.validate(first_key, first)
    assert len(calls) == 3

    memo.clear()
    calls.clear()
    monkeypatch.setattr(body_validation, "_MAX_RETAINED_KEY_BYTES", len(first) - 1)
    memo.validate(first_key, first)
    memo.validate(first_key, first)
    assert len(calls) == 2
    assert not memo._entries


def test_source_cache_is_epoch_scoped_and_close_clears_it(tmp_path, monkeypatch):
    import deykit.storage.source as source_module

    calls: list[tuple[ResourceKey, bytes]] = []
    original = source_module.validate_body

    def strict_validate(key: ResourceKey, body: bytes) -> object:
        calls.append((key, body))
        return original(key, body)

    monkeypatch.setattr(source_module, "validate_body", strict_validate)
    key = ResourceKey("drafts", "draft")
    body = _draft("cached")
    source = FileProjectSource(tmp_path / "epoch", create=True)
    with source.consistent_read():
        source._validate_source_body(key, body)
        source._validate_source_body(key, body)
    assert not calls
    assert len(source._body_validation._entries) == 1

    source._validate_source_body(key, body)
    source._validate_source_body(key, body)
    assert calls == [(key, body), (key, body)]

    source.close()
    assert not source._body_validation._entries


def test_success_memo_is_per_source(tmp_path, monkeypatch):
    calls = _counter(monkeypatch)
    first = FileProjectSource(tmp_path / "first", create=True)
    second = FileProjectSource(tmp_path / "second", create=True)
    key = ResourceKey("drafts", "draft")
    body = _draft("same")

    for source in (first, second):
        with source.consistent_read():
            source._validate_source_body(key, body)
            source._validate_source_body(key, body)

    assert calls == [(key, body), (key, body)]
    first.close()
    second.close()


def test_lock_free_receipt_peek_bypasses_warmed_memo(tmp_path, monkeypatch):
    source = FileProjectSource(tmp_path / "receipt", create=True)
    key = ResourceKey("drafts", "draft")
    body = _draft("receipt")
    intent_hash = "a" * 64
    source.commit(
        "operation",
        (SourceChange(key, body, None),),
        intent_hash=intent_hash,
    )
    assert source._body_validation._entries

    def forbidden(*_args, **_kwargs):
        pytest.fail("lock-free receipt peek must bypass the source memo")

    monkeypatch.setattr(source._body_validation, "validate", forbidden)
    receipt = source._peek_durable_receipt("operation", intent_hash=intent_hash)
    assert receipt is not None
    assert receipt.replayed is True
    source.close()


def test_warm_source_read_still_revalidates_fresh_disk_bytes(tmp_path):
    source = FileProjectSource(tmp_path / "tamper", create=True)
    key = ResourceKey("drafts", "draft")
    body = _draft("valid")
    source.commit("create", (SourceChange(key, body, None),))
    with source.consistent_read():
        source._all()
    (source.root / "source/drafts/draft.json").write_bytes(b"invalid replacement")

    with pytest.raises(ServiceFailure):
        source.read(key)
    source.close()


def test_warm_history_blob_still_checks_fresh_hash_before_memo(tmp_path, monkeypatch):
    source = FileProjectSource(tmp_path / "history-tamper", create=True)
    key = ResourceKey("drafts", "draft")
    body = _draft("committed")
    source.commit("operation", (SourceChange(key, body, None),))
    source.operation_history(key)
    assert (key, body) in source._body_validation._entries

    blob = source.root / "history/operations/operation/new-0.json"
    tampered = _draft("valid but different")
    blob.write_bytes(tampered)
    memo_calls: list[tuple[ResourceKey, bytes]] = []
    original_validate = source._body_validation.validate

    def observe_memo(key: ResourceKey, body: bytes) -> None:
        memo_calls.append((key, body))
        original_validate(key, body)

    monkeypatch.setattr(source._body_validation, "validate", observe_memo)
    with pytest.raises(ServiceFailure) as failure:
        source.read(key)
    assert failure.value.error.reason == "journal_integrity_error"
    assert (key, body) in memo_calls
    assert (key, tampered) not in memo_calls
    source.close()
