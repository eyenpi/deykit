"""Read-only inspection of frozen per-case results and their explicit evidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, cast

from deykit.application.annotations import annotation_hash
from deykit.application.dataset_support import fail, identifier, page
from deykit.application.evaluations import EvaluationMode, FrozenEvaluation, _frozen, _typed, _view
from deykit.contracts.json_value import JsonDocument, JsonError, JsonValue, parse_json
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
from deykit.domain.definitions import definition_hash
from deykit.metrics import assess_results
from deykit.metrics.summary import CaseAssessment, EvaluationSummary, MetricsInvalid

ProbabilityUnavailableReason = Literal[
    "probabilities_not_provided",
    "probability_question_unavailable",
    "invalid_probability_source",
    "probability_options_unavailable",
]


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
    assessment_counts: AssessmentCounts
    context: ResultContext
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
            "assessment_counts": self.assessment_counts.source(),
            "context": self.context.source(),
            "items": [item.source() for item in self.items],
            "next_cursor": self.next_cursor,
        }


@dataclass(frozen=True)
class CaseDetail:
    run_id: str
    result_snapshot_id: str
    label_snapshot_id: str
    evaluation_id: str | None
    context: ResultContext
    row: ResultRow
    answer: dict[str, object] | None
    annotations: tuple[ResultAnnotation, ...]
    attempts: tuple[dict[str, object], ...]
    input_source: str | None
    case_input_hash: str
    probabilities: tuple[ProbabilityRow, ...]
    probabilities_unavailable_reason: ProbabilityUnavailableReason | None

    def source(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "result_snapshot_id": self.result_snapshot_id,
            "label_snapshot_id": self.label_snapshot_id,
            "evaluation_id": self.evaluation_id,
            "context": self.context.source(),
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
            "case_input_hash": self.case_input_hash,
            "probabilities": [item.source() for item in self.probabilities],
            "probabilities_unavailable_reason": self.probabilities_unavailable_reason,
        }


@dataclass(frozen=True)
class AssessmentCounts:
    all: int
    inspect: int
    incorrect: int
    unlabelled: int

    def source(self) -> dict[str, int]:
        return {
            "all": self.all,
            "inspect": self.inspect,
            "incorrect": self.incorrect,
            "unlabelled": self.unlabelled,
        }


@dataclass(frozen=True)
class ResultContext:
    run_id: str
    result_snapshot_id: str
    label_snapshot_id: str
    evaluation_id: str | None
    decision_id: str
    dataset_id: str
    decision_revision_id: str
    decision_definition_hash: str
    dataset_snapshot_id: str
    dataset_content_hash: str
    label_content_hash: str
    result_content_hash: str
    evaluation_mode: EvaluationMode
    through_event_sequence: int

    def source(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "result_snapshot_id": self.result_snapshot_id,
            "label_snapshot_id": self.label_snapshot_id,
            "evaluation_id": self.evaluation_id,
            "decision_id": self.decision_id,
            "dataset_id": self.dataset_id,
            "decision_revision_id": self.decision_revision_id,
            "decision_definition_hash": self.decision_definition_hash,
            "dataset_snapshot_id": self.dataset_snapshot_id,
            "dataset_content_hash": self.dataset_content_hash,
            "label_content_hash": self.label_content_hash,
            "result_content_hash": self.result_content_hash,
            "evaluation_mode": self.evaluation_mode,
            "through_event_sequence": self.through_event_sequence,
        }


@dataclass(frozen=True)
class ProbabilityRow:
    option_id: str
    option_name: str
    probability: str

    def source(self) -> dict[str, str]:
        return {
            "option_id": self.option_id,
            "option_name": self.option_name,
            "probability": self.probability,
        }


@dataclass(frozen=True)
class _ResultCapture:
    rows: tuple[ResultRow, ...]
    result_snapshot_id: str
    label_snapshot_id: str
    summary: EvaluationSummary
    records: tuple[StoredRecord, ...]
    frozen: FrozenEvaluation
    evaluation_id: str | None
    mode: EvaluationMode
    through_event_sequence: int


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

    def _capture(self, run_id: str, evaluation_id: str | None) -> _ResultCapture:
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
        return _ResultCapture(
            rows,
            result_id,
            frozen.labels.id,
            summary,
            records,
            frozen,
            evaluation_id,
            mode,
            frozen.results.through_event_sequence,
        )

    @staticmethod
    def _result_context(capture: _ResultCapture, run_id: str) -> ResultContext:
        frozen = capture.frozen
        return ResultContext(
            run_id=run_id,
            result_snapshot_id=capture.result_snapshot_id,
            label_snapshot_id=capture.label_snapshot_id,
            evaluation_id=capture.evaluation_id,
            decision_id=cast(str, frozen.manifest.decision_id),
            dataset_id=cast(str, frozen.manifest.dataset_id),
            decision_revision_id=frozen.revision.id,
            decision_definition_hash=definition_hash(frozen.revision.definition),
            dataset_snapshot_id=frozen.dataset.id,
            dataset_content_hash=frozen.dataset.content_hash,
            label_content_hash=frozen.labels.content_hash,
            result_content_hash=frozen.results.content_hash,
            evaluation_mode=capture.mode,
            through_event_sequence=capture.through_event_sequence,
        )

    @staticmethod
    def _assessment_counts(rows: tuple[ResultRow, ...]) -> AssessmentCounts:
        inspect_statuses = {"pending", "input_invalid", "response_error", "unknown"}
        return AssessmentCounts(
            all=len(rows),
            inspect=sum(
                row.assessment.set_correct is False or row.result.status in inspect_statuses
                for row in rows
            ),
            incorrect=sum(row.assessment.set_correct is False for row in rows),
            unlabelled=sum(
                row.result.status == "valid"
                and row.assessment.answer_option_id is not None
                and "unlabelled" in row.assessment.exclusion_reasons
                for row in rows
            ),
        )

    @staticmethod
    def _check_expected_context(
        context: ResultContext,
        expected_result_snapshot_id: str | None,
        expected_label_snapshot_id: str | None,
    ) -> None:
        if (expected_result_snapshot_id is None) != (expected_label_snapshot_id is None):
            fail("result_context_selector_pair_required")
        if expected_result_snapshot_id is not None:
            identifier(expected_result_snapshot_id)
            identifier(cast(str, expected_label_snapshot_id))
            if (
                expected_result_snapshot_id != context.result_snapshot_id
                or expected_label_snapshot_id != context.label_snapshot_id
            ):
                fail("result_context_changed", "conflict")

    @staticmethod
    def _probability_projection(
        capture: _ResultCapture, row: ResultRow
    ) -> tuple[tuple[ProbabilityRow, ...], ProbabilityUnavailableReason | None]:
        answer = row.result.answer
        if answer is None or answer.probabilities_source is None:
            return (), "probabilities_not_provided"
        question = next(
            (q for q in capture.frozen.revision.definition.questions if q.id == answer.question_id),
            None,
        )
        if question is None:
            return (), "probability_question_unavailable"
        try:
            value = parse_json(answer.probabilities_source)
        except JsonError:
            return (), "invalid_probability_source"
        if not isinstance(value, dict) or set(value) != {option.id for option in question.options}:
            return (), "probability_options_unavailable"
        probabilities: list[ProbabilityRow] = []
        for option in question.options:
            item = value[option.id]
            if not isinstance(item, Decimal) or item < 0 or item > 1:
                return (), "invalid_probability_source"
            probabilities.append(ProbabilityRow(option.id, option.name, str(item)))
        return tuple(probabilities), None

    def list(
        self,
        run_id: str,
        *,
        evaluation_id: str | None = None,
        status: str | None = None,
        split: str | None = None,
        tag: str | None = None,
        assessment_filter: str = "all",
        expected_result_snapshot_id: str | None = None,
        expected_label_snapshot_id: str | None = None,
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
        if assessment_filter not in ("all", "inspect", "incorrect", "unlabelled"):
            fail("invalid_assessment_filter")
        capture = self._capture(run_id, evaluation_id)
        context = self._result_context(capture, run_id)
        self._check_expected_context(
            context, expected_result_snapshot_id, expected_label_snapshot_id
        )
        base_rows = tuple(
            item
            for item in capture.rows
            if (status is None or item.result.status == status)
            and (split is None or item.case.split == split)
            and (tag is None or tag in item.case.tags)
        )
        counts = self._assessment_counts(base_rows)
        matching = {
            item.case.id: item
            for item in base_rows
            if assessment_filter == "all"
            or (assessment_filter == "incorrect" and item.assessment.set_correct is False)
            or (
                assessment_filter == "inspect"
                and (
                    item.assessment.set_correct is False
                    or item.result.status
                    in {"pending", "input_invalid", "response_error", "unknown"}
                )
            )
            or (
                assessment_filter == "unlabelled"
                and item.result.status == "valid"
                and item.assessment.answer_option_id is not None
                and "unlabelled" in item.assessment.exclusion_reasons
            )
        }
        chosen, next_cursor = page(tuple(matching), cursor, limit)
        return ResultPage(
            run_id,
            capture.result_snapshot_id,
            capture.label_snapshot_id,
            evaluation_id,
            len(capture.rows),
            dict(capture.summary.status_counts),
            capture.summary.source(),
            len(matching),
            counts,
            context,
            tuple(matching[key] for key in chosen),
            next_cursor,
        )

    def show(
        self,
        run_id: str,
        case_id: str,
        *,
        evaluation_id: str | None = None,
        expected_result_snapshot_id: str | None = None,
        expected_label_snapshot_id: str | None = None,
        include_attempts: bool = False,
        include_request: bool = False,
        include_response: bool = False,
        include_input: bool = False,
    ) -> CaseDetail:
        identifier(run_id), identifier(case_id)
        if evaluation_id is not None:
            identifier(evaluation_id)
        capture = self._capture(run_id, evaluation_id)
        context = self._result_context(capture, run_id)
        self._check_expected_context(
            context, expected_result_snapshot_id, expected_label_snapshot_id
        )
        row = next((item for item in capture.rows if item.case.id == case_id), None)
        if row is None:
            fail("run_case_missing", "not_found")
        annotations = tuple(
            sorted(
                (
                    note
                    for stored in capture.records
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
                        for item in capture.records
                        if item.key.collection == "run_events" and item.key.scope == (run_id,)
                    ),
                    key=lambda event: event.sequence,
                )
                if event.attempt_id is not None
                and event.sequence <= capture.through_event_sequence
            }
            for stored in capture.records:
                if stored.key.collection != "attempts" or stored.key.scope != (run_id,):
                    continue
                attempt = _typed(stored, AttemptRecord)
                if attempt.case_id != case_id or attempt.id not in attempt_states:
                    continue
                events = sorted(
                    (
                        _typed(item, AttemptEvent)
                        for item in capture.records
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
            capture.result_snapshot_id,
            capture.label_snapshot_id,
            evaluation_id,
            context,
            row,
            normalized,
            annotations,
            tuple(sorted(attempts, key=lambda item: cast(int, item["number"]))),
            _sanitized_source(row.case.input_source.encode("utf-8")) if include_input else None,
            JsonDocument(row.case.input_source).content_hash,
            *self._probability_projection(capture, row),
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
