"""Project validated attempt evidence at an immutable result snapshot boundary."""

from collections import defaultdict
from dataclasses import replace
from typing import TYPE_CHECKING

from deykit.application.dataset_support import fail
from deykit.contracts.ports import StoredRecord
from deykit.contracts.records import AttemptEvent, AttemptRecord, ResultSnapshot
from deykit.runner.history import RunHistory, history_from_records

if TYPE_CHECKING:
    from deykit.runner.decoding import HistoryDecoder


def snapshot_attempts(
    records: tuple[StoredRecord, ...],
    snapshot: ResultSnapshot,
    *,
    decoder: "HistoryDecoder | None" = None,
    history: RunHistory | None = None,
) -> tuple[tuple[AttemptRecord, AttemptEvent], ...]:
    """Verify results against saved outcomes; include unsettled dispatched usage.

    Global run markers and attempt events are written atomically. A later outcome
    is therefore visible only if its corresponding marker precedes this boundary.
    No current result or later attempt can replace the snapshot's evidence.
    """
    _, dispatched = snapshot_history(records, snapshot, decoder=decoder, history=history)
    return dispatched


def snapshot_history(
    records: tuple[StoredRecord, ...],
    snapshot: ResultSnapshot,
    *,
    decoder: "HistoryDecoder | None" = None,
    history: RunHistory | None = None,
) -> tuple[RunHistory, tuple[tuple[AttemptRecord, AttemptEvent], ...]]:
    """Reconstruct the visible run evidence at a validated result boundary."""
    if history is None:
        history = history_from_records(records, snapshot.run_id, decoder=decoder)
    elif history.manifest.id != snapshot.run_id:
        fail("run_evidence_identity_mismatch", "incompatible_data")
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
    events_by_attempt: dict[str, list[AttemptEvent]] = defaultdict(list)
    for attempt_event in history.attempt_events:
        events_by_attempt[attempt_event.attempt_id].append(attempt_event)
    for attempt in history.attempts:
        events = tuple(events_by_attempt.get(attempt.id, ()))
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
    # Pre-fix snapshots retain their exact deadline-error projection. Admit only
    # that fully reconstructed legacy form; current scheduling uses pending cases.
    if (
        historical.results() != snapshot.results
        and historical.results(legacy_deadline_errors=True) != snapshot.results
    ):
        fail("result_attempt_evidence_mismatch", "incompatible_data")
    visible_segment_ids = {event.segment_id for event in historical.events}
    snapshots = tuple(item for item in history.snapshots if item.through_event_sequence <= boundary)
    historical = replace(
        historical,
        segments=tuple(item for item in history.segments if item.id in visible_segment_ids),
        controls=(),
        snapshots=tuple(item for item in snapshots if item.id != snapshot.id) + (snapshot,),
        group=None,
    )
    return historical, tuple(dispatched)
