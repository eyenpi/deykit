"""The installed Sandbox is authored source, not an observed provider run."""

import asyncio
import shutil
from dataclasses import replace
from fractions import Fraction

import pytest

from deykit.application.demo import DemoService, read_sandbox_corpus
from deykit.application.errors import ServiceFailure
from deykit.application.fixtures import FixtureService
from deykit.application.projects import ProjectService
from deykit.contracts.codec import load_record
from deykit.contracts.json_value import JsonDocument, JsonError, parse_json
from deykit.contracts.ports import ResourceKey
from deykit.contracts.records import (
    ChoiceDefinition,
    ChoiceQuestion,
    DecisionRevision,
    LabelRecord,
)
from deykit.domain.definitions import select_input
from deykit.providers.choice import compile_choice
from deykit.storage import FileProjectSource
from deykit.storage.demo_staging import DemoStagingSource

STAMP = "2026-10-05T12:00:00Z"
EXPECTED_LABELS = {
    "ex-001": "question",
    "ex-002": "report",
    "ex-003": "question",
    "ex-004": "report",
    "ex-005": "request",
    "ex-006": "question",
    "ex-007": "other",
    "ex-008": "request",
    "ex-012": "question",
}
EXPECTED_ANSWERS = {
    "ex-001": "question",
    "ex-002": "report",
    "ex-003": "report",
    "ex-004": "report",
    "ex-005": "request",
    "ex-006": "question",
    "ex-007": "other",
    "ex-008": "question",
    "ex-009": "question",
    "ex-010": "report",
}


class Clock:
    def utc_now(self):
        return STAMP

    def monotonic(self):
        return 0.0


def source_factory(path, create):
    return FileProjectSource(path, create=create)


def ids():
    number = 0
    while True:
        number += 1
        yield f"demo-generated-{number}"


def demo(tmp_path):
    sequence = ids()
    root = tmp_path / "Sandbox ü"
    info = DemoService(
        source_factory, Clock(), lambda: next(sequence), staging_factory=DemoStagingSource
    ).create(
        root, operation_id="create-demo"
    )
    return root, info


def test_packaged_authored_corpus_has_explicit_unmeasured_scenarios():
    corpus = read_sandbox_corpus()
    assert corpus.evidence_mode == "authored_fixture"
    assert len(corpus.cases) == 12
    assert tuple(case.id for case in corpus.cases) == tuple(
        f"ex-{number:03d}" for number in range(1, 13)
    )
    assert {case.id: case.label_option_id for case in corpus.cases if case.label_option_id} == (
        EXPECTED_LABELS
    )
    assert {case.id: case.answer_option_id for case in corpus.cases if case.answer_option_id} == (
        EXPECTED_ANSWERS
    )
    assert [(case.id, case.outcome) for case in corpus.cases if case.outcome != "answer"] == [
        ("ex-011", "input_invalid"),
        ("ex-012", "response_error"),
    ]
    assert corpus.cases[2].probabilities_source == (
        '{"report":0.62,"question":0.2,"request":0.14,"other":0.04}'
    )


