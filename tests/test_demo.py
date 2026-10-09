"""The installed Sandbox is authored source, not an observed provider run."""

import asyncio
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from fractions import Fraction
from threading import Barrier, Event

import pytest

from deykit.application.demo import DemoService, read_sandbox_corpus
from deykit.application.errors import ServiceFailure
from deykit.application.fixtures import FixtureService
from deykit.application.projects import ProjectService
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.json_value import JsonDocument, JsonError, parse_json
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import (
    ChoiceDefinition,
    ChoiceQuestion,
    DecisionRevision,
    LabelRecord,
    ProjectRecord,
)
from deykit.domain.definitions import select_input
from deykit.providers.choice import compile_choice
from deykit.storage import FileProjectSource
from deykit.storage.demo_staging import DemoStagingSource
from deykit.storage.demo_destination import FileDemoDestinationFactory

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
        source_factory, Clock(), lambda: next(sequence), staging_factory=DemoStagingSource,
        destination_factory=FileDemoDestinationFactory(),
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
            source_factory, Clock(), staging_factory=DemoStagingSource,
            destination_factory=FileDemoDestinationFactory(),
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

    service = DemoService(source_factory, Clock(), staging_factory=staging_factory, destination_factory=FileDemoDestinationFactory())
    source, created = service.create_opened(root, operation_id="staged-demo")
    assert stage_saw_path == [False]
    assert created.replayed is False
    source.close()

    replay_source, replayed = service.create_opened(root, operation_id="staged-demo")
    try:
        assert stage_saw_path == [False]
        assert replayed.replayed is True
        assert replayed.project_id == created.project_id
        assert replayed.operation_id == created.operation_id
    finally:
        replay_source.close()


def test_destination_port_orders_fresh_create_and_transfers_source_ownership(tmp_path):
    events: list[str] = []
    root = tmp_path / "Port Sandbox"
    delegate = FileDemoDestinationFactory()

    class TrackingSource:
        def __init__(self, source):
            self.source = source
            self.close_count = 0

        def __getattr__(self, name):
            value = getattr(self.source, name)
            if name == "operation_receipt":
                def operation_receipt(*args, **kwargs):
                    events.append("final_receipt")
                    return value(*args, **kwargs)
                return operation_receipt
            if name == "commit":
                def commit(*args, **kwargs):
                    events.append("commit")
                    return value(*args, **kwargs)
                return commit
            return value

        def close(self):
            self.close_count += 1
            self.source.close()

    class TrackingDestinationFactory:
        sources: list[TrackingSource] = []

        def open_existing(self, path, *, operation_id, intent_hash):
            events.append("open_existing")
            candidate = delegate.open_existing(
                path, operation_id=operation_id, intent_hash=intent_hash
            )
            if candidate is None:
                return None
            tracked = TrackingSource(candidate.source)
            self.sources.append(tracked)
            return type(candidate)(tracked, candidate.receipt)

        def create_exclusive(self, path):
            events.append("create_exclusive")
            tracked = TrackingSource(delegate.create_exclusive(path))
            self.sources.append(tracked)
            return tracked

    stage_sources = []

    class TrackingStagingSource(DemoStagingSource):
        def __init__(self):
            super().__init__()
            self.close_count = 0

        def close(self):
            self.close_count += 1
            events.append("stage_complete")
            super().close()

    def staging_factory():
        events.append("stage_begin")
        stage = TrackingStagingSource()
        stage_sources.append(stage)
        return stage

    destinations = TrackingDestinationFactory()
    service = DemoService(
        source_factory,
        Clock(),
        staging_factory=staging_factory,
        destination_factory=destinations,
    )
    retained, created = service.create_opened(root, operation_id="port-demo")
    assert events == [
        "open_existing",
        "stage_begin",
        "stage_complete",
        "create_exclusive",
        "final_receipt",
        "commit",
    ]
    assert retained is destinations.sources[0]
    assert retained.close_count == 0
    assert len(stage_sources) == 1 and stage_sources[0].close_count == 1
    retained.close()
    assert retained.close_count == 1

    replay_service = DemoService(
        source_factory,
        Clock(),
        staging_factory=staging_factory,
        destination_factory=destinations,
    )
    replay = replay_service.create(root, operation_id=created.operation_id)
    assert replay.replayed is True
    assert destinations.sources[-1].close_count == 1
    assert events[-2:] == ["open_existing", "final_receipt"]
    assert len(stage_sources) == 1 and stage_sources[0].close_count == 1


