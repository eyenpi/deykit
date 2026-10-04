import json
import shutil

import pytest

from deykit.application.errors import ServiceFailure
from deykit.application.projects import ProjectService, nearest_project
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import CaseRecord, DecisionDraft, RunSegment
from deykit.storage import FileProjectSource

STAMP = "2026-10-05T12:00:00Z"


class Clock:
    def utc_now(self):
        return STAMP

    def monotonic(self):
        return 0.0


def service():
    return ProjectService(
        lambda path, create: FileProjectSource(path, create=create), Clock(), lambda: "project"
    )


def draft(text):
    return dump_record(DecisionDraft(decision_id="d", editor_source=text, updated_at=STAMP))


def initialized(tmp_path):
    root = tmp_path / "Project ü"
    service().create(root, "Project", "create")
    return root


def reason(error, expected):
    assert error.value.error.reason == expected
    assert "SECRET" not in str(error.value)


def test_a05_conflicting_writers_keep_proposed_editor_content(tmp_path):
    root = initialized(tmp_path)
    key = ResourceKey("drafts", "d")
    with FileProjectSource(root) as first, FileProjectSource(root) as second:
        saved = first.commit("initial", (SourceChange(key, draft("first"), None),)).changes[0]
        proposed = draft("still editable")
        first.commit("winner", (SourceChange(key, draft("winner"), saved.etag),))
        with pytest.raises(ServiceFailure) as error:
            second.commit("loser", (SourceChange(key, proposed, saved.etag),))
        reason(error, "revision_changed")
        assert load_record(DecisionDraft, proposed).editor_source == "still editable"
        assert load_record(DecisionDraft, second.read(key).body).editor_source == "winner"


def test_a07_copy_and_discard_entire_cache_preserves_history_and_identity(tmp_path):
    root = initialized(tmp_path)
    with FileProjectSource(root) as source:
        key = ResourceKey("cases", "same-id", ("dataset",))
        case = CaseRecord(
            id="same-id",
            dataset_id="dataset",
            input_kind="json",
            input_source='{"big":9007199254740993,"n":0.1234567890123456789}',
        )
        original = source.commit("case", (SourceChange(key, dump_record(case), None),))
    copied = tmp_path / "Copied space é"
    shutil.copytree(root, copied)
    shutil.rmtree(copied / ".deykit")
    with FileProjectSource(copied) as reopened:
        assert reopened.read(key) == original.changes[0]
        assert reopened.operation_history(key)[0].after == original.changes[0]
        assert reopened.rebuild_index() == 2
    assert service().open(copied).project.id == "project"
    nested = copied / "nested" / "deeper"
    nested.mkdir(parents=True)
    assert nearest_project(nested) == copied
    assert (copied / "deykit.project.json").is_file()
    assert not (copied / "source" / "project").exists()


def test_replay_uses_original_receipt_and_rejects_changed_payload(tmp_path):
    root = initialized(tmp_path)
    key = ResourceKey("drafts", "d")
    with FileProjectSource(root) as source:
        changes = (SourceChange(key, draft("a"), None),)
        first = source.commit("same-op", changes)
        source.commit("later", (SourceChange(key, draft("b"), first.changes[0].etag),))
        replayed = source.commit("same-op", changes)
        assert replayed.replayed and replayed.changes == first.changes
        with pytest.raises(ServiceFailure) as error:
            source.commit("same-op", (SourceChange(key, draft("changed"), None),))
        reason(error, "operation_id_conflict")


def test_intent_replay_precedes_generated_data_and_later_edits(tmp_path):
    root = initialized(tmp_path)
    key = ResourceKey("drafts", "d")
    with FileProjectSource(root) as source:
        assert source.operation_receipt("intent", intent_hash="a" * 64) is None
        first = source.commit(
            "intent", (SourceChange(key, draft("generated-first"), None),), intent_hash="a" * 64
        )
        source.commit("later", (SourceChange(key, draft("later"), first.changes[0].etag),))
        assert source.operation_receipt("intent", intent_hash="a" * 64).changes == first.changes
        assert (
            source.commit(
                "intent",
                (SourceChange(key, draft("generated-second"), None),),
                intent_hash="a" * 64,
            ).changes
            == first.changes
        )
        with pytest.raises(ServiceFailure) as error:
            source.operation_receipt("intent", intent_hash="b" * 64)
        reason(error, "operation_id_conflict")


