"""Read models and pure scheduling decisions from immutable lifecycle evidence."""

from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from typing import Literal, TypeVar

from deykit.application.dataset_support import decoded, fail
from deykit.contracts.base import Record
from deykit.contracts.codec import dump_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import bytes_hash
from deykit.contracts.ports import Collection, ResourceKey, SnapshotSource, StoredRecord
from deykit.contracts.records import (
    AttemptEvent,
    AttemptRecord,
    CaseResult,
    PreparedCase,
    ResultSnapshot,
    RunControl,
    RunEvent,
    RunManifest,
    RunSegment,
)
from deykit.runner.decoding import HistoryDecoder
from deykit.runner.group_evidence import GroupBudget, group_budget

R = TypeVar("R", bound=Record)
AttemptKind = Literal["initial", "rate_retry", "unknown_retry"]


@dataclass(frozen=True)
class WorkItem:
    prepared: PreparedCase
    kind: AttemptKind
    prior_attempt_id: str | None = None
    delay_seconds: float = 0


@dataclass(frozen=True)
class RunHistory:
    manifest: RunManifest
    prepared: tuple[PreparedCase, ...]
    segments: tuple[RunSegment, ...]
    events: tuple[RunEvent, ...]
    attempts: tuple[AttemptRecord, ...]
    attempt_events: tuple[AttemptEvent, ...]
    controls: tuple[RunControl, ...]
    snapshots: tuple[ResultSnapshot, ...]
    group: GroupBudget | None = None

    @property
    def remaining(self) -> int:
        own = max(0, self.cap - self.used)
        return min(own, self.group.remaining) if self.group else own

    @property
    def cap(self) -> int:
        return (
            max(
                (item.max_attempts or 0 for item in self.controls),
                default=self.manifest.settings.max_attempts,
            )
            if any(item.max_attempts for item in self.controls)
            else self.manifest.settings.max_attempts
        )

    @property
    def used(self) -> int:
        return len(self.attempts)

    @property
    def boundary(self) -> int:
        return self.events[-1].sequence if self.events else 0

    @property
    def state(self) -> str:
        lifecycle = [
            event
            for event in self.events
            if not event.state.startswith("attempt_")
            and event.state not in {"cap_extended", "segment_ready"}
        ]
        return lifecycle[-1].state if lifecycle else "preparing"

    @cached_property
    def _final_events(self) -> dict[str, AttemptEvent]:
        return {event.attempt_id: event for event in self.attempt_events}

    @cached_property
    def _case_attempts(self) -> dict[str, tuple[AttemptRecord, ...]]:
        grouped: dict[str, list[AttemptRecord]] = defaultdict(list)
        for attempt in self.attempts:
            grouped[attempt.case_id].append(attempt)
        return {key: tuple(value) for key, value in grouped.items()}

    def final_event(self, attempt_id: str) -> AttemptEvent | None:
        return self._final_events.get(attempt_id)

    def case_attempts(self, case_id: str) -> tuple[AttemptRecord, ...]:
        return self._case_attempts.get(case_id, ())

    @cached_property
    def _results(self) -> tuple[CaseResult, ...]:
        return self._project_results(legacy_deadline_errors=False)

    def results(self, *, legacy_deadline_errors: bool = False) -> tuple[CaseResult, ...]:
        """Project current outcomes, or the legacy form for saved-snapshot admission."""
        if legacy_deadline_errors:
            return self._project_results(legacy_deadline_errors=True)
        return self._results

    def _project_results(self, *, legacy_deadline_errors: bool) -> tuple[CaseResult, ...]:
        return tuple(
            self.project_case(prepared, legacy_deadline_errors=legacy_deadline_errors)
            for prepared in self.prepared
        )

    def project_case(
        self, prepared: PreparedCase, *, legacy_deadline_errors: bool = False
    ) -> CaseResult:
        if prepared.error is not None:
            return CaseResult(
                case_id=prepared.case_id,
                input_hash=prepared.input_hash,
                status="input_invalid",
                error=prepared.error,
            )
        result = CaseResult(
            case_id=prepared.case_id, input_hash=prepared.input_hash, status="pending"
        )
        for attempt in self.case_attempts(prepared.case_id):
            event = self.final_event(attempt.id)
            outcome = event.outcome if event else None
            if outcome is not None and outcome.answer is not None:
                result = CaseResult(
                    case_id=prepared.case_id,
                    input_hash=prepared.input_hash,
                    status="valid",
                    attempt_id=attempt.id,
                    answer=outcome.answer,
                )
                break  # A valid saved answer can never be overwritten by another attempt.
            if (
                outcome is not None
                and outcome.state == "not_sent"
                and outcome.error
                and (
                    outcome.error.reason == "cancelled_before_dispatch"
                    or (outcome.error.reason == "segment_deadline" and not legacy_deadline_errors)
                )
            ):
                continue  # Keep the prior unknown/error; a proven non-call is not new evidence.
            elif outcome is None or outcome.state == "unknown":
                result = CaseResult(
                    case_id=prepared.case_id,
                    input_hash=prepared.input_hash,
                    status="unknown",
                    attempt_id=attempt.id,
                    error=outcome.error
                    if outcome
                    else ServiceError(code="run_incomplete", reason="unsettled_attempt"),
                )
            else:
                result = CaseResult(
                    case_id=prepared.case_id,
                    input_hash=prepared.input_hash,
                    status="response_error",
                    attempt_id=attempt.id,
                    error=outcome.error,
                )
        return result

    def work(self, *, retry_unknown: bool = False) -> tuple[WorkItem, ...]:
        result_by_id = {result.case_id: result for result in self.results()}
        work: list[WorkItem] = []
        for prepared in self.prepared:
            result = result_by_id[prepared.case_id]
            if result.status == "pending":
                work.append(WorkItem(prepared, "initial"))
            elif result.status == "unknown" and retry_unknown:
                work.append(WorkItem(prepared, "unknown_retry", result.attempt_id))
            elif result.status == "response_error" and result.attempt_id:
                final = self.final_event(result.attempt_id)
                outcome = final.outcome if final else None
                retries = sum(
                    item.kind == "rate_retry" for item in self.case_attempts(prepared.case_id)
                )
                if (
                    outcome is not None
                    and outcome.state == "known"
                    and outcome.retryable
                    and outcome.error
                    and outcome.error.code == "provider_rejected"
                    and outcome.error.reason in {"rate_limit", "overloaded"}
                    and retries < self.manifest.settings.max_retries_per_case
                ):
                    work.append(
                        WorkItem(
                            prepared,
                            "rate_retry",
                            result.attempt_id,
                            outcome.retry_after_seconds or 0,
                        )
                    )
        return tuple(work)


