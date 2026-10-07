"""Create and read immutable reports from one captured source boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, cast

from deykit.application.checks import FrozenCheckSnapshot
from deykit.application.comparisons import admit_comparison_from_records
from deykit.application.dataset_support import fail, identifier
from deykit.application.diagnostics import FrozenDiagnosticSnapshot
from deykit.application.errors import ServiceFailure
from deykit.application.evaluations import (
    EvaluationService,
    EvaluationView,
    admit_evaluation_record,
)
from deykit.comparisons.models import ComparisonOutcomes
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.execution_groups import CheckSnapshot, DiagnosticSnapshot
from deykit.contracts.identities import new_id
from deykit.contracts.json_value import (
    JsonError,
    JsonValue,
    bytes_hash,
    dump_json,
    semantic_hash,
)
from deykit.contracts.model_admission import admit_model
from deykit.contracts.ports import (
    Clock,
    Collection,
    ResourceKey,
    SnapshotSource,
    SourceChange,
    StoredRecord,
)
from deykit.contracts.records import ReportRecord, ResultSnapshot
from deykit.contracts.redaction import Sanitizer
from deykit.reports.admission import (
    ReportAdmissionError,
    admit_report,
    admit_report_metadata,
    report_hash,
)
from deykit.reports.group_projection import (
    project_check,
    project_diagnostic,
    project_group_raw,
    read_check,
    read_diagnostic,
)
from deykit.reports.models import (
    CheckReport,
    DiagnosticReport,
    ExportOutcome,
    FrozenTarget,
    RawMaterial,
    RenderedArtifact,
    ReportContent,
    ReportEvaluation,
    ReportFormat,
    ReportMetadata,
    ReportPage,
    ReportRequest,
    ReportView,
)
from deykit.reports.ports import ArtifactWriter
from deykit.reports.projection import (
    expected_group_limitations,
    expected_limitations,
    project_evaluation,
    safe_comparison_outcomes,
    sanitizer_would_change,
    validate_rendered_artifact_identities,
    validate_report_identity_context,
    validate_report_identity_value,
    validate_report_metadata_identities,
)
from deykit.reports.render import render_content


def _index(records: tuple[StoredRecord, ...]) -> dict[ResourceKey, StoredRecord]:
    return {item.key: item for item in records}


def _json_tree(value: object) -> JsonValue:
    if value is None or type(value) in (str, int, bool):
        return cast(JsonValue, value)
    if isinstance(value, (tuple, list)):
        return [_json_tree(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_tree(item) for key, item in value.items()}
    # Decimal is the exact JSON-number type returned by the project codec.
    from decimal import Decimal

    if isinstance(value, Decimal):
        return value
    fail("invalid_report_content", "incompatible_data")


def _stored(
    index: dict[ResourceKey, StoredRecord],
    collection: Collection,
    resource_id: str,
    scope: tuple[str, ...] = (),
) -> StoredRecord:
    value = index.get(ResourceKey(collection, resource_id, scope))
    if value is None:
        fail("report_target_missing", "not_found")
    return value


def _select_group_snapshot(
    records: tuple[StoredRecord, ...],
    kind: Literal["diagnostic", "check"],
    group_id: str,
    snapshot_id: str | None,
) -> FrozenDiagnosticSnapshot | FrozenCheckSnapshot:
    collection = "diagnostic_snapshots" if kind == "diagnostic" else "check_snapshots"
    reader = read_diagnostic if kind == "diagnostic" else read_check
    if snapshot_id is not None:
        frozen = reader(records, snapshot_id)
        if frozen.group.id != group_id or frozen.group.kind != (
            "choice_order" if kind == "diagnostic" else "regression_check"
        ):
            fail("report_selector_conflict", "incompatible_data")
        return frozen
    candidates: list[DiagnosticSnapshot | CheckSnapshot] = []
    for stored in records:
        if stored.key.collection != collection or stored.key.scope:
            continue
        try:
            if kind == "diagnostic":
                candidate: DiagnosticSnapshot | CheckSnapshot = load_record(
                    DiagnosticSnapshot, stored.body
                )
            else:
                candidate = load_record(CheckSnapshot, stored.body)
        except (JsonError, ValueError):
            continue
        if candidate.id == stored.key.resource_id and candidate.group_id == group_id:
            candidates.append(candidate)
    for snapshot_record in sorted(
        candidates, key=lambda item: (item.sequence, item.created_at, item.id), reverse=True
    ):
        try:
            return reader(records, snapshot_record.id)
        except ServiceFailure:
            continue
    missing = "diagnostic_snapshot_missing" if kind == "diagnostic" else "check_snapshot_missing"
    fail(missing, "not_found")


class ReportService:
    def __init__(
        self,
        source: SnapshotSource,
        clock: Clock,
        id_factory: Callable[[], str] = new_id,
        *,
        sanitizer: Sanitizer | None = None,
    ) -> None:
        self.source, self.clock, self.id_factory = source, clock, id_factory
        self.sanitizer = sanitizer or Sanitizer()

    def _request(self, request: ReportRequest) -> ReportRequest:
        try:
            return admit_model(ReportRequest, request, "invalid_report_request")
        except ValueError:
            fail("invalid_report_request")

    def create(self, request: ReportRequest, *, operation_id: str) -> ReportView:
        request = self._request(request)
        identifier(operation_id)
        intent = semantic_hash(
            {
                "command": "report.create",
                "profile": "deykit-report-v1",
                "target_id": request.target_id,
                "target_kind": request.target_kind,
                "evaluation_id": request.evaluation_id,
                "result_snapshot_id": request.result_snapshot_id,
                "group_snapshot_id": request.group_snapshot_id,
                "raw": {
                    "inputs": request.raw.inputs,
                    "requests": request.raw.requests,
                    "responses": request.raw.responses,
                },
            }
        )
        with self.source.consistent_read() as source:
            replay = source.operation_receipt(operation_id, intent_hash=intent)
            if replay is not None:
                if len(replay.changes) != 1 or replay.deleted_keys:
                    fail("invalid_report_receipt", "incompatible_data")
                records = cast(SnapshotSource, source).capture_snapshot()
                return self._admit_captured_report(replay.changes[0], records, replayed=True)
            records = cast(SnapshotSource, source).capture_snapshot()
            index = _index(records)
            target_kind = request.target_kind
            if target_kind is None:
                target_collections: tuple[
                    tuple[Literal["run", "evaluation", "comparison"], Collection], ...
                ] = (
                    ("run", "runs"),
                    ("evaluation", "evaluations"),
                    ("comparison", "comparisons"),
                )
                candidates = tuple(
                    kind
                    for kind, collection in target_collections
                    if ResourceKey(collection, request.target_id) in index
                )
                if not candidates:
                    fail("report_target_missing", "not_found")
                if len(candidates) > 1:
                    fail("ambiguous_report_target", "incompatible_data")
                target_kind = candidates[0]
            evaluations: list[ReportEvaluation] = []
            eval_views: list[EvaluationView] = []
            material: list[RawMaterial] = []
            comparison_source: ComparisonOutcomes | None = None
            comparison_id: str | None = None
            comparison_hash: str | None = None
            diagnostic_source: DiagnosticReport | None = None
            check_source: CheckReport | None = None
            diagnostic_snapshot_id: str | None = None
            check_snapshot_id: str | None = None
            group_snapshot: FrozenDiagnosticSnapshot | FrozenCheckSnapshot | None = None
            result_ids: tuple[str, ...] = ()
            label_ids: tuple[str, ...] = ()
            selected_target_id = request.target_id
            if target_kind in ("run", "evaluation"):
                if target_kind == "evaluation":
                    if (
                        request.evaluation_id is not None
                        or request.result_snapshot_id is not None
                        or request.group_snapshot_id is not None
                    ):
                        fail("invalid_report_selector")
                    evaluation_id = request.target_id
                    stored = _stored(index, "evaluations", evaluation_id)
                    eval_view = admit_evaluation_record(stored)
                    if eval_view.record.id != evaluation_id:
                        fail("report_context_mismatch", "incompatible_data")
                    eval_views.append(eval_view)
                else:
                    if request.group_snapshot_id is not None:
                        fail("invalid_report_selector")
                    if request.evaluation_id:
                        eval_view = admit_evaluation_record(
                            _stored(index, "evaluations", request.evaluation_id)
                        )
                        if eval_view.record.run_id != request.target_id or (
                            request.result_snapshot_id
                            and eval_view.record.result_snapshot_id != request.result_snapshot_id
                        ):
                            fail("report_selector_conflict", "incompatible_data")
                        eval_views.append(eval_view)
                    else:
                        snapshots = []
                        for item in records:
                            if item.key.collection == "result_snapshots":
                                try:
                                    snapshot = load_record(ResultSnapshot, item.body)
                                except JsonError:
                                    continue
                                if snapshot.run_id == request.target_id and (
                                    request.result_snapshot_id is None
                                    or snapshot.id == request.result_snapshot_id
                                ):
                                    snapshots.append(snapshot)
                        if not snapshots:
                            fail("result_snapshot_missing", "not_found")
                        selected_result = max(
                            snapshots,
                            key=lambda item: (
                                item.through_event_sequence,
                                item.created_at,
                                item.id,
                            ),
                        )
                        originals = []
                        for item in records:
                            if item.key.collection == "evaluations":
                                try:
                                    candidate = admit_evaluation_record(item)
                                except ServiceFailure as failure:
                                    if (
                                        failure.error.reason
                                        == "evaluation_record_identity_mismatch"
                                    ):
                                        raise
                                    continue
                                if (
                                    candidate.record.run_id == request.target_id
                                    and candidate.record.result_snapshot_id == selected_result.id
                                    and candidate.record.mode == "original"
                                ):
                                    originals.append(candidate)
                        if originals:
                            eval_views.append(
                                max(
                                    originals,
                                    key=lambda item: (item.record.created_at, item.record.id),
                                )
                            )
                        else:
                            operation = "report-eval-" + semantic_hash(
                                {
                                    "run_id": request.target_id,
                                    "result_snapshot_id": selected_result.id,
                                }
                            )
                            eval_views.append(
                                EvaluationService(
                                    cast(SnapshotSource, source), self.clock
                                ).evaluate_saved(
                                    request.target_id, selected_result.id, operation_id=operation
                                )
                            )
                            records = cast(SnapshotSource, source).capture_snapshot()
                            index = _index(records)
                selected_target_id = request.target_id
            elif target_kind == "comparison":
                if any(
                    (request.evaluation_id, request.result_snapshot_id, request.group_snapshot_id)
                ):
                    fail("invalid_report_selector")
                stored = _stored(index, "comparisons", request.target_id)
                comparison = admit_comparison_from_records(stored, records)
                if (
                    self.sanitizer.text(comparison.record.id) != comparison.record.id
                    or self.sanitizer.text(comparison.record.content_hash)
                    != comparison.record.content_hash
                ):
                    fail("report_sensitive_identity", "validation_error")
                comparison_id = comparison.record.id
                comparison_hash = comparison.record.content_hash
                for evaluation_id in (
                    comparison.record.left_evaluation_id,
                    comparison.record.right_evaluation_id,
                ):
                    eval_views.append(
                        admit_evaluation_record(_stored(index, "evaluations", evaluation_id))
                    )
                comparison_source = safe_comparison_outcomes(comparison.outcomes, self.sanitizer)
            elif target_kind in ("diagnostic", "check"):
                if request.evaluation_id is not None or request.result_snapshot_id is not None:
                    fail("invalid_report_selector")
                group_snapshot = _select_group_snapshot(
                    records, target_kind, request.target_id, request.group_snapshot_id
                )
                if target_kind == "diagnostic":
                    assert isinstance(group_snapshot, FrozenDiagnosticSnapshot)
                    diagnostic_source = project_diagnostic(records, group_snapshot, self.sanitizer)
                    diagnostic_snapshot_id = group_snapshot.snapshot.id
                else:
                    assert isinstance(group_snapshot, FrozenCheckSnapshot)
                    check_source = project_check(records, group_snapshot, self.sanitizer)
                    check_snapshot_id = group_snapshot.snapshot.id
                raw_tuple = project_group_raw(records, group_snapshot, self.sanitizer, request.raw)
                group_context = diagnostic_source or check_source
                if group_context is None:
                    fail("report_link_mismatch", "incompatible_data")
                result_ids = tuple(
                    dict.fromkeys(member.result_snapshot_id for member in group_context.members)
                )
                label_ids = tuple(
                    dict.fromkeys(member.label_snapshot_id for member in group_context.members)
                )
            else:
                fail("report_target_missing", "not_found")

            for view in eval_views:
                projected, raw_items = project_evaluation(
                    records, view, self.sanitizer, request.raw
                )
                evaluations.append(projected)
                material.extend(raw_items)
            eval_ids = tuple(dict.fromkeys(view.record.id for view in eval_views))
            if group_snapshot is None:
                result_ids = tuple(
                    dict.fromkeys(view.record.result_snapshot_id for view in eval_views)
                )
                label_ids = tuple(
                    dict.fromkeys(view.record.label_snapshot_id for view in eval_views)
                )
                raw_tuple = tuple(dict.fromkeys(material))
                limitation_tuple = expected_limitations(tuple(evaluations), raw_tuple)
            else:
                limitation_tuple = ()
            content = ReportContent(
                target=FrozenTarget(
                    kind=target_kind,
                    target_id=selected_target_id,
                    evaluation_ids=eval_ids,
                    result_snapshot_ids=result_ids,
                    label_snapshot_ids=label_ids,
                    comparison_id=comparison_id,
                    comparison_hash=comparison_hash,
                    group_snapshot_id=(diagnostic_snapshot_id or check_snapshot_id),
                ),
                raw=request.raw,
                evaluations=tuple(evaluations),
                comparison=comparison_source,
                diagnostic=diagnostic_source,
                check=check_source,
                raw_material=raw_tuple,
                limitations=limitation_tuple,
            )
            if group_snapshot is not None:
                group_report = diagnostic_source or check_source
                assert group_report is not None
                content_fields = content.model_dump(mode="python")
                content_fields["limitations"] = expected_group_limitations(group_report, content)
                content = ReportContent.model_validate(content_fields)
            content_source = dump_json(_json_tree(content.model_dump(mode="python")))
            if len(content_source.encode("utf-8")) > 1_048_576:
                fail("report_content_limit")
            provisional = ReportRecord(
                id=identifier(self.id_factory()),
                evaluation_ids=eval_ids,
                result_snapshot_ids=result_ids,
                label_snapshot_ids=label_ids,
                comparison_id=comparison_id,
                includes_raw_input=request.raw.inputs,
                includes_raw_request=request.raw.requests,
                includes_raw_response=request.raw.responses,
                content_source=content_source,
                content_hash="0" * 64,
                created_at=self.clock.utc_now(),
                diagnostic_snapshot_id=diagnostic_snapshot_id,
                check_snapshot_id=check_snapshot_id,
            )
            if self.sanitizer.text(provisional.id) != provisional.id:
                fail("report_sensitive_identity", "validation_error")
            record = provisional.model_copy(
                update={"content_hash": report_hash(provisional, content)}
            )
            validate_report_identity_context(
                record.id, record.content_hash, content, self.sanitizer
            )
            body = dump_record(record)
            validate_report_identity_value(bytes_hash(body), self.sanitizer)
            if cast(SnapshotSource, source).capture_snapshot() != records:
                fail("report_source_changed", "conflict")
            receipt = source.commit(
                operation_id,
                (SourceChange(ResourceKey("reports", record.id), body, None),),
                intent_hash=intent,
            )
            expected_key = ResourceKey("reports", record.id)
            if (
                receipt.operation_id != operation_id
                or receipt.replayed
                or len(receipt.changes) != 1
                or receipt.deleted_keys
                or receipt.changes[0].key != expected_key
                or receipt.changes[0].body != body
                or receipt.changes[0].etag != bytes_hash(body)
            ):
                fail("invalid_report_receipt", "incompatible_data")
            try:
                admitted = admit_report(receipt.changes[0])
            except ValueError:
                fail("invalid_report_receipt", "incompatible_data")
            return ReportView(admitted.record, admitted.etag, admitted.content, receipt.replayed)

    def read(self, report_id: str) -> ReportView:
        key = ResourceKey("reports", identifier(report_id))
        with self.source.consistent_read() as source:
            records = cast(SnapshotSource, source).capture_snapshot()
            stored = next((item for item in records if item.key == key), None)
            if stored is None:
                fail("report_missing", "not_found")
            return self._admit_captured_report(stored, records)

    def _admit_captured_report(
        self, stored: StoredRecord, records: tuple[StoredRecord, ...], *, replayed: bool = False
    ) -> ReportView:
        try:
            admitted = admit_report(stored)
        except ReportAdmissionError as error:
            fail(error.reason, "incompatible_data")
        validate_report_identity_value(admitted.etag, self.sanitizer)
        validate_report_identity_context(
            admitted.record.id,
            admitted.record.content_hash,
            admitted.content,
            self.sanitizer,
        )
        expected_raw: list[RawMaterial] = []
        if admitted.content.target.kind in ("diagnostic", "check"):
            frozen_group: FrozenDiagnosticSnapshot | FrozenCheckSnapshot
            snapshot_id = admitted.content.target.group_snapshot_id
            if snapshot_id is None:
                fail("report_link_mismatch", "incompatible_data")
            if admitted.content.target.kind == "diagnostic":
                frozen_group = read_diagnostic(records, snapshot_id)
                if frozen_group.group.id != admitted.content.target.target_id:
                    fail("report_link_mismatch", "incompatible_data")
                diagnostic_projection = project_diagnostic(records, frozen_group, self.sanitizer)
                if diagnostic_projection != admitted.content.diagnostic:
                    fail("report_link_mismatch", "incompatible_data")
                if admitted.record.diagnostic_snapshot_id != snapshot_id:
                    fail("report_link_mismatch", "incompatible_data")
            else:
                frozen_group = read_check(records, snapshot_id)
                if frozen_group.group.id != admitted.content.target.target_id:
                    fail("report_link_mismatch", "incompatible_data")
                check_projection = project_check(records, frozen_group, self.sanitizer)
                if check_projection != admitted.content.check:
                    fail("report_link_mismatch", "incompatible_data")
                if admitted.record.check_snapshot_id != snapshot_id:
                    fail("report_link_mismatch", "incompatible_data")
            expected_raw.extend(
                project_group_raw(records, frozen_group, self.sanitizer, admitted.content.raw)
            )
            group_context = admitted.content.diagnostic or admitted.content.check
            assert group_context is not None
            expected_limitations_value = expected_group_limitations(group_context, admitted.content)
        else:
            for saved_evaluation in admitted.content.evaluations:
                evaluation_id = saved_evaluation.context.evaluation_id
                linked = next(
                    (
                        item
                        for item in records
                        if item.key == ResourceKey("evaluations", evaluation_id)
                    ),
                    None,
                )
                if linked is None:
                    fail("report_link_mismatch", "incompatible_data")
                view = admit_evaluation_record(linked)
                projected, raw_items = project_evaluation(
                    records, view, self.sanitizer, admitted.content.raw
                )
                expected_raw.extend(raw_items)
                if projected != saved_evaluation:
                    if sanitizer_would_change(admitted.content, self.sanitizer):
                        fail("report_redaction_context_mismatch", "incompatible_data")
                    fail("report_link_mismatch", "incompatible_data")
            expected_limitations_value = expected_limitations(
                admitted.content.evaluations, admitted.content.raw_material
            )
        if admitted.content.limitations != expected_limitations_value:
            fail("report_link_mismatch", "incompatible_data")
        if admitted.record.comparison_id:
            linked = next(
                (
                    item
                    for item in records
                    if item.key == ResourceKey("comparisons", admitted.record.comparison_id)
                ),
                None,
            )
            if linked is None:
                fail("report_link_mismatch", "incompatible_data")
            comparison = admit_comparison_from_records(linked, records)
            actual = safe_comparison_outcomes(comparison.outcomes, self.sanitizer)
            if (
                actual != admitted.content.comparison
                or comparison.record.content_hash != admitted.content.target.comparison_hash
            ):
                fail("report_link_mismatch", "incompatible_data")
        if tuple(dict.fromkeys(expected_raw)) != admitted.content.raw_material:
            if sanitizer_would_change(admitted.content, self.sanitizer):
                fail("report_redaction_context_mismatch", "incompatible_data")
            fail("report_link_mismatch", "incompatible_data")
        return ReportView(admitted.record, admitted.etag, admitted.content, replayed)

    def metadata(self, report_id: str) -> ReportMetadata:
        key = ResourceKey("reports", identifier(report_id))
        with self.source.consistent_read() as source:
            records = cast(SnapshotSource, source).capture_snapshot((key,))
        stored = next((item for item in records if item.key == key), None)
        if stored is None:
            fail("report_missing", "not_found")
        try:
            result = admit_report_metadata(stored)
        except ReportAdmissionError as error:
            fail(error.reason, "incompatible_data")
        validate_report_metadata_identities(result, self.sanitizer)
        return result

    def list(self, *, cursor: str | None = None, limit: int = 50) -> ReportPage:
        if type(limit) is not int or not 1 <= limit <= 500:
            fail("invalid_page_limit")
        if cursor is not None:
            identifier(cursor)
        with self.source.consistent_read() as source:
            records = cast(SnapshotSource, source).capture_snapshot()
        reports = sorted(
            (item for item in records if item.key.collection == "reports" and item.key.scope == ()),
            key=lambda item: item.key.resource_id,
        )
        ids = tuple(
            item.key.resource_id
            for item in reports
            if cursor is None or item.key.resource_id > cursor
        )
        selected = ids[:limit]
        by_id = {item.key.resource_id: item for item in reports}
        output = []
        for report_id in selected:
            try:
                result = admit_report_metadata(by_id[report_id])
            except ReportAdmissionError as error:
                fail(error.reason, "incompatible_data")
            validate_report_metadata_identities(result, self.sanitizer)
            output.append(result)
        return ReportPage(tuple(output), len(reports), selected[-1] if len(ids) > limit else None)

    def render(self, report_id: str, *, format: ReportFormat) -> RenderedArtifact:
        view = self.read(report_id)
        try:
            artifact = render_content(view.record, view.content, format)
        except ValueError as error:
            if error.args == ("report_artifact_limit",):
                fail("report_artifact_limit")
            if error.args == ("invalid_report_format",):
                fail("invalid_report_format")
            raise
        if len(artifact.body) > 8 * 1024 * 1024:
            fail("report_artifact_limit")
        validate_rendered_artifact_identities(
            artifact.report_id, artifact.bytes_hash, self.sanitizer
        )
        return artifact

    def export(
        self, report_id: str, *, format: ReportFormat, destination: str, writer: ArtifactWriter
    ) -> ExportOutcome:
        artifact = self.render(report_id, format=format)
        report_meta = self.metadata(report_id)
        try:
            destination.encode("utf-8", "strict")
            destination_is_safe = self.sanitizer.text(destination) == destination
        except UnicodeEncodeError:
            destination_is_safe = False
        requested_destination = destination if destination_is_safe else None
        if not destination_is_safe:
            return ExportOutcome(
                report=report_meta,
                format=format,
                success=False,
                destination=None,
                requested_destination=None,
                artifact_hash=artifact.bytes_hash,
                byte_count=artifact.byte_count,
                error=ServiceError(code="validation_error", reason="report_sensitive_destination"),
            )

        def display_is_safe(value: str) -> bool:
            try:
                value.encode("utf-8", "strict")
            except UnicodeEncodeError:
                return False
            return self.sanitizer.text(value) == value

        try:
            outcome = writer.write(destination, artifact.body, display_is_safe=display_is_safe)
        except Exception:
            outcome = None
        if outcome is None:
            write_error = ServiceError(code="internal_error", reason="export_write_failed")
            return ExportOutcome(
                report=report_meta,
                format=format,
                success=False,
                destination=None,
                requested_destination=requested_destination,
                artifact_hash=artifact.bytes_hash,
                byte_count=artifact.byte_count,
                error=write_error,
            )
        if outcome.success and (
            outcome.destination is None or not display_is_safe(outcome.destination)
        ):
            return ExportOutcome(
                report=report_meta,
                format=format,
                success=False,
                destination=None,
                requested_destination=requested_destination,
                artifact_hash=artifact.bytes_hash,
                byte_count=artifact.byte_count,
                error=ServiceError(code="validation_error", reason="report_sensitive_destination"),
            )
        destination_error: ServiceError | None
        if not outcome.success and outcome.error is None:
            destination_error = ServiceError(code="internal_error", reason="export_write_failed")
        else:
            destination_error = outcome.error
        return ExportOutcome(
            report=report_meta,
            format=format,
            success=outcome.success,
            destination=outcome.destination,
            requested_destination=requested_destination,
            artifact_hash=artifact.bytes_hash,
            byte_count=artifact.byte_count,
            error=destination_error,
            durability_warning=outcome.durability_warning,
        )
