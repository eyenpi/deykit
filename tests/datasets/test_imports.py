from dataclasses import replace
from decimal import Decimal

import pytest

from deykit.application.datasets import CaseInput
from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.json_value import dump_json, parse_json
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import DecisionDraft, LabelRecord
from deykit.domain.definitions import select_input
from deykit.domain.import_mapping import ImportMapping, InputField, OptionAlias
from deykit.providers.choice import compile_choice
from deykit.storage import FileProjectSource


def mapping():
    return ImportMapping(
        input_kind="json", input_column="input", id_column="id", expected_column="expected"
    )


def oracle():
    return "\n".join(
        dump_json(
            {
                "id": f"row-{i}",
                "input": {} if i == 3 else {"text": f"Text{i}"},
                "expected": "bad" if i == 7 else "A",
            }
        )
        for i in range(1, 11)
    )


def test_a09_default_abort_explicit_eight_rows_one_transaction(project):
    source, datasets, imports, dataset = project
    prior = source.capture_snapshot()
    preview = imports.preview(
        "data", oracle(), format="jsonl", mapping=mapping(), decision_id="decision"
    )
    assert source.capture_snapshot() == prior
    assert len(preview.valid_rows) == 8
    assert [(row.row, row.errors[0].reason) for row in preview.exclusions] == [
        (3, "input_schema_mismatch"),
        (7, "unknown_expected_option"),
    ]
    with pytest.raises(ServiceFailure) as error:
        imports.commit(preview, operation_id="import-default")
    assert error.value.error.reason == "import_rows_invalid"
    assert source.capture_snapshot() == prior
    result = imports.commit(preview, operation_id="import-partial", skip_invalid=True)
    assert len(result.imported_case_ids) == 8
    assert tuple(row.row for row in result.exclusions) == (3, 7)
    assert datasets.list_cases("data").total == 8
    assert len(source.list_ids("labels", ("decision", "data"))) == 8
    assert len(source.list_ids("label_history", ("decision", "data"))) == 8
    assert result.dataset.etag != dataset.etag
    for label_id in source.list_ids("labels", ("decision", "data")):
        label = load_record(
            LabelRecord, source.read(ResourceKey("labels", label_id, ("decision", "data"))).body
        )
        assert label.provenance == "imported_unknown"
        assert (
            source.operation_history(ResourceKey("labels", label_id, ("decision", "data")))[
                0
            ].operation_id
            == "import-partial"
        )


def test_a10_id_conflicts_distinct_identical_input_flags_and_auto_ids_are_stable(project):
    _, _, imports, _ = project
    text = "\n".join(
        [
            '{"id":"a","input":{"text":"same"},"expected":"A"}',
            '{"id":"b","input":{"text":"same"},"expected":"B"}',
            '{"input":{"text":"auto"},"expected":"A"}',
        ]
    )
    preview = imports.preview(
        "data", text, format="jsonl", mapping=mapping(), decision_id="decision"
    )
    assert preview.rows[0].duplicate_input_ids == ("b",)
    assert preview.rows[1].duplicate_input_ids == ("a",)
    # A missing explicitly mapped ID column is invalid; an empty cell requests generation.
    assert preview.rows[2].errors[0].reason == "missing_column"
    text = text.replace('{"input":{"text":"auto"}', '{"id":"","input":{"text":"auto"}')
    preview = imports.preview(
        "data", text, format="jsonl", mapping=mapping(), decision_id="decision"
    )
    again = imports.preview("data", text, format="jsonl", mapping=mapping(), decision_id="decision")
    assert preview.preview_hash == again.preview_hash
    assert preview.rows[2].case.id == again.rows[2].case.id
    imports.commit(preview, operation_id="first")
    conflict = imports.preview(
        "data", text, format="jsonl", mapping=mapping(), decision_id="decision"
    )
    assert len(conflict.exclusions) == 3
    assert all(row.errors[0].reason == "case_id_conflict" for row in conflict.exclusions)


def test_a11_explicit_csv_mapping_separates_labels_from_model_input(project):
    source, _, imports, _ = project
    text = (
        'id,text,context,expected,metadata\ncase,Hello,"{""big"":9007199254740993}",Alpha,PRIVATE\n'
    )
    mapped = ImportMapping(
        input_kind="json",
        fields=(
            InputField(source="text", target="text"),
            InputField(source="context", target="context", parse_json=True),
        ),
        id_column="id",
        expected_column="expected",
        metadata_column="metadata",
        option_aliases=(OptionAlias(value="Alpha", option_id="A"),),
    )
    preview = imports.preview("data", text, format="csv", mapping=mapped, decision_id="decision")
    assert not preview.exclusions
    case = preview.rows[0].case
    assert parse_json(case.input_source) == {
        "text": "Hello",
        "context": {"big": Decimal("9007199254740993")},
    }
    assert case.metadata_source == '"PRIVATE"'
    draft = load_record(DecisionDraft, source.read(ResourceKey("drafts", "decision")).body)
    from deykit.contracts.json_value import JsonDocument
    from deykit.contracts.records import ChoiceDefinition

    definition = load_record(ChoiceDefinition, draft.editor_source)
    compiled = compile_choice(
        definition, select_input(definition, JsonDocument(case.input_source)).value, "jev-1.13.0"
    )
    assert parse_json(compiled.body)["state"] == {"text": "Hello"}
    assert b'"expected"' not in compiled.body and b"PRIVATE" not in compiled.body