def test_deletion_receipt_replay_and_chronological_history(tmp_path):
    root = initialized(tmp_path)
    key = ResourceKey("drafts", "d")
    with FileProjectSource(root) as source:
        first = source.commit("z-first", (SourceChange(key, draft("a"), None),))
        changes = (SourceChange(key, None, first.changes[0].etag),)
        deleted = source.commit("a-second", changes)
        assert deleted.deleted_keys == (key,) and deleted.changes == ()
        assert source.commit("a-second", changes).deleted_keys == (key,)
        history = source.operation_history(key)
        assert [entry.operation_id for entry in history] == ["z-first", "a-second"]
        assert history[1].before == first.changes[0] and history[1].after is None


def test_postcommit_index_failure_is_success_and_rebuildable(tmp_path):
    root = initialized(tmp_path)

    def bad_index(_):
        raise RuntimeError("SECRET")

    key = ResourceKey("drafts", "d")
    with FileProjectSource(root, index_updater=bad_index) as source:
        receipt = source.commit("write", (SourceChange(key, draft("saved"), None),))
        assert source.last_index_error == "index_unavailable"
        assert source.read(key) == receipt.changes[0]
    with FileProjectSource(root) as reopened:
        assert reopened.rebuild_index() == 2
        assert reopened.commit("write", (SourceChange(key, draft("saved"), None),)).replayed


def test_a08_external_change_during_snapshot_rejects_mixed_capture(tmp_path):
    root = initialized(tmp_path)
    key = ResourceKey("drafts", "d")
    with FileProjectSource(root) as source:
        source.commit("draft", (SourceChange(key, draft("before"), None),))

    def external_edit(checkpoint):
        if checkpoint == "snapshot_captured":
            (root / "source/drafts/d.json").write_bytes(draft("after"))

    with FileProjectSource(root, fault_hook=external_edit) as source:
        with pytest.raises(ServiceFailure) as error:
            source.capture_snapshot()
        reason(error, "unstable_source")


def test_a08_unknown_version_blocks_unrelated_mutation(tmp_path):
    root = initialized(tmp_path)
    marker = root / "deykit.project.json"
    value = json.loads(marker.read_bytes())
    value["schema_version"] = 2
    marker.write_text(json.dumps(value))
    with FileProjectSource(root) as source:
        with pytest.raises(ServiceFailure):
            source.commit("write", (SourceChange(ResourceKey("drafts", "d"), draft("x"), None),))
    assert not (root / "source/drafts/d.json").exists()
    assert json.loads(marker.read_bytes())["schema_version"] == 2


def test_casefold_scope_and_id_collisions(tmp_path):
    root = initialized(tmp_path)
    with FileProjectSource(root) as source:
        a = CaseRecord(id="Case", dataset_id="Data", input_kind="text", input_source='"x"')
        source.commit(
            "a", (SourceChange(ResourceKey("cases", "Case", ("Data",)), dump_record(a), None),)
        )
        for case_id, dataset in (("case", "Data"), ("other", "data")):
            b = CaseRecord(id=case_id, dataset_id=dataset, input_kind="text", input_source='"x"')
            with pytest.raises(ServiceFailure) as error:
                source.commit(
                    "b",
                    (
                        SourceChange(
                            ResourceKey("cases", case_id, (dataset,)), dump_record(b), None
                        ),
                    ),
                )
            reason(error, "casefold_collision")