@pytest.mark.parametrize("mutation", ["operation_id", "etag", "incomplete"])
def test_demo_receipt_rejects_wrong_operation_or_row_hash(tmp_path, mutation):
    root, info = demo(tmp_path)
    source = FileProjectSource(root)
    service = DemoService(source_factory, Clock(), staging_factory=DemoStagingSource, destination_factory=FileDemoDestinationFactory())
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
    with FileProjectSource(root) as source:
        stored = source.read(ResourceKey("project", created.project_id))
        assert stored is not None
        project = load_record(ProjectRecord, stored.body)
        edited = ProjectRecord(
            id=project.id,
            name="Edited after the original demo",
            created_at=project.created_at,
            default_provider_id=project.default_provider_id,
        )
        source.commit(
            "edit-after-demo",
            (SourceChange(stored.key, dump_record(edited), stored.etag),),
        )

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
        destination_factory=FileDemoDestinationFactory(),
    ).create_opened(root, operation_id=created.operation_id)
    try:
        assert replayed.replayed is True
        assert replayed.project_id == created.project_id
    finally:
        source.close()

    copied = root.parent / "Copied without cache"
    shutil.copytree(root, copied)
    shutil.rmtree(copied / ".deykit")
    copied_replay = DemoService(
        source_factory,
        ForbiddenClock(),
        forbidden,
        staging_factory=forbidden,
        destination_factory=FileDemoDestinationFactory(),
    ).create(copied, operation_id=created.operation_id)
    assert copied_replay.replayed is True
    assert copied_replay.project_id == created.project_id