def test_demo_creates_portable_authored_records_and_independent_acceptance_arithmetic(tmp_path):
    root, info = demo(tmp_path)
    assert (info.case_count, info.binding_count, info.label_count) == (12, 11, 9)
    assert info.evidence_mode == "authored_fixture"
    assert ProjectService(source_factory, Clock(), lambda: "unused").open(root).project.id == (
        info.project_id
    )
    with FileProjectSource(root) as source:
        revision = load_record(
            DecisionRevision,
            source.read(ResourceKey("revisions", info.revision_id, (info.decision_id,))).body,
        )
        definition = revision.definition
        assert isinstance(definition, ChoiceDefinition)
        assert definition.selected_fields == ("text", "context")
        case_ids = source.list_ids("cases", (info.dataset_id,))
        assert case_ids == tuple(f"ex-{number:03d}" for number in range(1, 13))
        label_ids = source.list_ids("labels", (info.decision_id, info.dataset_id))
        assert len(label_ids) == 9
        labels = {
            label.case_id: label
            for label in (
                load_record(
                    LabelRecord,
                    source.read(
                        ResourceKey("labels", key, (info.decision_id, info.dataset_id))
                    ).body,
                )
                for key in label_ids
            )
        }
        assert {key: label.acceptable_option_ids for key, label in labels.items()} == {
            key: (option,) for key, option in EXPECTED_LABELS.items()
        }
        assert all(label.provenance == "authored_fixture" for label in labels.values())
        assert source.list_ids("label_history", (info.decision_id, info.dataset_id))

        fixtures = FixtureService(source, Clock())
        profile = fixtures.read_profile(info.profile_id)
        assert (profile.adapter, profile.destination, profile.credential_ref) == (
            "fixture",
            "fixture:jev-choice",
            None,
        )
        stored = fixtures.read(info.fixture_set_id)
        assert stored.fixture_set.evidence_mode == "authored_fixture"
        assert len(stored.fixture_set.bindings) == 11
        factory = fixtures.transport_factory(info.fixture_set_id, profile_id=info.profile_id)
        outcomes = {}
        invalid = []
        for case in read_sandbox_corpus().cases:
            if case.id == "ex-011":
                with pytest.raises(JsonError, match="input_schema_mismatch"):
                    select_input(definition, JsonDocument(case.input_source))
                assert all(binding.case_id != case.id for binding in stored.fixture_set.bindings)
                invalid.append(case.id)
                continue
            selected = select_input(definition, JsonDocument(case.input_source))
            assert set(selected.value) == {"text", "context"}
            compiled = compile_choice(
                definition, selected.value, profile.requested_model, adapter="fixture"
            )
            outcomes[case.id] = asyncio.run(
                factory.for_case(case.id).dispatch(compiled, timeout_seconds=1.0)
            )
        assert invalid == ["ex-011"]
        assert len(outcomes) == 11
        assert {
            key: result.answer.option_id for key, result in outcomes.items() if result.answer
        } == (EXPECTED_ANSWERS)
        assert outcomes["ex-012"].error.code == "response_invalid"
        assert outcomes["ex-012"].state == "known"
        assert parse_json(outcomes["ex-003"].answer.probabilities_source) == {
            "report": parse_json("0.62"),
            "question": parse_json("0.2"),
            "request": parse_json("0.14"),
            "other": parse_json("0.04"),
        }
        assert outcomes["ex-003"].answer.native_confidence_source is None
        assert outcomes["ex-001"].answer.probabilities_source is None

        scored = {
            key: result.answer.option_id
            for key, result in outcomes.items()
            if result.answer is not None and key in labels
        }
        assert len(scored) == 8
        correct = sum(value in labels[key].acceptable_option_ids for key, value in scored.items())
        assert correct == 6
        assert Fraction(correct, len(scored)) == Fraction(3, 4)
        assert {key for key, result in outcomes.items() if result.answer and key not in labels} == {
            "ex-009",
            "ex-010",
        }
        assert (len(EXPECTED_ANSWERS), len(case_ids)) == (10, 12)

        question = definition.questions[0]
        changed = ChoiceDefinition(
            input_kind=definition.input_kind,
            input_schema_source=definition.input_schema_source,
            selected_fields=definition.selected_fields,
            questions=(
                ChoiceQuestion(
                    id=question.id,
                    instructions=question.instructions,
                    options=tuple(reversed(question.options)),
                ),
            ),
        )
        selected = select_input(changed, JsonDocument(read_sandbox_corpus().cases[0].input_source))
        edited = compile_choice(changed, selected.value, profile.requested_model, adapter="fixture")
        missing = asyncio.run(factory.for_case("ex-001").dispatch(edited, timeout_seconds=1.0))
        assert missing.state == "not_sent" and missing.error.code == "missing_fixture"

    copied = tmp_path / "Copied Sandbox"
    shutil.copytree(root, copied)
    shutil.rmtree(copied / ".deykit")
    with FileProjectSource(copied) as recovered:
        assert recovered.rebuild_index() > 20
        assert FixtureService(recovered, Clock()).read(info.fixture_set_id) == stored


def test_demo_refuses_existing_user_path_without_overwrite(tmp_path):
    existing = tmp_path / "Sandbox"
    existing.mkdir()
    sentinel = existing / "user.txt"
    sentinel.write_text("keep me")
    with pytest.raises(ServiceFailure) as conflict:
        DemoService(
            source_factory, Clock(), staging_factory=DemoStagingSource
        ).create(existing, operation_id="demo-existing")
    assert conflict.value.error.reason == "demo_path_exists"
    assert sentinel.read_text() == "keep me"
    assert sorted(path.name for path in existing.iterdir()) == ["user.txt"]