@pytest.mark.parametrize("change", ["draft", "dataset", "external_case"])
def test_changed_context_between_preview_commit_is_conflict(project, change):
    source, datasets, imports, dataset = project
    preview = imports.preview(
        "data",
        '{"id":"a","input":{"text":"Hello"},"expected":"A"}',
        format="jsonl",
        mapping=mapping(),
        decision_id="decision",
    )
    if change == "draft":
        stored = source.read(ResourceKey("drafts", "decision"))
        original = load_record(DecisionDraft, stored.body)
        updated = original.model_copy(
            update={
                "editor_source": original.editor_source.replace("Choose.", "Choose differently.")
            }
        )
        source.commit(
            "draft-change", (SourceChange(stored.key, dump_record(updated), stored.etag),)
        )
    elif change == "dataset":
        datasets.add_case(
            "data",
            CaseInput(input_kind="text", input_source='"new"'),
            expected_dataset_etag=dataset.etag,
            operation_id="other",
        )
    else:
        from deykit.contracts.records import CaseRecord

        # Simulate an external editor adding a valid source without touching dataset metadata.
        folder = source.root / "source/cases/data"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "external.json").write_bytes(
            dump_record(
                CaseRecord(
                    id="external", dataset_id="data", input_kind="text", input_source='"external"'
                )
            )
        )
    with pytest.raises(ServiceFailure) as error:
        imports.commit(preview, operation_id="stale")
    assert error.value.error.code == "conflict"
    assert source.read(ResourceKey("cases", "a", ("data",))) is None


def test_import_operation_replay_after_later_edits_retains_original_result(project):
    _, datasets, imports, _ = project
    preview = imports.preview(
        "data",
        '{"id":"a","input":{"text":"Hello"},"expected":"A"}',
        format="jsonl",
        mapping=mapping(),
        decision_id="decision",
    )
    first = imports.commit(preview, operation_id="same")
    datasets.update(
        "data",
        name="Later",
        metadata_source="{}",
        expected_etag=first.dataset.etag,
        operation_id="later",
    )
    replay = imports.commit(preview, operation_id="same")
    assert replay.replayed and replay.dataset == first.dataset
    with pytest.raises(ServiceFailure) as failure:
        imports.commit(preview, operation_id="same", skip_invalid=True)
    assert failure.value.error.reason == "operation_id_conflict"


@pytest.mark.parametrize(
    "checkpoint,committed",
    [("prepared", False), ("decided", True), ("applied:0", True), ("applied:2", True)],
)
def test_import_crash_exposes_complete_old_or_new_cases_labels_metadata(
    project, checkpoint, committed
):
    source, datasets, imports, dataset = project
    preview = imports.preview(
        "data",
        '{"id":"a","input":{"text":"Hello"},"expected":"A"}',
        format="jsonl",
        mapping=mapping(),
        decision_id="decision",
    )

    class Crash(BaseException):
        pass

    def crash(stage):
        if stage == checkpoint:
            raise Crash

    source._hook = crash
    with pytest.raises(Crash):
        imports.commit(preview, operation_id="crash")
    source._hook = lambda _: None
    with FileProjectSource(source.root) as recovered:
        assert len(recovered.list_ids("cases", ("data",))) == int(committed)
        assert len(recovered.list_ids("labels", ("decision", "data"))) == int(committed)
        assert len(recovered.list_ids("label_history", ("decision", "data"))) == int(committed)
        assert (recovered.read(ResourceKey("datasets", "data")).etag != dataset.etag) is committed


def test_tampered_preview_rejected(project):
    imports = project[2]
    preview = imports.preview(
        "data",
        '{"text":"Hi"}',
        format="jsonl",
        mapping=ImportMapping(input_kind="text", input_column="text"),
    )
    with pytest.raises(ServiceFailure) as failure:
        imports.commit(
            replace(preview, source_text='{"text":"different"}'), operation_id="tampered"
        )
    assert failure.value.error.reason == "invalid_import_preview"
