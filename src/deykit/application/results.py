"""Read-only inspection of frozen per-case results and their explicit evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from deykit.application.annotations import annotation_hash
from deykit.application.dataset_support import fail, identifier, page
from deykit.application.evaluations import EvaluationMode, _frozen, _typed, _view
from deykit.contracts.json_value import JsonValue
from deykit.contracts.ports import ResourceKey, SnapshotSource, StoredRecord
from deykit.contracts.records import (
    AttemptEvent,
    AttemptRecord,
    CaseRecord,
    CaseResult,
    ResultAnnotation,
    ResultSnapshot,
    RunEvent,
    RunManifest,
)
from deykit.contracts.redaction import Sanitizer, safe_choice_response
from deykit.metrics import assess_results
from deykit.metrics.summary import CaseAssessment, EvaluationSummary, MetricsInvalid


@dataclass(frozen=True)
class ResultRow:
    case: CaseRecord
    result: CaseResult
    assessment: CaseAssessment
    annotation_count: int

    def source(self) -> dict[str, object]:
        return {
            "case_id": self.case.id,
            "split": self.case.split,
            "tags": list(self.case.tags),
            "status": self.result.status,
            "answer_option_id": self.assessment.answer_option_id,
            "expected_option_ids": list(self.assessment.expected_option_ids),
            "set_correct": self.assessment.set_correct,
            "exclusion_reasons": list(self.assessment.exclusion_reasons),
            "annotation_count": self.annotation_count,
        }


@dataclass(frozen=True)
class ResultPage:
    run_id: str
    result_snapshot_id: str
    label_snapshot_id: str
    evaluation_id: str | None
    selected_count: int
    status_counts: dict[str, int]
    summary: dict[str, JsonValue]
    filtered_count: int
    items: tuple[ResultRow, ...]
    next_cursor: str | None

    def source(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "result_snapshot_id": self.result_snapshot_id,
            "label_snapshot_id": self.label_snapshot_id,
            "evaluation_id": self.evaluation_id,
            "selected_count": self.selected_count,
            "status_counts": self.status_counts,
            "summary": self.summary,
            "filtered_count": self.filtered_count,
            "items": [item.source() for item in self.items],
            "next_cursor": self.next_cursor,
        }


@dataclass(frozen=True)
class CaseDetail:
    run_id: str
    result_snapshot_id: str
    label_snapshot_id: str
    evaluation_id: str | None
    row: ResultRow
    answer: dict[str, object] | None
    annotations: tuple[ResultAnnotation, ...]
    attempts: tuple[dict[str, object], ...]
    input_source: str | None

    def source(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "result_snapshot_id": self.result_snapshot_id,
            "label_snapshot_id": self.label_snapshot_id,
            "evaluation_id": self.evaluation_id,
            **self.row.source(),
            "question_id": self.row.result.answer.question_id
            if self.row.result.answer is not None
            else None,
            "answer": self.answer,
            "legacy_question_ids": list(self.row.assessment.legacy_question_ids),
            "legacy_expected_option_ids": [
                list(ids) for ids in self.row.assessment.legacy_expected_option_ids
            ],
            "legacy_exclusion_reasons": [
                list(reasons) for reasons in self.row.assessment.legacy_exclusion_reasons
            ],
            "label_provenance": self.row.assessment.label_provenance,
            "annotations": [
                {"id": item.id, "note": Sanitizer().text(item.note), "created_at": item.created_at}
                for item in self.annotations
            ],
            "attempts": list(self.attempts),
            "input_source": self.input_source,
        }


class ResultInspection:
    def __init__(self, source: SnapshotSource) -> None:
        self.source = source

    def _context(
        self, run_id: str, evaluation_id: str | None
    ) -> tuple[tuple[StoredRecord, ...], str, str | None, EvaluationMode]:
        with self.source.consistent_read():
            records = self.source.capture_snapshot()
        index = {item.key: item for item in records}
        stored_run = index.get(ResourceKey("runs", run_id))
        if stored_run is None:
            fail("run_missing", "not_found")
        _typed(stored_run, RunManifest)
        if evaluation_id is not None:
            evaluation_stored = index.get(ResourceKey("evaluations", evaluation_id))
            if evaluation_stored is None:
                fail("evaluation_missing", "not_found")
            evaluation = _view(evaluation_stored).record
            if evaluation.run_id != run_id:
                fail("evaluation_run_mismatch", "incompatible_data")
            return (
                records,
                evaluation.result_snapshot_id,
                evaluation.label_snapshot_id,
                evaluation.mode,
            )
        snapshots = [
            _typed(item, ResultSnapshot)
            for item in records
            if item.key.collection == "result_snapshots"
        ]
        matching = [item for item in snapshots if item.run_id == run_id]
        if not matching:
            fail("result_snapshot_missing", "not_found")
        latest = max(
            matching, key=lambda item: (item.through_event_sequence, item.created_at, item.id)
        )
        return records, latest.id, None, "original"

    def _rows(
        self, run_id: str, evaluation_id: str | None
    ) -> tuple[tuple[ResultRow, ...], str, str, EvaluationSummary, tuple[StoredRecord, ...], int]:
        records, result_id, label_id, mode = self._context(run_id, evaluation_id)
        frozen = _frozen(records, run_id, result_id, label_id, mode)
        try:
            summary = assess_results(
                frozen.revision.definition,
                frozen.dataset,
                frozen.labels,
                frozen.results,
                frozen.manifest.case_ids,
            )
        except MetricsInvalid as error:
            fail(str(error), "incompatible_data")
        annotation_counts: dict[str, int] = {}
        for stored in records:
            if stored.key.collection == "annotations":
                note = _typed(stored, ResultAnnotation)
                if note.content_hash != annotation_hash(note.run_id, note.case_id, note.note):
                    fail("annotation_hash_mismatch", "incompatible_data")
                if note.run_id == run_id:
                    annotation_counts[note.case_id] = annotation_counts.get(note.case_id, 0) + 1
        rows = tuple(
            ResultRow(case, result, assessment, annotation_counts.get(case.id, 0))
            for case, result, assessment in zip(
                frozen.dataset.cases, frozen.results.results, summary.cases, strict=True
            )
        )
        return (
            rows,
            result_id,
            frozen.labels.id,
            summary,
            records,
            frozen.results.through_event_sequence,
        )

    def list(
        self,
        run_id: str,
        *,
        evaluation_id: str | None = None,
        status: str | None = None,
        split: str | None = None,
        tag: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> ResultPage:
        identifier(run_id)
        if evaluation_id is not None:
            identifier(evaluation_id)
        if status is not None and status not in (
            "pending",
            "input_invalid",
            "response_error",
            "unknown",
            "valid",
        ):
            fail("invalid_result_status")
        if split is not None and split not in ("development", "calibration", "test"):
            fail("invalid_split")
        if tag is not None and (type(tag) is not str or not tag):
            fail("invalid_tag")
        rows, result_id, label_id, summary, _, _ = self._rows(run_id, evaluation_id)
        matching = {
            item.case.id: item
            for item in rows
            if (status is None or item.result.status == status)
            and (split is None or item.case.split == split)
            and (tag is None or tag in item.case.tags)
        }
        chosen, next_cursor = page(tuple(matching), cursor, limit)
        return ResultPage(
            run_id,
            result_id,
            label_id,
            evaluation_id,
            len(rows),
            dict(summary.status_counts),
            summary.source(),
            len(matching),
            tuple(matching[key] for key in chosen),
            next_cursor,
        )

    def show(
        self,
        run_id: str,
        case_id: str,
        *,
        evaluation_id: str | None = None,
        include_attempts: bool = False,
        include_request: bool = False,
        include_response: bool = False,
        include_input: bool = False,
    ) -> CaseDetail:
        identifier(run_id), identifier(case_id)
        if evaluation_id is not None:
            identifier(evaluation_id)
        rows, result_id, label_id, _, records, boundary = self._rows(run_id, evaluation_id)
        row = next((item for item in rows if item.case.id == case_id), None)
        if row is None:
            fail("run_case_missing", "not_found")
        annotations = tuple(
            sorted(
                (
                    note
                    for stored in records
                    if stored.key.collection == "annotations"
                    if (note := _typed(stored, ResultAnnotation)).run_id == run_id
                    and note.case_id == case_id
                ),
                key=lambda note: (note.created_at, note.id),
            )
        )
        attempts: list[dict[str, object]] = []
        if include_attempts or include_request or include_response:
            attempt_states = {
                event.attempt_id: event.state
                for event in sorted(
                    (
                        _typed(item, RunEvent)
                        for item in records
                        if item.key.collection == "run_events" and item.key.scope == (run_id,)
                    ),
                    key=lambda event: event.sequence,
                )
                if event.attempt_id is not None and event.sequence <= boundary
            }
            for stored in records:
                if stored.key.collection != "attempts" or stored.key.scope != (run_id,):
                    continue
                attempt = _typed(stored, AttemptRecord)
                if attempt.case_id != case_id or attempt.id not in attempt_states:
                    continue
                events = sorted(
                    (
                        _typed(item, AttemptEvent)
                        for item in records
                        if item.key.collection == "attempt_events"
                        and item.key.scope == (attempt.id,)
                    ),
                    key=lambda event: event.sequence,
                )
                state = attempt_states[attempt.id]
                outcome = events[-1].outcome if events and state == "attempt_settled" else None
                detail: dict[str, object] = {
                    "attempt_id": attempt.id,
                    "number": attempt.number,
                    "kind": attempt.kind,
                    "state": state.removeprefix("attempt_"),
                    "request_body_hash": attempt.request.body_hash,
                    "error_code": outcome.error.code if outcome and outcome.error else None,
                    "error_reason": outcome.error.reason if outcome and outcome.error else None,
                }
                if include_request:
                    detail["request_body_source"] = _sanitized_source(attempt.request.body)
                if include_response:
                    detail["response_source"] = (
                        _sanitized_source(
                            outcome.raw_response_source.encode("utf-8"), response=True
                        )
                        if outcome and outcome.raw_response_source is not None
                        else None
                    )
                attempts.append(detail)
        answer = row.result.answer
        normalized: dict[str, object] | None = (
            {
                "option_id": answer.option_id,
                "question_id": answer.question_id,
                "probabilities_source": answer.probabilities_source,
                "native_confidence_source": answer.native_confidence_source,
                "native_confidence_semantics": answer.native_confidence_semantics,
                "reported_model": answer.reported_model,
            }
            if answer is not None
            else None
        )
        return CaseDetail(
            run_id,
            result_id,
            label_id,
            evaluation_id,
            row,
            normalized,
            annotations,
            tuple(sorted(attempts, key=lambda item: cast(int, item["number"]))),
            _sanitized_source(row.case.input_source.encode("utf-8")) if include_input else None,
        )


def _sanitized_source(body: bytes, *, response: bool = False) -> str:
    # Raw bodies are explicit opt-ins. The provider adapter has already removed
    # credential values before persistence; inspection redacts common headers too.
    from deykit.contracts.json_value import JsonError, dump_json, parse_json

    try:
        value = parse_json(body.decode("utf-8"))
        safe = safe_choice_response(value, Sanitizer()) if response else Sanitizer().value(value)
        return dump_json(safe)
    except (JsonError, UnicodeError):
        fail("invalid_raw_evidence", "incompatible_data")
