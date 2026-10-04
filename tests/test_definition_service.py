"""Authoring semantics against a narrow source test double, with no provider calls."""

import json
from contextlib import nullcontext
from dataclasses import dataclass, field

import pytest

from deykit.application.definitions import DecisionService
from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record
from deykit.contracts.json_value import bytes_hash
from deykit.contracts.ports import CommitReceipt, ResourceKey, SourceChange, StoredRecord
from deykit.contracts.records import ChoiceDefinition, ChoiceOption, ChoiceQuestion, LabelRecord


class FixedClock:
    def utc_now(self) -> str:
        return "2026-10-05T12:00:00Z"

    def monotonic(self) -> float:
        return 0.0


@dataclass
class MemorySource:
    records: dict[ResourceKey, StoredRecord] = field(default_factory=dict)
    operations: dict[str, tuple[str | None, CommitReceipt]] = field(default_factory=dict)

    def read(self, key: ResourceKey) -> StoredRecord | None:
        return self.records.get(key)

    def list_ids(self, collection: str, scope: tuple[str, ...] = ()) -> tuple[str, ...]:
        return tuple(
            sorted(
                key.resource_id
                for key in self.records
                if key.collection == collection and key.scope == scope
            )
        )

    def consistent_read(self):
        return nullcontext(self)

    def operation_receipt(self, operation_id: str, *, intent_hash: str):
        prior = self.operations.get(operation_id)
        if prior is None:
            return None
        if prior[0] != intent_hash:
            raise ServiceFailure(self._conflict())
        return prior[1]

    @staticmethod
    def _conflict():
        from deykit.contracts.errors import ServiceError

        return ServiceError(code="conflict")

    def commit(
        self,
        operation_id: str,
        changes: tuple[SourceChange, ...],
        *,
        intent_hash: str | None = None,
    ) -> CommitReceipt:
        existing = self.operation_receipt(operation_id, intent_hash=intent_hash or "")
        if existing is not None:
            return existing
        for change in changes:
            old = self.records.get(change.key)
            if (old.etag if old else None) != change.expected_etag:
                raise ServiceFailure(self._conflict())
        stored = tuple(
            StoredRecord(change.key, change.body, bytes_hash(change.body))
            for change in changes
            if change.body is not None
        )
        for record in stored:
            self.records[record.key] = record
        receipt = CommitReceipt(operation_id, stored)
        self.operations[operation_id] = (intent_hash, receipt)
        return receipt


def definition_source(*, option_name: str = "One", options=("one", "two"), schema=None):
    definition = ChoiceDefinition(
        input_kind="json",
        input_schema_source=schema,
        selected_fields=("shown",),
        questions=(
            ChoiceQuestion(
                id="q",
                instructions="Classify the selected text",
                options=tuple(
                    ChoiceOption(id=option, name=(option_name if option == "one" else option))
                    for option in options
                ),
            ),
        ),
    )
    return dump_record(definition).decode("utf-8")


@pytest.fixture
def authoring():
    source = MemorySource()
    ids = iter(("rev1", "rev2", "rev3"))
    return DecisionService(source, FixedClock(), lambda: next(ids)), source


def test_incomplete_draft_becomes_immutable_revision_and_replays(authoring):
    service, _ = authoring
    created = service.create("d", "Original", '{"unfinished":', operation_id="create")
    assert service.read("d").draft.record.editor_source == '{"unfinished":'
    with pytest.raises(ServiceFailure) as invalid:
        service.save(
            "d",
            expected_draft_etag=created.draft.etag,
            expected_decision_etag=created.decision.etag,
            operation_id="save",
        )
    assert invalid.value.error.code == "validation_error"
    source = definition_source()
    draft = service.update_draft("d", source, expected_etag=created.draft.etag, operation_id="edit")
    saved = service.save(
        "d",
        expected_draft_etag=draft.etag,
        expected_decision_etag=created.decision.etag,
        operation_id="save",
        note="First",
    )
    assert saved.record.id == "rev1"
    assert saved.record.note == "First"
    assert service.history("d").items[0].record == saved.record
    assert (
        service.save(
            "d",
            expected_draft_etag=draft.etag,
            expected_decision_etag=created.decision.etag,
            operation_id="save",
            note="First",
        )
        == saved
    )
    with pytest.raises(ServiceFailure) as changed_intent:
        service.save(
            "d",
            expected_draft_etag=draft.etag,
            expected_decision_etag=created.decision.etag,
            operation_id="save",
            note="Changed",
        )
    assert changed_intent.value.error.code == "conflict"


