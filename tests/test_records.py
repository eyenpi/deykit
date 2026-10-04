import json

import pytest
from pydantic import ValidationError

from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import validate_resource_id
from deykit.contracts.json_value import JsonDocument, JsonError, bytes_hash
from deykit.contracts.ports import ResourceKey
from deykit.contracts.records import (
    CaseRecord,
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    CompiledRequest,
    DecisionDraft,
    DispatchOutcome,
    LabelRecord,
    ProjectRecord,
)
from deykit.domain.definitions import (
    definition_hash,
    label_applicability,
    missing_options,
    select_input,
)

STAMP = "2026-10-05T12:00:00Z"


def definition(*, name="A", options=("a", "b")):
    return ChoiceDefinition(
        input_kind="json",
        questions=(
            ChoiceQuestion(
                id="q",
                instructions="Choose",
                options=tuple(ChoiceOption(id=x, name=name if x == "a" else x) for x in options),
            ),
        ),
    )


def test_a04_renaming_preserves_expectations_deletion_exposes_incompatibility():
    label = LabelRecord(
        id="label",
        decision_id="decision",
        dataset_id="data",
        case_id="case",
        question_id="q",
        input_hash="a" * 64,
        acceptable_option_ids=("a",),
        provenance="human",
        updated_at=STAMP,
    )
    renamed = definition(name="Renamed")
    assert not label_applicability(label, renamed, "a" * 64)
    assert definition_hash(renamed) != definition_hash(definition())
    removed = definition(options=("b", "c"))
    assert label_applicability(label, removed, "a" * 64) == ("incompatible",)
    assert missing_options(removed, "q", ("a",)) == ("a",)
    assert label.acceptable_option_ids == ("a",)
    disputed = LabelRecord(**{**label.model_dump(), "status": "disputed"})
    assert label_applicability(disputed, removed, "b" * 64) == ("disputed", "stale", "incompatible")


def test_complete_input_validation_precedes_selection():
    d = ChoiceDefinition(
        input_kind="json",
        selected_fields=("shown",),
        input_schema_source='{"required":["hidden"],"properties":{"hidden":{"type":"integer"}}}',
        questions=definition().questions,
    )
    with pytest.raises(JsonError, match="input_schema_mismatch"):
        select_input(d, JsonDocument('{"shown":1}'))
    assert (
        select_input(d, JsonDocument('{"hidden":2,"shown":9007199254740993}')).source
        == '{"shown":9.007199254740993e15}'
    )


def test_arbitrary_source_strings_survive_immutable_record_codec():
    source = '{"n":0.123456789012345678901234567890123456789,"big":9007199254740993}'
    case = CaseRecord(id="c", dataset_id="d", input_kind="json", input_source=source)
    saved = dump_record(case)
    assert json.loads(saved)["input_source"] == source
    assert load_record(CaseRecord, saved) == case
    with pytest.raises(ValidationError):
        case.input_source = "{}"
    nested = definition()
    with pytest.raises(ValidationError):
        nested.questions[0].options[0].name = "changed"


def test_editable_invalid_draft_is_not_a_runnable_definition():
    draft = DecisionDraft(decision_id="d", editor_source='{"unfinished":', updated_at=STAMP)
    assert load_record(DecisionDraft, dump_record(draft)) == draft
    with pytest.raises(ValidationError):
        ChoiceDefinition.model_validate_json(draft.editor_source)


@pytest.mark.parametrize(
    "identifier",
    [
        "../a",
        ".",
        "..",
        "a/b",
        "a\\b",
        "C:foo",
        "%2e%2e",
        "NUL",
        "con",
        "COM1",
        "LPT9",
        "foo.",
        "foo ",
        "a\x00",
        "é",
        "a" * 129,
    ],
)
def test_cross_platform_resource_ids(identifier):
    with pytest.raises(ValueError):
        validate_resource_id(identifier)
    with pytest.raises(ValueError):
        ResourceKey("cases", identifier)


@pytest.mark.parametrize(
    "patch",
    [
        {"schema_version": 2},
        {"schema_version": True},
        {"schema_version": 1.0},
        {"schema_version": "1"},
        {"surprise": 1},
        {"id": 123},
        {"created_at": "2026-10-05"},
    ],
)
def test_strict_version_fields_and_types(patch):
    value = {"schema_version": 1, "id": "p", "name": "Project", "created_at": STAMP, **patch}
    with pytest.raises(JsonError, match="invalid_record"):
        load_record(ProjectRecord, json.dumps(value))