def read_history(
    source: SnapshotSource, run_id: str, *, decoder: HistoryDecoder | None = None
) -> RunHistory:
    return history_from_records(source.capture_snapshot(), run_id, decoder=decoder)


def history_from_records(
    records: tuple[StoredRecord, ...],
    run_id: str,
    *,
    verify_group: bool = True,
    decoder: HistoryDecoder | None = None,
) -> RunHistory:
    """Validate a run from one captured source epoch without performing source reads.

    Evaluation and inspection consumers can reuse runner validation while retaining
    their own consistent-read boundary and immutable historical snapshot selection.
    """
    decode = decoder.decode if decoder is not None else decoded
    indexed: dict[tuple[Collection, tuple[str, ...]], list[StoredRecord]] = defaultdict(list)
    for record in records:
        indexed[(record.key.collection, record.key.scope)].append(record)

    def selected(kind: type[R], collection: Collection, scope: tuple[str, ...]) -> tuple[R, ...]:
        return tuple(decode(kind, item) for item in indexed.get((collection, scope), ()))

    manifest_key = ResourceKey("runs", run_id)
    manifest_source = next((record for record in records if record.key == manifest_key), None)
    if manifest_source is None:
        fail("run_missing", "not_found")
    manifest = decode(RunManifest, manifest_source)
    if (
        manifest.provider is None
        or manifest.decision_id is None
        or manifest.dataset_id is None
        or manifest.baseline_dataset_snapshot_id is None
        or manifest.baseline_label_snapshot_id is None
    ):
        fail("legacy_run_not_executable", "incompatible_data")
    profile = manifest.provider
    if (
        manifest.provider_config_hash != bytes_hash(dump_record(profile))
        or manifest.provider_profile_id != profile.id
        or manifest.adapter != profile.adapter
        or manifest.requested_model != profile.requested_model
        or len(manifest.case_ids) != len(set(manifest.case_ids))
    ):
        fail("invalid_frozen_run_context", "incompatible_data")
    prepared = selected(PreparedCase, "prepared_cases", (run_id,))
    if any(
        item.request is not None
        and (
            item.request.adapter != profile.adapter
            or item.request.destination != profile.destination
            or item.request.requested_model != profile.requested_model
        )
        for item in prepared
    ):
        fail("invalid_frozen_run_context", "incompatible_data")
    by_id = {item.case_id: item for item in prepared}
    if set(by_id) != set(manifest.case_ids):
        fail("incomplete_prepared_plan", "incompatible_data")
    segments = tuple(
        sorted(selected(RunSegment, "segments", (run_id,)), key=lambda item: item.sequence)
    )
    events = tuple(
        sorted(selected(RunEvent, "run_events", (run_id,)), key=lambda item: item.sequence)
    )
    attempts = tuple(
        sorted(
            selected(AttemptRecord, "attempts", (run_id,)),
            key=lambda item: item.number,
        )
    )
    controls = tuple(
        sorted(
            selected(RunControl, "run_controls", (run_id,)),
            key=lambda item: item.sequence,
        )
    )
    for values in (
        tuple(item.sequence for item in segments),
        tuple(item.sequence for item in events),
        tuple(item.number for item in attempts),
        tuple(item.sequence for item in controls),
    ):
        if values != tuple(range(1, len(values) + 1)):
            fail("invalid_run_sequence", "incompatible_data")
    attempt_events: list[AttemptEvent] = []
    segment_ids = {segment.id for segment in segments}
    for attempt in attempts:
        ordered = tuple(
            sorted(
                selected(AttemptEvent, "attempt_events", (attempt.id,)),
                key=lambda item: item.sequence,
            )
        )
        validate_attempt(attempt, ordered, by_id, segment_ids)
        attempt_events.extend(ordered)
    snapshots = tuple(
        item for item in selected(ResultSnapshot, "result_snapshots", ()) if item.run_id == run_id
    )
    history = RunHistory(
        manifest,
        tuple(by_id[key] for key in manifest.case_ids),
        segments,
        events,
        attempts,
        tuple(attempt_events),
        controls,
        tuple(sorted(snapshots, key=lambda item: (item.through_event_sequence, item.id))),
        group_budget(records, manifest.execution_group_id)
        if verify_group and manifest.execution_group_id
        else None,
    )
    previous = manifest.settings.max_attempts
    for control in controls:
        if control.max_attempts is not None:
            if control.max_attempts <= previous:
                fail("invalid_cap_extension", "incompatible_data")
            previous = control.max_attempts
    if history.used > history.cap:
        fail("attempt_cap_exceeded", "incompatible_data")
    return history