def test_etag_conflict_preserves_other_editor_and_replay_after_newer_edit(authoring):
    service, _ = authoring
    created = service.create("d", "D", "bad", operation_id="create")
    first = service.update_draft(
        "d", "first", expected_etag=created.draft.etag, operation_id="edit1"
    )
    with pytest.raises(ServiceFailure) as conflict:
        service.update_draft("d", "second", expected_etag=created.draft.etag, operation_id="edit2")
    assert conflict.value.error.code == "conflict"
    assert service.read("d").draft.record.editor_source == "first"
    service.update_draft("d", "third", expected_etag=first.etag, operation_id="edit3")
    assert (
        service.update_draft("d", "first", expected_etag=created.draft.etag, operation_id="edit1")
        == first
    )


def test_schema_rejection_before_selection_and_precise_input(authoring):
    service, _ = authoring
    source = definition_source(
        schema='{"required":["hidden"],"properties":{"hidden":{"type":"integer"}}}'
    )
    service.create("d", "D", source, operation_id="create")
    with pytest.raises(ServiceFailure) as invalid:
        service.select_case("d", '{"shown":1}')
    assert invalid.value.error.reason == "input_schema_mismatch"
    selected = service.select_case("d", '{"hidden":2,"shown":9007199254740993}')
    assert selected.source == '{"shown":9007199254740993}'
    for schema, reason in (
        ('{"$ref":"https://example.invalid/schema"}', "remote_schema_reference"),
        ('{"type":"nonsense"}', "invalid_schema"),
        ('{"type":"object","type":"array"}', "duplicate_key"),
    ):
        edited = definition_source().replace(
            '"input_schema_source":null', '"input_schema_source":' + json.dumps(schema)
        )
        current = service.read("d")
        service.update_draft(
            "d", edited, expected_etag=current.draft.etag, operation_id="edit" + reason
        )
        with pytest.raises(ServiceFailure) as rejected:
            service.validate("d")
        assert rejected.value.error.reason == reason
    current = service.read("d")
    malformed = definition_source().replace('"schema_version":1', '"schema_version":NaN')
    service.update_draft("d", malformed, expected_etag=current.draft.etag, operation_id="nonfinite")
    with pytest.raises(ServiceFailure) as nonfinite:
        service.validate("d")
    assert nonfinite.value.error.reason == "nonfinite_number"


def test_option_rename_and_deletion_keep_references_visible(authoring):
    service, store = authoring
    created = service.create("d", "D", definition_source(), operation_id="create")
    first = service.save(
        "d",
        expected_draft_etag=created.draft.etag,
        expected_decision_etag=created.decision.etag,
        operation_id="save1",
    )
    label = LabelRecord(
        id="label",
        decision_id="d",
        dataset_id="data",
        case_id="case",
        question_id="q",
        input_hash="a" * 64,
        acceptable_option_ids=("one",),
        provenance="human",
        updated_at="2026-10-05T12:00:00Z",
    )
    store.records[ResourceKey("datasets", "data")] = StoredRecord(
        ResourceKey("datasets", "data"), b"{}", bytes_hash(b"{}")
    )
    store.records[ResourceKey("labels", "label", ("d", "data"))] = StoredRecord(
        ResourceKey("labels", "label", ("d", "data")),
        dump_record(label),
        bytes_hash(dump_record(label)),
    )
    renamed = service.update_draft(
        "d",
        definition_source(option_name="Renamed"),
        expected_etag=service.read("d").draft.etag,
        operation_id="renameoption",
    )
    second = service.save(
        "d",
        expected_draft_etag=renamed.etag,
        expected_decision_etag=service.read("d").decision.etag,
        operation_id="save2",
    )
    assert second.record.content_hash != first.record.content_hash
    assert service.diff("d", "rev1", "rev2").removed_option_ids == ()
    service.update_draft(
        "d",
        definition_source(options=("two", "three")),
        expected_etag=service.read("d").draft.etag,
        operation_id="removeoption",
    )
    diff = service.diff("d", "rev2", "draft")
    assert diff.removed_option_ids == ("one",)
    assert [
        (item.kind, item.resource_id, item.missing_option_ids)
        for item in diff.incompatible_references
    ] == [("label", "label", ("one",))]
    assert label.acceptable_option_ids == ("one",)


def test_metadata_hash_and_archival_history_are_independent(authoring):
    service, _ = authoring
    created = service.create("d", "D", definition_source(), operation_id="create")
    saved = service.save(
        "d",
        expected_draft_etag=created.draft.etag,
        expected_decision_etag=created.decision.etag,
        operation_id="save",
    )
    renamed = service.rename(
        "d", "New name", expected_etag=service.read("d").decision.etag, operation_id="rename"
    )
    archived = service.archive("d", expected_etag=renamed.etag, operation_id="archive")
    assert service.list().total == 0
    assert service.list(include_archived=True).total == 1
    assert service.revision("d", saved.record.id).record.content_hash == saved.record.content_hash
    restored = service.restore("d", expected_etag=archived.etag, operation_id="restore")
    assert restored.record.latest_revision_id == saved.record.id
    assert service.list().total == 1


