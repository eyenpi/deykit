"""Decision service against the actual journaled portable source."""

from pathlib import Path
from threading import Event, Thread

import pytest

from deykit.application.definitions import DecisionService
from deykit.application.errors import ServiceFailure
from deykit.application.projects import ProjectService
from deykit.contracts.codec import dump_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import (
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    DatasetRecord,
    LabelRecord,
    RegressionRecord,
)
from deykit.storage import FileProjectSource

STAMP = "2026-10-05T12:00:00Z"


class Clock:
    def utc_now(self) -> str:
        return STAMP

    def monotonic(self) -> float:
        return 0.0


def definition(*, options=("one", "two"), schema='{"type":"object"}') -> str:
    return dump_record(
        ChoiceDefinition(
            input_kind="json",
            input_schema_source=schema,
            selected_fields=("shown",),
            questions=(
                ChoiceQuestion(
                    id="q",
                    instructions="Choose",
                    options=tuple(ChoiceOption(id=option, name=option) for option in options),
                ),
            ),
        )
    ).decode()


def opened(root: Path) -> FileProjectSource:
    return FileProjectSource(root)


def initialized(tmp_path: Path) -> Path:
    root = tmp_path / "Portable project ü"
    ProjectService(
        lambda path, create: FileProjectSource(path, create=create), Clock(), lambda: "project"
    ).create(root, "Project", "project-create")
    return root


def test_real_source_revision_replay_history_and_external_version(tmp_path):
    root = initialized(tmp_path)
    ids = iter(("revision-one", "revision-two"))
    with opened(root) as source:
        service = DecisionService(source, Clock(), lambda: next(ids))
        created = service.create("d", "D", definition(), operation_id="create")
        first = service.save(
            "d",
            expected_draft_etag=created.draft.etag,
            expected_decision_etag=created.decision.etag,
            operation_id="save-one",
        )
        edited = service.update_draft(
            "d",
            definition(options=("two", "three")),
            expected_etag=service.read("d").draft.etag,
            operation_id="edit",
        )
        second = service.save(
            "d",
            expected_draft_etag=edited.etag,
            expected_decision_etag=service.read("d").decision.etag,
            operation_id="save-two",
        )
        assert [item.record.id for item in service.history("d").items] == [
            "revision-one",
            "revision-two",
        ]
        assert (
            service.revision("d", first.record.id).record.definition.questions[0].options[0].id
            == "one"
        )
        assert (
            service.revision("d", second.record.id).record.definition.questions[0].options[0].id
            == "two"
        )
        assert (
            service.save(
                "d",
                expected_draft_etag=created.draft.etag,
                expected_decision_etag=created.decision.etag,
                operation_id="save-one",
            )
            == first
        )
        with pytest.raises(ServiceFailure) as changed:
            service.save(
                "d",
                expected_draft_etag=created.draft.etag,
                expected_decision_etag=created.decision.etag,
                operation_id="save-one",
                note="changed",
            )
        assert changed.value.error.reason == "operation_id_conflict"
    path = root / "source" / "drafts" / "d.json"
    path.write_text(path.read_text().replace('"schema_version":1', '"schema_version":2'))
    with opened(root) as source:
        service = DecisionService(source, Clock())
        with pytest.raises(ServiceFailure) as unsupported:
            service.rename("d", "New", expected_etag=created.decision.etag, operation_id="rename")
        assert unsupported.value.error.code == "validation_error"


def test_real_source_option_deletion_reports_label_and_regression(tmp_path):
    root = initialized(tmp_path)
    with opened(root) as source:
        ids = iter(("rev-one",))
        service = DecisionService(source, Clock(), lambda: next(ids))
        created = service.create("d", "D", definition(), operation_id="create")
        saved = service.save(
            "d",
            expected_draft_etag=created.draft.etag,
            expected_decision_etag=created.decision.etag,
            operation_id="save",
        )
        dataset = DatasetRecord(id="data", name="Data", created_at=STAMP)
        label = LabelRecord(
            id="label",
            decision_id="d",
            dataset_id="data",
            case_id="case",
            question_id="q",
            input_hash="a" * 64,
            acceptable_option_ids=("one",),
            provenance="human",
            updated_at=STAMP,
        )
        regression = RegressionRecord(
            id="regression",
            decision_revision_id=saved.record.id,
            dataset_id="data",
            case_id="case",
            question_id="q",
            input_source='{"shown":"x"}',
            input_hash="a" * 64,
            acceptable_option_ids=("one",),
            reason="Expected one",
            created_at=STAMP,
        )
        source.commit(
            "expectations",
            (
                SourceChange(ResourceKey("datasets", "data"), dump_record(dataset), None),
                SourceChange(
                    ResourceKey("labels", "label", ("d", "data")), dump_record(label), None
                ),
                SourceChange(
                    ResourceKey("regressions", "regression"), dump_record(regression), None
                ),
            ),
        )
        service.update_draft(
            "d",
            definition(options=("two", "three")),
            expected_etag=service.read("d").draft.etag,
            operation_id="edit",
        )
        diff = service.diff("d", saved.record.id, "draft")
        assert diff.removed_option_ids == ("one",)
        assert [
            (ref.kind, ref.resource_id, ref.missing_option_ids)
            for ref in diff.incompatible_references
        ] == [
            ("label", "label", ("one",)),
            ("regression", "regression", ("one",)),
        ]
        assert source.read(ResourceKey("labels", "label", ("d", "data"))).body == dump_record(label)


def test_archive_waits_for_draft_update_source_boundary(tmp_path):
    root = initialized(tmp_path)
    with opened(root) as first, opened(root) as second:
        base = DecisionService(first, Clock()).create("d", "D", definition(), operation_id="create")
        started = Event()
        finished = Event()
        errors: list[Exception] = []

        def archive() -> None:
            started.set()
            try:
                DecisionService(second, Clock()).archive(
                    "d", expected_etag=base.decision.etag, operation_id="archive"
                )
            except Exception as error:
                errors.append(error)
            finally:
                finished.set()

        class InterleavingClock(Clock):
            def utc_now(self) -> str:
                worker = Thread(target=archive, daemon=True)
                worker.start()
                assert started.wait(2)
                if finished.wait(0.1):
                    assert isinstance(errors[0], ServiceFailure)
                    assert errors[0].error.reason == "source_busy"
                return STAMP

        draft = DecisionService(first, InterleavingClock()).update_draft(
            "d",
            definition(options=("two", "three")),
            expected_etag=base.draft.etag,
            operation_id="edit",
        )
        assert finished.wait(2)
        if errors:
            DecisionService(second, Clock()).archive(
                "d", expected_etag=base.decision.etag, operation_id="archive"
            )
        assert draft.record.editor_source == definition(options=("two", "three"))
        with pytest.raises(ServiceFailure) as archived:
            DecisionService(first, Clock()).update_draft(
                "d", "later", expected_etag=draft.etag, operation_id="late-edit"
            )
        assert archived.value.error.reason == "decision_archived"
