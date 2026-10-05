"""Project validated attempt evidence at an immutable result snapshot boundary."""

from dataclasses import replace

from deykit.application.dataset_support import fail
from deykit.contracts.ports import StoredRecord
from deykit.contracts.records import AttemptEvent, AttemptRecord, ResultSnapshot
from deykit.runner.history import history_from_records


def snapshot_attempts(
    records: tuple[StoredRecord, ...], snapshot: ResultSnapshot
) -> tuple[tuple[AttemptRecord, AttemptEvent], ...]:
    """Verify results against saved outcomes; include unsettled dispatched usage.

    Global run markers and attempt events are written atomically. A later outcome
    is therefore visible only if its corresponding marker precedes this boundary.
    No current result or later attempt can replace the snapshot's evidence.
    """
    history = history_from_records(records, snapshot.run_id)
    if any(item.run_id != snapshot.run_id for item in history.prepared) or any(
        item.run_id != snapshot.run_id for item in history.segments
    ):
        fail("run_evidence_identity_mismatch", "incompatible_data")
    boundary = snapshot.through_event_sequence
    if boundary > history.boundary:
        fail("invalid_result_boundary", "incompatible_data")
    attempts = {attempt.id: attempt for attempt in history.attempts}
    markers: dict[str, list[tuple[str, int]]] = {key: [] for key in attempts}
    for event in history.events:
        if event.run_id != snapshot.run_id:
            fail("run_event_identity_mismatch", "incompatible_data")
        if not event.state.startswith("attempt_"):
            continue
        attempt = attempts.get(event.attempt_id or "")
        if attempt is None or event.segment_id != attempt.segment_id:
            fail("attempt_marker_mismatch", "incompatible_data")
        markers[attempt.id].append((event.state, event.sequence))
    visible_attempts: list[AttemptRecord] = []
    visible_events: list[AttemptEvent] = []
    dispatched: list[tuple[AttemptRecord, AttemptEvent]] = []
    for attempt in history.attempts:
        events = tuple(item for item in history.attempt_events if item.attempt_id == attempt.id)
        expected = tuple(
            "attempt_reserved"
            if item.state == "reserved"
            else "attempt_dispatched"
            if item.state == "dispatched"
            else "attempt_settled"
            for item in events
        )
        actual = markers[attempt.id]
        if attempt.run_id != snapshot.run_id or tuple(item[0] for item in actual) != expected:
            fail("attempt_marker_mismatch", "incompatible_data")
        visible = tuple(
            item for item, (_, sequence) in zip(events, actual, strict=True) if sequence <= boundary
        )
        if not visible:
            continue
        visible_attempts.append(attempt)
        visible_events.extend(visible)
        if any(item.state == "dispatched" for item in visible):
            dispatched.append((attempt, visible[-1]))
    historical = replace(
        history,
        events=tuple(item for item in history.events if item.sequence <= boundary),
        attempts=tuple(visible_attempts),
        attempt_events=tuple(visible_events),
    )
    if historical.results() != snapshot.results:
        fail("result_attempt_evidence_mismatch", "incompatible_data")
    return tuple(dispatched)