def validate_attempt(
    attempt: AttemptRecord,
    ordered: tuple[AttemptEvent, ...],
    by_id: dict[str, PreparedCase],
    segment_ids: set[str],
) -> None:
    if (
        attempt.case_id not in by_id
        or attempt.segment_id not in segment_ids
        or attempt.request != by_id[attempt.case_id].request
    ):
        fail("attempt_plan_mismatch", "incompatible_data")
    if tuple(event.sequence for event in ordered) != tuple(range(1, len(ordered) + 1)):
        fail("invalid_attempt_sequence", "incompatible_data")
    if not ordered or ordered[0].state != "reserved":
        fail("missing_attempt_reservation", "incompatible_data")
    states = tuple(event.state for event in ordered)
    if states not in {
        ("reserved",),
        ("reserved", "dispatched"),
        ("reserved", "unknown"),
        ("reserved", "not_sent"),
        ("reserved", "dispatched", "known"),
        ("reserved", "dispatched", "unknown"),
        ("reserved", "dispatched", "not_sent"),
    } or any(
        (event.state in {"reserved", "dispatched"} and event.outcome is not None)
        or (
            event.state not in {"reserved", "dispatched"}
            and (event.outcome is None or event.outcome.state != event.state)
        )
        for event in ordered
    ):
        fail("invalid_attempt_transition", "incompatible_data")
