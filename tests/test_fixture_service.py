"""Portable fixture sets persist as immutable source, independent of SQLite."""

import asyncio
import shutil

import pytest

from deykit.application.errors import ServiceFailure
from deykit.application.fixtures import FixtureService, StoredFixtureSet
from deykit.application.projects import ProjectService
from deykit.contracts.codec import dump_record
from deykit.contracts.json_value import bytes_hash
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import (
    CaseRecord,
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    DatasetRecord,
    DecisionRecord,
    FixtureBinding,
    FixtureSet,
    NormalizedAnswer,
)
from deykit.contracts.redaction import Sanitizer
from deykit.providers.choice import compile_choice
from deykit.providers.fixtures import fixture_set_hash, validate_fixture_set
from deykit.storage import FileProjectSource

STAMP = "2026-10-05T12:00:00Z"
MODEL = "authored-test-v1"


class Clock:
    def utc_now(self):
        return STAMP

    def monotonic(self):
        return 0.0


def binding(case_id="case", option_id="yes"):
    definition = ChoiceDefinition(
        input_kind="json",
        selected_fields=("text",),
        questions=(
            ChoiceQuestion(
                id="q",
                instructions="Choose",
                options=(ChoiceOption(id="yes", name="Yes"), ChoiceOption(id="no", name="No")),
            ),
        ),
    )
    compiled = compile_choice(definition, {"text": "hello"}, MODEL, adapter="fixture")
    return FixtureBinding(
        id="binding",
        case_id=case_id,
        request=compiled,
        answer=NormalizedAnswer(question_id="q", option_id=option_id, reported_model=MODEL),
    )


def initialized(tmp_path):
    root = tmp_path / "Fixture project ü"
    ProjectService(
        lambda path, create: FileProjectSource(path, create=create), Clock(), lambda: "project"
    ).create(root, "Project", "create-project")
    with FileProjectSource(root) as source:
        source.commit(
            "seed-context",
            (
                SourceChange(
                    ResourceKey("decisions", "decision"),
                    dump_record(DecisionRecord(id="decision", name="Decision")),
                    None,
                ),
                SourceChange(
                    ResourceKey("datasets", "dataset"),
                    dump_record(DatasetRecord(id="dataset", name="Data", created_at=STAMP)),
                    None,
                ),
                SourceChange(
                    ResourceKey("cases", "case", ("dataset",)),
                    dump_record(
                        CaseRecord(
                            id="case",
                            dataset_id="dataset",
                            input_kind="json",
                            input_source='{"text":"hello"}',
                        )
                    ),
                    None,
                ),
            ),
        )
    return root


def test_create_replay_copy_and_index_rebuild_preserve_authored_binding(tmp_path):
    root = initialized(tmp_path)
    source_text = dump_record(binding())
    with FileProjectSource(root) as source:
        service = FixtureService(source, Clock())
        first = service.create(
            "set",
            "decision",
            "dataset",
            "Authored",
            MODEL,
            (source_text,),
            operation_id="fixture-create",
        )
        assert service.list_ids() == ("set",)
        assert first.replayed is False
        assert service.read("set") == first
        replayed = service.create(
            "set",
            "decision",
            "dataset",
            "Authored",
            MODEL,
            (source_text,),
            operation_id="fixture-create",
        )
        assert replayed == first and replayed.replayed is True
        with pytest.raises(ServiceFailure) as changed:
            service.create(
                "set",
                "decision",
                "dataset",
                "Changed",
                MODEL,
                (source_text,),
                operation_id="fixture-create",
            )
        assert changed.value.error.reason == "operation_id_conflict"
        result = asyncio.run(
            service.transport_factory("set")
            .for_case("case")
            .dispatch(binding().request, timeout_seconds=1.0)
        )
        assert result.answer.option_id == "yes"
        with pytest.raises(ServiceFailure) as immutable:
            source.commit(
                "replace",
                (
                    SourceChange(
                        ResourceKey("fixtures", "set"), dump_record(first.fixture_set), first.etag
                    ),
                ),
            )
        assert immutable.value.error.reason == "immutable_record"
    copied = tmp_path / "Copied fixture project"
    shutil.copytree(root, copied)
    shutil.rmtree(copied / ".deykit")
    with FileProjectSource(copied) as reopened:
        assert reopened.rebuild_index() >= 4
        assert FixtureService(reopened, Clock()).read("set") == first


def test_missing_context_case_and_bad_binding_source_fail_without_partial_set(tmp_path):
    root = initialized(tmp_path)
    with FileProjectSource(root) as source:
        service = FixtureService(source, Clock())
        with pytest.raises(ServiceFailure) as missing:
            service.create(
                "set",
                "decision",
                "absent",
                "Authored",
                MODEL,
                (dump_record(binding()),),
                operation_id="missing",
            )
        assert missing.value.error.code == "not_found"
        with pytest.raises(ServiceFailure) as malformed:
            service.create(
                "set",
                "decision",
                "dataset",
                "Authored",
                MODEL,
                (b'{"schema_version":1,"schema_version":1}',),
                operation_id="malformed",
            )
        assert malformed.value.error.reason == "duplicate_key"
        with pytest.raises(ServiceFailure) as missing_case:
            service.create(
                "set",
                "decision",
                "dataset",
                "Authored",
                MODEL,
                (dump_record(binding(case_id="absent")),),
                operation_id="missing-case",
            )
        assert missing_case.value.error.reason == "fixture_case_missing"
        assert service.list_ids() == ()