def test_restore_saved_revision_copies_draft_without_mutating_history(authoring):
    service, _ = authoring
    first_source = definition_source()
    created = service.create("d", "D", first_source, operation_id="create")
    saved = service.save(
        "d",
        expected_draft_etag=created.draft.etag,
        expected_decision_etag=created.decision.etag,
        operation_id="save",
    )
    updated = service.update_draft(
        "d",
        definition_source(option_name="Changed"),
        expected_etag=service.read("d").draft.etag,
        operation_id="edit",
    )
    restored = service.restore_revision_to_draft(
        "d", saved.record.id, expected_draft_etag=updated.etag, operation_id="copy"
    )
    assert restored.record.base_revision_id == saved.record.id
    assert service.validate("d") == saved.record.definition
    assert service.revision("d", saved.record.id).record == saved.record
    assert (
        service.restore_revision_to_draft(
            "d", saved.record.id, expected_draft_etag=updated.etag, operation_id="copy"
        )
        == restored
    )


def test_unsupported_persisted_version_blocks_mutation(authoring):
    service, store = authoring
    created = service.create("d", "D", definition_source(), operation_id="create")
    key = ResourceKey("drafts", "d")
    body = dump_record(created.draft.record).replace(b'"schema_version":1', b'"schema_version":2')
    store.records[key] = StoredRecord(key, body, bytes_hash(body))
    with pytest.raises(ServiceFailure) as blocked:
        service.rename("d", "Changed", expected_etag=created.decision.etag, operation_id="rename")
    assert blocked.value.error.code == "validation_error"
    assert store.records[ResourceKey("decisions", "d")].etag == created.decision.etag


def test_deterministic_page_boundaries(authoring):
    service, _ = authoring
    for decision_id in ("c", "a", "b"):
        service.create(decision_id, decision_id, "{}", operation_id="create" + decision_id)
    first = service.list(limit=2)
    assert tuple(view.decision.record.id for view in first.items) == ("a", "b")
    assert first.total == 3 and first.next_cursor == "b"
    second = service.list(cursor=first.next_cursor, limit=2)
    assert tuple(view.decision.record.id for view in second.items) == ("c",)
    assert second.next_cursor is None
    for bad in (0, 501, True):
        with pytest.raises(ServiceFailure) as invalid:
            service.list(limit=bad)
        assert invalid.value.error.reason == "invalid_page_limit"


def test_order_only_edit_is_explicit_in_diff(authoring):
    service, _ = authoring
    created = service.create("d", "D", definition_source(), operation_id="create")
    saved = service.save(
        "d",
        expected_draft_etag=created.draft.etag,
        expected_decision_etag=created.decision.etag,
        operation_id="save",
    )
    reordered = ChoiceDefinition(
        input_kind="json",
        selected_fields=("shown",),
        questions=(
            ChoiceQuestion(
                id="q",
                instructions="Classify the selected text",
                options=(ChoiceOption(id="two", name="two"), ChoiceOption(id="one", name="One")),
            ),
        ),
    )
    service.update_draft(
        "d",
        dump_record(reordered).decode(),
        expected_etag=service.read("d").draft.etag,
        operation_id="reorder",
    )
    diff = service.diff("d", saved.record.id, "draft")
    assert diff.option_order_changed
    assert diff.added_option_ids == diff.removed_option_ids == diff.changed_option_ids == ()
    assert diff.before_hash != diff.after_hash


def test_current_revision_exposes_one_saved_identity(authoring):
    service, _ = authoring
    created = service.create("d", "D", definition_source(), operation_id="create")
    with pytest.raises(ServiceFailure) as unsaved:
        service.current_revision("d")
    assert unsaved.value.error.reason == "unsaved_decision"
    saved = service.save(
        "d",
        expected_draft_etag=created.draft.etag,
        expected_decision_etag=created.decision.etag,
        operation_id="save",
    )
    current = service.current_revision("d")
    assert current.decision.record.latest_revision_id == saved.record.id
    assert current.revision == saved
    service.archive("d", expected_etag=current.decision.etag, operation_id="archive")
    with pytest.raises(ServiceFailure) as archived:
        service.current_revision("d")
    assert archived.value.error.reason == "decision_archived"


def test_large_incomplete_draft_stays_editable_with_stable_intent(authoring):
    service, _ = authoring
    source = '{"unfinished":"' + "x" * 2_200_000
    created = service.create("d", "D", source, operation_id="create")
    assert created.draft.record.editor_source == source
    assert service.create("d", "D", source, operation_id="create") == created
