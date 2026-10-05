"""Notes are append-only project resources, separate from model results."""

import asyncio
import itertools

import pytest

from deykit.application.annotations import AnnotationService
from deykit.application.errors import ServiceFailure
from deykit.contracts.ports import ResourceKey
from deykit.runner.planner import RunRequest


def test_run_case_note_replay_and_distinct_new_note(setup):
    source, runner, factory, clock = setup(1)
    run = asyncio.run(
        runner.start(
            RunRequest(
                decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
            ),
            operation_id="start",
        )
    )
    before = source.capture_snapshot()
    counter = itertools.count()
    service = AnnotationService(source, clock, lambda: f"note-{next(counter)}")
    first = service.add(run.run_id, "case-00", "Inspect this answer", operation_id="note-one")
    repeated = service.add(run.run_id, "case-00", "Inspect this answer", operation_id="note-one")
    assert repeated.annotation.id == first.annotation.id and repeated.replayed
    assert service.list(run.run_id).items == (service.read(first.annotation.id),)
    assert source.read(ResourceKey("annotations", first.annotation.id)) is not None
    assert len(source.capture_snapshot()) == len(before) + 1
    second = service.add(run.run_id, "case-00", "Confirmed", operation_id="note-two")
    assert second.annotation.id != first.annotation.id
    assert [item.annotation.note for item in service.list(run.run_id).items] == [
        "Inspect this answer",
        "Confirmed",
    ]
    assert len(factory.calls) == 1
    with pytest.raises(ServiceFailure) as changed:
        service.add(run.run_id, "case-00", "Different intent", operation_id="note-one")
    assert changed.value.error.reason == "operation_id_conflict"
    with pytest.raises(ServiceFailure) as missing:
        service.add(run.run_id, "missing", "No case", operation_id="bad-case")
    assert missing.value.error.reason == "run_case_missing"
    assert len(source.capture_snapshot()) == len(before) + 2