def test_fixture_page_and_identity_summary_keep_requests_private_by_default(tmp_path):
    root = initialized(tmp_path)
    with FileProjectSource(root) as source:
        service = FixtureService(source, Clock())
        for fixture_id in ("a-set", "b-set", "c-set"):
            service.create(
                fixture_id,
                "decision",
                "dataset",
                "Authored",
                MODEL,
                (dump_record(binding()),),
                operation_id=f"create-{fixture_id}",
            )

        first = service.list(limit=2)
        assert [item.id for item in first.items] == ["a-set", "b-set"]
        assert first.total == 3 and first.next_cursor == "b-set"
        second = service.list(cursor=first.next_cursor, limit=2)
        assert [item.id for item in second.items] == ["c-set"]
        assert second.total == 3 and second.next_cursor is None
        summary = service.read_summary("a-set")
        assert summary.binding_count == 1
        assert summary.bindings[0].request_hash == binding().request.body_hash
        assert summary.requests == ()
        with_requests = service.read_summary("a-set", include_requests=True)
        assert with_requests.requests == (binding().request.body.decode("utf-8"),)

        with pytest.raises(ServiceFailure) as bad_limit:
            service.list(limit=0)
        assert bad_limit.value.error.reason == "invalid_page_limit"
        with pytest.raises(ServiceFailure) as bad_cursor:
            service.list(cursor="bad id")
        assert bad_cursor.value.error.reason == "invalid_resource_id"


def test_fixture_request_projection_redacts_without_rewriting_authored_hashes():
    selected_state = {
        "text": "Bearer fixture-secret",
        "api_key": "fixture-secret",
        "exact": 9007199254740993,
    }
    compiled = compile_choice(
        ChoiceDefinition(
            input_kind="json",
            selected_fields=("text", "api_key", "exact"),
            questions=(
                ChoiceQuestion(
                    id="q",
                    instructions="Choose",
                    options=(
                        ChoiceOption(id="yes", name="Yes"),
                        ChoiceOption(id="no", name="No"),
                    ),
                ),
            ),
        ),
        selected_state,
        MODEL,
        adapter="fixture",
    )
    original_body = compiled.body
    authored = binding()
    record = FixtureSet(
        id="fixture-set",
        decision_id="decision",
        dataset_id="dataset",
        name="Bearer fixture-secret",
        model_identity=MODEL,
        bindings=(authored.model_copy(update={"request": compiled}),),
        created_at=STAMP,
        content_hash="0" * 64,
    )
    record = record.model_copy(update={"content_hash": fixture_set_hash(record)})
    assert validate_fixture_set(record) == record
    summary = FixtureService.identity_summary(
        StoredFixtureSet(record, "fixture-etag"),
        include_requests=True,
        sanitizer=Sanitizer(("fixture-secret",)),
    )

    assert summary.name == "Bearer [REDACTED]"
    assert summary.model_identity == MODEL
    assert summary.bindings[0].model_identity == MODEL
    assert summary.bindings[0].request_hash == bytes_hash(original_body)
    assert "fixture-secret" not in summary.requests[0]
    assert '"api_key":"[REDACTED]"' in summary.requests[0]
    assert '"exact":9007199254740993' in summary.requests[0]


def test_fixture_profile_and_invalid_public_inputs(tmp_path):
    root = initialized(tmp_path)
    with FileProjectSource(root) as source:
        service = FixtureService(source, Clock())
        profile = service.create_profile("fixture-profile", MODEL, operation_id="profile-op")
        assert service.read_profile("fixture-profile") == profile
        assert (
            service.create_profile("fixture-profile", MODEL, operation_id="profile-op") == profile
        )
        assert profile.adapter == "fixture" and profile.destination == "fixture:jev-choice"
        assert profile.credential_ref is None
        with pytest.raises(ServiceFailure) as changed:
            service.create_profile("fixture-profile", "authored-other", operation_id="profile-op")
        assert changed.value.error.reason == "operation_id_conflict"
        for sources in (None, [dump_record(binding())], "invalid"):
            with pytest.raises(ServiceFailure) as invalid:
                service.create(
                    "set", "decision", "dataset", "Authored", MODEL, sources, operation_id="bad"
                )
            assert invalid.value.error.reason == "invalid_binding_sources"
        with pytest.raises(ServiceFailure) as invalid_name:
            service.create(
                "set",
                "decision",
                "dataset",
                3,
                MODEL,
                (dump_record(binding()),),
                operation_id="bad-name",
            )
        assert invalid_name.value.error.reason == "invalid_fixture_metadata"
