from decimal import Decimal

import pytest

from deykit.application.errors import ServiceFailure
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.json_value import parse_json
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import ChoiceDefinition, DecisionDraft, DecisionRevision
from deykit.domain.definitions import definition_hash
from deykit.domain.import_mapping import ImportMapping, InputField


@pytest.mark.parametrize("source", [b"\xff", "\ud800"])
def test_invalid_utf8_source_has_safe_error_and_no_writes(project, source):
    storage, _, imports, _ = project
    before = storage.capture_snapshot()
    with pytest.raises(ServiceFailure) as failure:
        imports.preview(
            "data",
            source,
            format="jsonl",
            mapping=ImportMapping(input_kind="text", input_column="text"),
        )
    assert failure.value.error.reason == "invalid_utf8"
    assert storage.capture_snapshot() == before


@pytest.mark.parametrize(
    "line",
    [
        '{"text":"SECRET","text":"duplicate"}',
        '{"text":NaN}',
        '{"text":Infinity}',
        '{"text":-Infinity}',
        '{"text":"\\ud800"}',
        '["SECRET"]',
        "",
        '{"text":',
    ],
)
def test_jsonl_malformed_row_is_excluded_without_leaking_source(project, line):
    storage, _, imports, _ = project
    before = storage.capture_snapshot()
    preview = imports.preview(
        "data",
        '{"text":"valid"}\n' + line + "\n",
        format="jsonl",
        mapping=ImportMapping(input_kind="text", input_column="text"),
    )
    assert len(preview.valid_rows) == 1 and preview.exclusions[0].row == 2
    with pytest.raises(ServiceFailure) as failure:
        imports.commit(preview, operation_id="abort")
    assert "SECRET" not in str(failure.value)
    assert storage.capture_snapshot() == before


def test_jsonl_unicode_separators_and_crlf_preserve_data(project):
    imports = project[2]
    preview = imports.preview(
        "data",
        '{"text":"a\u2028b\u2029c"}\r\n{"text":"d"}\r\n',
        format="jsonl",
        mapping=ImportMapping(input_kind="text", input_column="text"),
    )
    assert len(preview.rows) == 2
    assert parse_json(preview.rows[0].case.input_source) == "a\u2028b\u2029c"


@pytest.mark.parametrize(
    "source,reason",
    [
        ("text,text\na,b\n", "invalid_csv_header"),
        (",text\na,b\n", "invalid_csv_header"),
        ('text\n"unterminated', "malformed_csv"),
        ('text\n"a"afterquote\n', "malformed_csv"),
        ("text\n" + "x" * 131073, "csv_field_resource_limit"),
        ("\ufefftext\nx", "unexpected_byte_order_mark"),
        ("text\n", "empty_import"),
    ],
)
def test_csv_lexical_failure_aborts_preview(project, source, reason):
    storage, _, imports, _ = project
    before = storage.capture_snapshot()
    with pytest.raises(ServiceFailure) as failure:
        imports.preview(
            "data",
            source,
            format="csv",
            mapping=ImportMapping(input_kind="text", input_column="text"),
        )
    assert failure.value.error.reason == reason
    assert storage.capture_snapshot() == before


def test_csv_string_cells_multiline_record_numbers_and_explicit_exact_json(project):
    imports = project[2]
    preview = imports.preview(
        "data",
        'text,number\n"first\nsecond",9007199254740993\nshort\n',
        format="csv",
        mapping=ImportMapping(
            input_kind="json",
            fields=(
                InputField(source="text", target="text"),
                InputField(source="number", target="number"),
            ),
        ),
    )
    assert parse_json(preview.rows[0].case.input_source) == {
        "text": "first\nsecond",
        "number": "9007199254740993",
    }
    assert preview.rows[0].source_line == 3
    assert preview.exclusions[0].row == 2 and preview.exclusions[0].source_line == 4
    precise = imports.preview(
        "data",
        "value\n0.123456789012345678901234567890123456789\n",
        format="csv",
        mapping=ImportMapping(
            input_kind="json", fields=(InputField(source="value", target="value", parse_json=True),)
        ),
    )
    assert parse_json(precise.rows[0].case.input_source)["value"] == Decimal(
        "0.123456789012345678901234567890123456789"
    )