def test_missing_version_duplicate_records_and_exact_request_bytes():
    with pytest.raises(JsonError, match="missing_schema_version"):
        load_record(ProjectRecord, '{"id":"p"}')
    with pytest.raises(JsonError, match="duplicate_key"):
        load_record(ProjectRecord, '{"schema_version":1,"schema_version":1}')
    body = b'{"state":{"n":9007199254740993},"model":"authored"}'
    request = CompiledRequest(
        adapter="fixture",
        compiler="choice",
        compiler_version="1",
        requested_model="authored",
        destination="fixture:local",
        body=body,
        body_hash=bytes_hash(body),
    )
    assert load_record(CompiledRequest, dump_record(request)).body == body
    with pytest.raises(ValidationError, match="request_body_hash_mismatch"):
        CompiledRequest(**{**request.model_dump(), "body_hash": "0" * 64})


def test_unknown_cannot_silently_retry_and_safe_errors():
    error = ServiceError(code="provider_rejected", reason="connection_lost")
    outcome = DispatchOutcome(state="unknown", error=error)
    assert not outcome.retryable
    with pytest.raises(ValidationError):
        DispatchOutcome(state="unknown", error=error, retryable=True)
    with pytest.raises(ValidationError):
        ServiceError(code="internal_error", message="SECRET raw exception")
    assert error.safe_dict()["message"] == "The provider rejected the request."


@pytest.mark.parametrize("instructions", ["", " ", "\n\t", "\u2003"])
def test_blank_instructions_block_runnable_definition(instructions):
    with pytest.raises(ValidationError):
        ChoiceQuestion(id="q", instructions=instructions, options=definition().questions[0].options)


@pytest.mark.parametrize(
    "provenance", ["human", "authored_fixture", "imported_unknown", "model_generated"]
)
def test_documented_label_provenance(provenance):
    label = LabelRecord(
        id="l",
        decision_id="d",
        dataset_id="data",
        case_id="c",
        question_id="q",
        input_hash="a" * 64,
        acceptable_option_ids=("a",),
        provenance=provenance,
        updated_at=STAMP,
    )
    assert load_record(LabelRecord, dump_record(label)).provenance == provenance


@pytest.mark.parametrize("provenance", ["authored", "imported", "unknown"])
def test_ambiguous_label_provenance_is_rejected(provenance):
    with pytest.raises(ValidationError):
        LabelRecord(
            id="l",
            decision_id="d",
            dataset_id="data",
            case_id="c",
            question_id="q",
            input_hash="a" * 64,
            acceptable_option_ids=("a",),
            provenance=provenance,
            updated_at=STAMP,
        )


def test_nested_persisted_records_require_explicit_versions():
    from deykit.contracts.records import DecisionRevision

    revision = DecisionRevision(
        id="r", decision_id="d", definition=definition(), content_hash="a" * 64, created_at=STAMP
    )
    assert load_record(DecisionRevision, dump_record(revision)) == revision
    source = json.loads(dump_record(revision))
    del source["definition"]["schema_version"]
    with pytest.raises(JsonError, match="invalid_record"):
        load_record(DecisionRevision, json.dumps(source))
    source["definition"]["schema_version"] = True
    with pytest.raises(JsonError, match="invalid_record"):
        load_record(DecisionRevision, json.dumps(source))


def test_resource_keys_preserve_scoped_case_and_revision_ids():
    assert ResourceKey("cases", "case-1", ("dataset-a",)) != ResourceKey(
        "cases", "case-1", ("dataset-b",)
    )
    assert ResourceKey("revisions", "v1", ("decision-a",)) != ResourceKey(
        "revisions", "v1", ("decision-b",)
    )
    with pytest.raises(ValueError):
        ResourceKey("cases", "case-1", ("../data",))
    with pytest.raises(ValueError):
        ResourceKey("cases", "case-1", ["dataset"])


def test_persisted_hash_profiles_are_explicit_including_nested_records():
    from deykit.contracts.records import DatasetSnapshot, DecisionRevision, ResultSnapshot

    records = [
        DecisionRevision(
            id="r",
            decision_id="d",
            definition=definition(),
            content_hash="a" * 64,
            created_at=STAMP,
        ),
        ResultSnapshot(
            id="r",
            run_id="run",
            results=(),
            through_event_sequence=0,
            content_hash="a" * 64,
            created_at=STAMP,
        ),
    ]
    for record in records:
        for profile in (None, "unknown"):
            value = json.loads(dump_record(record))
            if profile is None:
                del value["hash_format"]
            else:
                value["hash_format"] = profile
            with pytest.raises(JsonError, match="invalid_record"):
                load_record(type(record), json.dumps(value))
    snapshot = DatasetSnapshot(
        id="s",
        dataset_id="d",
        content_hash="a" * 64,
        created_at=STAMP,
        cases=(CaseRecord(id="c", dataset_id="d", input_kind="json", input_source="{}"),),
    )
    value = json.loads(dump_record(snapshot))
    del value["cases"][0]["hash_format"]
    with pytest.raises(JsonError, match="invalid_record"):
        load_record(DatasetSnapshot, json.dumps(value))