def test_demo_stages_before_creating_and_replays_the_original_receipt(tmp_path):
    root = tmp_path / "Staged Sandbox"
    stage_saw_path: list[bool] = []

    def staging_factory():
        stage_saw_path.append(root.exists())
        return DemoStagingSource()

    service = DemoService(source_factory, Clock(), staging_factory=staging_factory)
    source, created = service._create_opened(root, operation_id="staged-demo")
    assert stage_saw_path == [False]
    assert created.replayed is False
    source.close()

    replay_source, replayed = service._create_opened(root, operation_id="staged-demo")
    try:
        assert stage_saw_path == [False]
        assert replayed.replayed is True
        assert replayed.project_id == created.project_id
        assert replayed.operation_id == created.operation_id
    finally:
        replay_source.close()


@pytest.mark.parametrize("mutation", ["operation_id", "etag", "incomplete"])
def test_demo_receipt_rejects_wrong_operation_or_row_hash(tmp_path, mutation):
    root, info = demo(tmp_path)
    source = FileProjectSource(root)
    service = DemoService(source_factory, Clock(), staging_factory=DemoStagingSource)
    receipt = source.operation_receipt(info.operation_id, intent_hash=service._intent())
    assert receipt is not None
    if mutation == "operation_id":
        corrupted = replace(receipt, operation_id="different-operation")
    elif mutation == "etag":
        first = replace(receipt.changes[0], etag="0" * 64)
        corrupted = replace(receipt, changes=(first, *receipt.changes[1:]))
    else:
        case = next(row for row in receipt.changes if row.key.collection == "cases")
        corrupted = replace(
            receipt,
            changes=tuple(row for row in receipt.changes if row.key != case.key),
        )
    with pytest.raises(ServiceFailure) as error:
        service._admit_receipt(corrupted, root, operation_id=info.operation_id)
    assert error.value.error.code == "incompatible_data"
    assert error.value.error.reason == "invalid_demo_receipt"
    source.close()


def test_demo_replay_uses_receipt_before_corpus_clock_or_ids(tmp_path, monkeypatch):
    root, created = demo(tmp_path)

    class ForbiddenClock:
        def utc_now(self):
            raise AssertionError("replay read the clock")

        def monotonic(self):
            raise AssertionError("replay read monotonic time")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("replay consulted current corpus or generated an ID")

    monkeypatch.setattr("deykit.application.demo.read_sandbox_corpus", forbidden)
    source, replayed = DemoService(
        source_factory,
        ForbiddenClock(),
        forbidden,
        staging_factory=forbidden,
    )._create_opened(root, operation_id=created.operation_id)
    try:
        assert replayed.replayed is True
        assert replayed.project_id == created.project_id
    finally:
        source.close()


def test_invalid_demo_corpus_does_not_create_the_requested_path(tmp_path, monkeypatch):
    root = tmp_path / "Invalid Sandbox"
    monkeypatch.setattr(
        "deykit.application.demo.read_sandbox_corpus",
        lambda: (_ for _ in ()).throw(ValueError("invalid fixture")),
    )
    with pytest.raises(ValueError):
        DemoService(source_factory, Clock(), staging_factory=DemoStagingSource).create(
            root, operation_id="invalid-demo"
        )
    assert not root.exists()


def test_demo_rejects_operation_id_already_used_for_another_intent(tmp_path):
    root = tmp_path / "Existing project"
    root.mkdir()
    with FileProjectSource(root, create=True) as source:
        ProjectService(source_factory, Clock(), lambda: "project-id").create_in(
            source, "Existing", "shared-operation"
        )
        staged: list[bool] = []

        def staging_factory():
            staged.append(True)
            return DemoStagingSource()

        with pytest.raises(ServiceFailure) as error:
            DemoService(source_factory, Clock(), staging_factory=staging_factory).create_in(
                source, root, operation_id="shared-operation"
            )
        assert error.value.error.code == "conflict"
        assert staged == []
