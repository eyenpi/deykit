"""Portable fixture sets persist as immutable source, independent of SQLite."""

import asyncio
import shutil

import pytest

from deykit.application.errors import ServiceFailure
from deykit.application.fixtures import FixtureService
from deykit.application.projects import ProjectService
from deykit.contracts.codec import dump_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import (
    CaseRecord,
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    DatasetRecord,
    DecisionRecord,
    FixtureBinding,
    NormalizedAnswer,
)
from deykit.providers.choice import compile_choice
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
        assert service.read("set") == first
        assert (
            service.create(
                "set",
                "decision",
                "dataset",
                "Authored",
                MODEL,
                (source_text,),
                operation_id="fixture-create",
            )
            == first
        )
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