def test_invalid_demo_corpus_does_not_create_the_requested_path(tmp_path, monkeypatch):
    root = tmp_path / "Invalid Sandbox"
    monkeypatch.setattr(
        "deykit.application.demo.read_sandbox_corpus",
        lambda: (_ for _ in ()).throw(ValueError("invalid fixture")),
    )
    with pytest.raises(ValueError):
        DemoService(source_factory, Clock(), staging_factory=DemoStagingSource, destination_factory=FileDemoDestinationFactory()).create(
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
            DemoService(source_factory, Clock(), staging_factory=staging_factory, destination_factory=FileDemoDestinationFactory()).create_in(
                source, root, operation_id="shared-operation"
            )
        assert error.value.error.code == "conflict"
        assert staged == []
        assert not source.files.closed


DEMO_CRASH_CHILD = r"""
import os, sys
from pathlib import Path
from deykit.application.demo import DemoService
from deykit.storage import FileProjectSource
from deykit.storage.demo_staging import DemoStagingSource
from deykit.storage.demo_destination import FileDemoDestinationFactory

root = Path(sys.argv[1])
checkpoint = sys.argv[2]
def source_factory(path, create):
    return FileProjectSource(path, create=create)

def fault(point):
    if point == checkpoint:
        os._exit(73)

DemoService(source_factory, type('Clock', (), {
    'utc_now': lambda self: '2026-10-05T12:00:00Z',
    'monotonic': lambda self: 0.0,
})(), staging_factory=DemoStagingSource, destination_factory=FileDemoDestinationFactory(fault_hook=fault)).create(root, operation_id='crashed-demo')
"""


@pytest.mark.parametrize(
    "checkpoint,committed",
    [("prepared", False), ("decided", True), ("applied:0", True), ("archived", True)],
)
def test_demo_process_crash_recovers_only_the_real_atomic_decision(
    tmp_path, checkpoint, committed
):
    root = tmp_path / f"Sandbox {checkpoint}"
    result = subprocess.run(
        [sys.executable, "-c", DEMO_CRASH_CHILD, str(root), checkpoint],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 73, result.stderr.decode()

    if not committed:
        before = tuple(
            sorted(
                (path.relative_to(root).as_posix(), path.is_dir(),
                 None if path.is_dir() else path.read_bytes())
                for path in root.rglob("*")
            )
        )
        with pytest.raises(ServiceFailure) as refused:
            DemoService(
                source_factory,
                Clock(),
                staging_factory=DemoStagingSource,
                destination_factory=FileDemoDestinationFactory(),
            ).create(root, operation_id="crashed-demo")
        assert refused.value.error.reason == "demo_path_exists"
        after = tuple(
            sorted(
                (path.relative_to(root).as_posix(), path.is_dir(),
                 None if path.is_dir() else path.read_bytes())
                for path in root.rglob("*")
            )
        )
        assert after == before
        with FileProjectSource(root) as source:
            assert source.capture_snapshot() == ()
            assert source.operation_receipt(
                "crashed-demo", intent_hash=DemoService._intent()
            ) is None
        return

    with FileProjectSource(root) as source:
        records = source.capture_snapshot()
        receipt = source.operation_receipt(
            "crashed-demo", intent_hash=DemoService._intent()
        )
        assert receipt is not None
        assert receipt.replayed is True
        assert len(records) == len(receipt.changes)
        assert {row.key: (row.body, row.etag) for row in records} == {
            row.key: (row.body, row.etag) for row in receipt.changes
        }
        original = tuple((row.key, row.body, row.etag) for row in receipt.changes)

    replay = DemoService(
        source_factory, Clock(), staging_factory=DemoStagingSource,
        destination_factory=FileDemoDestinationFactory(),
    ).create(root, operation_id="crashed-demo")
    assert replay.replayed is True
    assert (replay.case_count, replay.binding_count, replay.label_count) == (12, 11, 9)
    with FileProjectSource(root) as source:
        receipt = source.operation_receipt(
            "crashed-demo", intent_hash=DemoService._intent()
        )
        assert receipt is not None
        assert tuple((row.key, row.body, row.etag) for row in receipt.changes) == original


@pytest.mark.parametrize("corruption", ["decision", "manifest", "blob"])
def test_corrupt_decided_demo_is_refused_without_recovery_writes(tmp_path, corruption):
    root = tmp_path / f"Corrupt {corruption}"
    result = subprocess.run(
        [sys.executable, "-c", DEMO_CRASH_CHILD, str(root), "decided"],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 73, result.stderr.decode()
    journal = root / "history" / "journal" / "crashed-demo"
    target = {
        "decision": journal / "commit.json",
        "manifest": journal / "manifest.json",
        "blob": journal / "new-0.json",
    }[corruption]
    target.write_bytes(b"corrupt bytes")
    before = tuple(
        sorted(
            (path.relative_to(root).as_posix(), path.is_dir(),
             None if path.is_dir() else path.read_bytes())
            for path in root.rglob("*")
        )
    )
    with pytest.raises(ServiceFailure):
        DemoService(
            source_factory,
            Clock(),
            staging_factory=DemoStagingSource,
            destination_factory=FileDemoDestinationFactory(),
        ).create(root, operation_id="crashed-demo")
    after = tuple(
        sorted(
            (path.relative_to(root).as_posix(), path.is_dir(),
             None if path.is_dir() else path.read_bytes())
            for path in root.rglob("*")
        )
    )
    assert after == before


def test_readonly_receipt_inspection_retries_decided_journal_archival(tmp_path, monkeypatch):
    """A barrier-controlled recovery exercises relocation without hostile-race claims."""
    root = tmp_path / "Relocating demo"
    result = subprocess.run(
        [sys.executable, "-c", DEMO_CRASH_CHILD, str(root), "decided"],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 73, result.stderr.decode()

    entered_journal_inspection = Event()
    continue_inspection = Event()
    original_inspection = FileProjectSource._peek_receipt_folder

    def pause_on_journal(self, folder, operation_id, *, intent_hash):
        if folder == ("history", "journal", "crashed-demo"):
            entered_journal_inspection.set()
            if not continue_inspection.wait(timeout=30):
                raise AssertionError("receipt inspector was not released")
        return original_inspection(
            self, folder, operation_id, intent_hash=intent_hash
        )

    monkeypatch.setattr(FileProjectSource, "_peek_receipt_folder", pause_on_journal)
    factory = FileDemoDestinationFactory()

    def inspect():
        candidate = factory.open_existing(
            root,
            operation_id="crashed-demo",
            intent_hash=DemoService._intent(),
        )
        assert candidate is not None
        try:
            info = DemoService(
                source_factory,
                Clock(),
                staging_factory=DemoStagingSource,
                destination_factory=factory,
            )._admit_receipt(
                candidate.receipt, root, operation_id="crashed-demo"
            )
            return candidate.receipt, info
        finally:
            candidate.source.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        inspection = pool.submit(inspect)
        try:
            assert entered_journal_inspection.wait(timeout=10)
            recovery_source = FileProjectSource(root)
            try:
                recovered = recovery_source.operation_receipt(
                    "crashed-demo", intent_hash=DemoService._intent()
                )
            finally:
                recovery_source.close()
            assert recovered is not None
            after_recovery = tuple(
                sorted(
                    (
                        path.relative_to(root).as_posix(),
                        path.is_dir(),
                        None if path.is_dir() else path.read_bytes(),
                    )
                    for path in root.rglob("*")
                )
            )
        finally:
            continue_inspection.set()
        inspected, info = inspection.result(timeout=30)

    after_inspection = tuple(
        sorted(
            (
                path.relative_to(root).as_posix(),
                path.is_dir(),
                None if path.is_dir() else path.read_bytes(),
            )
            for path in root.rglob("*")
        )
    )
    assert after_inspection == after_recovery
    assert inspected.operation_id == recovered.operation_id
    assert inspected.changes == recovered.changes
    assert info.operation_id == "crashed-demo"
    assert info.replayed is True


def test_concurrent_demo_creates_publish_one_receipt_and_replay_its_identity(tmp_path):
    root = tmp_path / "Concurrent Sandbox"
    root.mkdir()
    barrier = Barrier(2)

    class SynchronizedStagingSource(DemoStagingSource):
        def capture_snapshot(self, keys=None):
            records = super().capture_snapshot(keys)
            barrier.wait(timeout=30)
            return records

    with FileProjectSource(root) as source:
        def create():
            service = DemoService(
                source_factory,
                Clock(),
                staging_factory=SynchronizedStagingSource,
                destination_factory=FileDemoDestinationFactory(),
            )
            return service.create_in(source, root, operation_id="parallel-demo")

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(create) for _ in range(2)]
            outcomes = []
            failures = []
            for future in futures:
                try:
                    outcomes.append(future.result(timeout=60))
                except ServiceFailure as error:
                    failures.append(error.error.reason)

        assert outcomes
        assert set(failures) <= {"source_busy"}
        assert len({info.project_id for info in outcomes}) == 1
        assert len({info.decision_id for info in outcomes}) == 1
        receipt = source.operation_receipt(
            "parallel-demo", intent_hash=DemoService._intent()
        )
        assert receipt is not None
        assert len([row for row in receipt.changes if row.key.collection == "project"]) == 1

        replay = DemoService(
            source_factory, Clock(), staging_factory=DemoStagingSource,
            destination_factory=FileDemoDestinationFactory(),
        ).create_in(source, root, operation_id="parallel-demo")
        assert replay.replayed is True
        assert replay.project_id == outcomes[0].project_id
        assert (replay.case_count, replay.binding_count, replay.label_count) == (12, 11, 9)
        assert not source.files.closed
