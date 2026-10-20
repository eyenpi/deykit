"""Incremental read models after comparing the complete, freshly admitted record set."""

from collections import defaultdict
from dataclasses import replace
from threading import RLock
from typing import TypeVar

from deykit.application.dataset_support import fail
from deykit.contracts.base import Record
from deykit.contracts.ports import RecordViewDelta, ResourceKey, StoredRecord
from deykit.contracts.records import (
    AttemptEvent,
    AttemptRecord,
    ResultSnapshot,
    RunControl,
    RunEvent,
    RunSegment,
)
from deykit.runner.decoding import HistoryDecoder
from deykit.runner.history import RunHistory, history_from_records, validate_attempt

R = TypeVar("R", bound=Record)


class HistoryIndex:
    def __init__(self, decoder: HistoryDecoder) -> None:
        self.decoder = decoder
        self.records: dict[ResourceKey, StoredRecord] = {}
        self.history: RunHistory | None = None
        self.event_scopes: set[str] = set()
        self.weight = 0
        self.vector: tuple[StoredRecord, ...] | None = None
        self.mutex = RLock()

    def capture(
        self, records: tuple[StoredRecord, ...], run_id: str, *, view: RecordViewDelta | None = None
    ) -> RunHistory:
        with self.mutex:
            try:
                return self._capture(records, run_id, view)
            except BaseException:
                self.history = None
                self.records.clear()
                self.event_scopes.clear()
                self.weight = 0
                self.vector = None
                raise

    def _capture(
        self, records: tuple[StoredRecord, ...], run_id: str, view: RecordViewDelta | None
    ) -> RunHistory:
        proved = (
            view is not None
            and view.records is records
            and view.changes is not None
            and not view.deleted_keys
            and view.previous_records is self.vector
        )
        current = (
            self.records
            if proved and view is not None and not view.changes
            else dict(self.records)
            if proved
            else {record.key: record for record in records}
        )
        if proved and view is not None and view.changes is not None:
            current.update((record.key, record) for record in view.changes)
        previous = self.history
        append_only = (
            previous is not None
            and previous.manifest.id == run_id
            and previous.manifest.execution_group_id is None
            and len(current) == len(records)
            and (proved or self.records.keys() <= current.keys())
        )
        added = []
        if append_only:
            inspected = (
                view.changes
                if proved and view is not None and view.changes is not None
                else records
            )
            for record in inspected:
                old = self.records.get(record.key)
                if old is None:
                    added.append(record)
                elif old is not record and old != record:
                    append_only = False
                    break
        if append_only and previous is not None:
            # Previously orphaned events must join the new attempt through full admission.
            append_only = not any(
                r.key.collection == "attempts" and r.key.resource_id in self.event_scopes
                for r in added
            ) and not any(
                r.key.collection == "prepared_cases" and r.key.scope == (run_id,) for r in added
            )
        if append_only and previous is not None:
            result = self._advance(previous, tuple(added)) if added else previous
            weight = self.weight + sum(len(r.body) for r in added)
            scopes = self.event_scopes | {
                r.key.scope[0] for r in added if r.key.collection == "attempt_events"
            }
        else:
            result = history_from_records(records, run_id, decoder=self.decoder)
            weight = sum(len(r.body) for r in records)
            scopes = {r.key.scope[0] for r in records if r.key.collection == "attempt_events"}
        if len(current) <= 131_072 and weight <= 128 * 1024 * 1024:
            self.records, self.history, self.weight, self.event_scopes = (
                current,
                result,
                weight,
                scopes,
            )
            self.vector = records
        else:
            self.records, self.history, self.weight, self.event_scopes = {}, None, 0, set()
            self.vector = None
        return result

    def _advance(self, prior: RunHistory, added: tuple[StoredRecord, ...]) -> RunHistory:
        run_id = prior.manifest.id
        decode = self.decoder.decode
        scoped: dict[str, list[StoredRecord]] = defaultdict(list)
        for record in added:
            if record.key.scope == (run_id,):
                scoped[record.key.collection].append(record)

        def sequenced(
            kind: type[R], collection: str, old: tuple[R, ...], attribute: str = "sequence"
        ) -> tuple[R, ...]:
            new = tuple(
                sorted(
                    (decode(kind, r) for r in scoped[collection]),
                    key=lambda v: getattr(v, attribute),
                )
            )
            if tuple(getattr(v, attribute) for v in new) != tuple(
                range(len(old) + 1, len(old) + len(new) + 1)
            ):
                fail("invalid_run_sequence", "incompatible_data")
            return old + new

        segments = sequenced(RunSegment, "segments", prior.segments)
        events = sequenced(RunEvent, "run_events", prior.events)
        controls = sequenced(RunControl, "run_controls", prior.controls)
        attempts = sequenced(AttemptRecord, "attempts", prior.attempts, "number")
        attempt_by_id = {attempt.id: attempt for attempt in attempts}
        event_groups = defaultdict(list)
        for record in added:
            if record.key.collection == "attempt_events" and record.key.scope[0] in attempt_by_id:
                value = decode(AttemptEvent, record)
                event_groups[value.attempt_id].append(value)
        changed_attempts = set(event_groups) | {a.id for a in attempts[len(prior.attempts) :]}
        by_id = {p.case_id: p for p in prior.prepared}
        segment_ids = {s.id for s in segments}
        old_events = defaultdict(list)
        for event in prior.attempt_events:
            if event.attempt_id in changed_attempts:
                old_events[event.attempt_id].append(event)
        for attempt_id in changed_attempts:
            ordered = tuple(
                sorted(
                    (*old_events[attempt_id], *event_groups[attempt_id]), key=lambda e: e.sequence
                )
            )
            validate_attempt(attempt_by_id[attempt_id], ordered, by_id, segment_ids)
        snapshots = list(prior.snapshots)
        for record in added:
            if record.key.collection == "result_snapshots":
                snapshot = decode(ResultSnapshot, record)
                if snapshot.run_id == run_id:
                    snapshots.append(snapshot)
        cap = prior.cap
        for control in controls[len(prior.controls) :]:
            if control.max_attempts is not None:
                if control.max_attempts <= cap:
                    fail("invalid_cap_extension", "incompatible_data")
                cap = control.max_attempts
        if len(attempts) > cap:
            fail("attempt_cap_exceeded", "incompatible_data")
        # Keep the same attempt-grouped ordering as full reconstruction.
        all_events: dict[str, list[AttemptEvent]] = {a.id: [] for a in attempts}
        for event in prior.attempt_events:
            all_events[event.attempt_id].append(event)
        for attempt_id, values in event_groups.items():
            all_events[attempt_id].extend(values)
            all_events[attempt_id].sort(key=lambda event: event.sequence)
        result = replace(
            prior,
            segments=segments,
            events=events,
            controls=controls,
            attempts=attempts,
            attempt_events=tuple(e for a in attempts for e in all_events[a.id]),
            snapshots=tuple(sorted(snapshots, key=lambda v: (v.through_event_sequence, v.id))),
        )
        case_attempts = dict(prior._case_attempts)
        for attempt in attempts[len(prior.attempts) :]:
            case_attempts[attempt.case_id] = (*case_attempts.get(attempt.case_id, ()), attempt)
        final_events = dict(prior._final_events)
        for attempt_id in event_groups:
            final_events[attempt_id] = all_events[attempt_id][-1]
        result.__dict__["_case_attempts"] = case_attempts
        result.__dict__["_final_events"] = final_events
        changed_cases = {attempt_by_id[a].case_id for a in changed_attempts}
        result.__dict__["_results"] = tuple(
            result.project_case(prepared) if prepared.case_id in changed_cases else old
            for prepared, old in zip(prior.prepared, prior.results(), strict=True)
        )
        return result