@pytest.mark.parametrize(
    "extra",
    [
        '"expected_column":"text"',
        '"metadata_column":"text"',
        '"id_column":"text"',
        '"group_column":"text"',
        '"tags_column":"text"',
        '"split_column":"text"',
        '"expected_parse_json":true',
        '"tags_parse_json":true',
        '"metadata_parse_json":true',
        '"expected_column":"x","metadata_column":"x"',
        '"option_aliases":[{"value":"Alpha","option_id":"A"}]',
        '"unrecognized":"SECRET"',
    ],
)
def test_malformed_mapping_is_safe_structured_failure(project, extra):
    with pytest.raises(ServiceFailure) as failure:
        project[2].parse_mapping(
            '{"schema_version":1,"input_kind":"text","input_column":"text",' + extra + "}"
        )
    assert "SECRET" not in str(failure.value)


def test_mapped_labels_cannot_alias_input_field_even_with_different_target(project):
    with pytest.raises(ServiceFailure):
        project[2].parse_mapping(
            '{"schema_version":1,"input_kind":"json","fields":[{"source":"expected","target":"innocent"}],"expected_column":"expected"}'
        )


def test_current_draft_invalidated_after_preview_is_conflict(project):
    storage, _, imports, _ = project
    preview = imports.preview(
        "data",
        '{"input":{"text":"hello"}}',
        format="jsonl",
        mapping=ImportMapping(input_kind="json", input_column="input"),
        decision_id="decision",
    )
    stored = storage.read(ResourceKey("drafts", "decision"))
    draft = load_record(DecisionDraft, stored.body)
    storage.commit(
        "break-draft",
        (
            SourceChange(
                stored.key,
                dump_record(
                    draft.model_copy(update={"editor_source": "incomplete editor content"})
                ),
                stored.etag,
            ),
        ),
    )
    with pytest.raises(ServiceFailure) as failure:
        imports.commit(preview, operation_id="stale")
    assert failure.value.error.code == "conflict"
    assert storage.list_ids("cases", ("data",)) == ()


def test_explicit_revision_can_differ_from_current_draft_without_implicit_fallback(project):
    storage, _, imports, _ = project
    stored = storage.read(ResourceKey("drafts", "decision"))
    draft = load_record(DecisionDraft, stored.body)
    definition = load_record(ChoiceDefinition, draft.editor_source)
    revision = DecisionRevision(
        id="saved",
        decision_id="decision",
        definition=definition,
        content_hash=definition_hash(definition),
        created_at="2026-10-05T12:00:00Z",
    )
    storage.commit(
        "revision",
        (
            SourceChange(
                ResourceKey("revisions", "saved", ("decision",)), dump_record(revision), None
            ),
            SourceChange(
                stored.key,
                dump_record(draft.model_copy(update={"editor_source": "invalid current draft"})),
                stored.etag,
            ),
        ),
    )
    kwargs = dict(
        format="jsonl",
        mapping=ImportMapping(input_kind="json", input_column="input"),
        decision_id="decision",
    )
    with pytest.raises(ServiceFailure):
        imports.preview("data", '{"input":{"text":"hello"}}', **kwargs)
    preview = imports.preview(
        "data", '{"input":{"text":"hello"}}', decision_selector="saved", **kwargs
    )
    assert not preview.exclusions and preview.decision_selector == "saved"
    imports.commit(preview, operation_id="explicit-revision")


def test_two_previews_compete_for_dataset_revision(project):
    storage, datasets, imports, _ = project
    kwargs = dict(format="jsonl", mapping=ImportMapping(input_kind="text", input_column="text"))
    first = imports.preview("data", '{"text":"first"}', **kwargs)
    second = imports.preview("data", '{"text":"second"}', **kwargs)
    imports.commit(first, operation_id="winner")
    with pytest.raises(ServiceFailure) as failure:
        imports.commit(second, operation_id="loser")
    assert failure.value.error.code == "conflict"
    assert datasets.list_cases("data").total == 1
    assert len(storage.list_ids("cases", ("data",))) == 1