def test_immutable_segment_allows_only_terminal_end(tmp_path):
    root = initialized(tmp_path)
    key = ResourceKey("segments", "s", ("r",))
    segment = RunSegment(id="s", run_id="r", started_at=STAMP, deadline_at="2026-10-05T12:10:00Z")
    with FileProjectSource(root) as source:
        first = source.commit("start", (SourceChange(key, dump_record(segment), None),)).changes[0]
        end = RunSegment(**{**segment.model_dump(), "ended_at": "2026-10-05T12:01:00Z"})
        ended = source.commit("end", (SourceChange(key, dump_record(end), first.etag),)).changes[0]
        with pytest.raises(ServiceFailure) as error:
            source.commit("rewrite", (SourceChange(key, dump_record(end), ended.etag),))
        reason(error, "immutable_record")
        changed = RunSegment(**{**segment.model_dump(), "retry_unknown": True})
        (root / "source/segments/r/s.json").write_bytes(dump_record(changed))
        with pytest.raises(ServiceFailure) as error:
            source.read(key)
        reason(error, "immutable_source_changed")


def test_safe_project_replay_no_new_id_or_clock_needed(tmp_path):
    root = initialized(tmp_path)

    def forbidden():
        raise AssertionError("must not generate a new identity")

    replay = ProjectService(
        lambda path, create: FileProjectSource(path, create=create), Clock(), forbidden
    )
    assert replay.create(root, "Project", "create").project.id == "project"
    with pytest.raises(ServiceFailure) as error:
        replay.create(root, "Different", "create")
    reason(error, "operation_id_conflict")


def test_deleted_immutable_identity_cannot_be_reused_or_replayed(tmp_path):
    root = initialized(tmp_path)
    key = ResourceKey("segments", "s", ("r",))
    segment = RunSegment(id="s", run_id="r", started_at=STAMP, deadline_at="2026-10-05T12:10:00Z")
    with FileProjectSource(root) as source:
        changes = (SourceChange(key, dump_record(segment), None),)
        source.commit("immutable", changes, intent_hash="a" * 64)
        (root / "source/segments/r/s.json").unlink()
        for action in (
            lambda: source.read(key),
            lambda: source.commit("reuse", changes),
            lambda: source.operation_receipt("immutable", intent_hash="a" * 64),
        ):
            with pytest.raises(ServiceFailure) as error:
                action()
            reason(error, "immutable_source_changed")


def test_terminal_segment_end_cannot_precede_start(tmp_path):
    root = initialized(tmp_path)
    key = ResourceKey("segments", "s", ("r",))
    segment = RunSegment(id="s", run_id="r", started_at=STAMP, deadline_at="2026-10-05T12:10:00Z")
    with FileProjectSource(root) as source:
        first = source.commit("start", (SourceChange(key, dump_record(segment), None),)).changes[0]
        invalid = RunSegment(**{**segment.model_dump(), "ended_at": "2026-10-05T11:59:59Z"})
        with pytest.raises(ServiceFailure) as error:
            source.commit("end", (SourceChange(key, dump_record(invalid), first.etag),))
        reason(error, "invalid_segment_end")


def test_project_create_replay_returns_original_receipt_after_rename(tmp_path):
    from deykit.contracts.records import ProjectRecord

    root = initialized(tmp_path)
    with FileProjectSource(root) as source:
        key = ResourceKey("project", "project")
        current = source.read(key)
        renamed = ProjectRecord(id="project", name="Renamed", created_at=STAMP)
        source.commit("rename", (SourceChange(key, dump_record(renamed), current.etag),))
    assert service().create(root, "Project", "create").project.name == "Project"
    assert service().open(root).project.name == "Renamed"


def test_reentrant_reads_recover_a_failed_commit_within_outer_context(tmp_path):
    root = initialized(tmp_path)
    key = ResourceKey("drafts", "d")
    crashed = False

    def failure(point):
        nonlocal crashed
        if point == "decided" and not crashed:
            crashed = True
            raise OSError("injected write failure")

    with FileProjectSource(root, fault_hook=failure) as source:
        with source.consistent_read():
            with pytest.raises(ServiceFailure):
                source.commit("write", (SourceChange(key, draft("recover me"), None),))
            assert load_record(DecisionDraft, source.read(key).body).editor_source == "recover me"
