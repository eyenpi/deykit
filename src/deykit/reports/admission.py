"""Pure immutable report and content admission."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from pydantic import ValidationError

from deykit.contracts.codec import load_record
from deykit.contracts.json_value import JsonError, parse_json, semantic_hash
from deykit.contracts.ports import StoredRecord
from deykit.contracts.records import ReportRecord
from deykit.reports.models import RawChoices, ReportContent, ReportMetadata


@dataclass(frozen=True)
class AdmittedReport:
    record: ReportRecord
    content: ReportContent
    etag: str


class ReportAdmissionError(ValueError):
    """A stable, input-free report admission reason."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _has_persisted_version(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    version = value.get("schema_version")
    return isinstance(version, Decimal) and version == 1 and version.as_tuple().exponent == 0


def report_hash(record: ReportRecord, content: ReportContent) -> str:
    return semantic_hash(
        {
            "profile": "deykit-report-v1",
            "evaluation_ids": list(record.evaluation_ids),
            "result_snapshot_ids": list(record.result_snapshot_ids),
            "label_snapshot_ids": list(record.label_snapshot_ids),
            "comparison_id": record.comparison_id,
            "diagnostic_snapshot_id": record.diagnostic_snapshot_id,
            "check_snapshot_id": record.check_snapshot_id,
            "includes_raw_input": record.includes_raw_input,
            "includes_raw_request": record.includes_raw_request,
            "includes_raw_response": record.includes_raw_response,
            "content": parse_json(record.content_source),
        }
    )


def admit_report(stored: StoredRecord) -> AdmittedReport:
    """Validate storage identity, strict v1 profile, links, flags and semantic hash."""
    try:
        record = load_record(ReportRecord, stored.body)
        if (
            stored.key.collection != "reports"
            or stored.key.scope
            or record.id != stored.key.resource_id
        ):
            raise ReportAdmissionError("report_record_identity_mismatch")
        parsed = parse_json(record.content_source)
        if not isinstance(parsed, dict) or parsed.get("profile") != "deykit-report-v1":
            raise ReportAdmissionError("unsupported_report_profile")
        if not _has_persisted_version(parsed):
            raise ReportAdmissionError("missing_schema_version")
        evaluations = parsed.get("evaluations")
        if not isinstance(evaluations, list) or any(
            not isinstance(item, dict) or not _has_persisted_version(item.get("metrics"))
            for item in evaluations
        ):
            raise ReportAdmissionError("missing_schema_version")
        content = ReportContent.model_validate_json(
            record.content_source, context={"persisted": True}
        )
        target = content.target
        expected_evaluations = tuple(dict.fromkeys(target.evaluation_ids))
        expected_results = tuple(dict.fromkeys(target.result_snapshot_ids))
        expected_labels = tuple(dict.fromkeys(target.label_snapshot_ids))
        if (
            record.evaluation_ids != expected_evaluations
            or record.result_snapshot_ids != expected_results
            or record.label_snapshot_ids != expected_labels
            or record.comparison_id != target.comparison_id
            or record.diagnostic_snapshot_id is not None
            or record.check_snapshot_id is not None
            or RawChoices(
                inputs=record.includes_raw_input,
                requests=record.includes_raw_request,
                responses=record.includes_raw_response,
            )
            != content.raw
            or record.content_hash != report_hash(record, content)
        ):
            raise ReportAdmissionError("report_hash_mismatch")
        if len(set(record.evaluation_ids)) != len(record.evaluation_ids):
            raise ReportAdmissionError("report_link_mismatch")
        return AdmittedReport(record, content, stored.etag)
    except ReportAdmissionError:
        raise
    except JsonError as error:
        raise ReportAdmissionError(error.code) from None
    except (ValidationError, ValueError):
        raise ReportAdmissionError("invalid_report_content") from None


def admit_report_metadata(stored: StoredRecord) -> ReportMetadata:
    """Admit safe report listing metadata without walking linked source records."""
    try:
        record = load_record(ReportRecord, stored.body)
    except JsonError as error:
        raise ReportAdmissionError(error.code) from None
    if (
        stored.key.collection != "reports"
        or stored.key.scope
        or record.id != stored.key.resource_id
    ):
        raise ReportAdmissionError("report_record_identity_mismatch")
    try:
        parsed = parse_json(record.content_source)
    except JsonError:
        return ReportMetadata(
            report_id=record.id,
            content_hash=record.content_hash,
            created_at=record.created_at,
            raw=RawChoices(
                inputs=record.includes_raw_input,
                requests=record.includes_raw_request,
                responses=record.includes_raw_response,
            ),
            evaluation_ids=record.evaluation_ids,
            result_snapshot_ids=record.result_snapshot_ids,
            label_snapshot_ids=record.label_snapshot_ids,
            comparison_id=record.comparison_id,
            diagnostic_snapshot_id=record.diagnostic_snapshot_id,
            check_snapshot_id=record.check_snapshot_id,
            legacy=True,
            nonexportable_reason="unsupported_report_profile",
        )
    if not isinstance(parsed, dict) or parsed.get("profile") != "deykit-report-v1":
        return ReportMetadata(
            report_id=record.id,
            content_hash=record.content_hash,
            created_at=record.created_at,
            raw=RawChoices(
                inputs=record.includes_raw_input,
                requests=record.includes_raw_request,
                responses=record.includes_raw_response,
            ),
            evaluation_ids=record.evaluation_ids,
            result_snapshot_ids=record.result_snapshot_ids,
            label_snapshot_ids=record.label_snapshot_ids,
            comparison_id=record.comparison_id,
            diagnostic_snapshot_id=record.diagnostic_snapshot_id,
            check_snapshot_id=record.check_snapshot_id,
            legacy=True,
            nonexportable_reason="unsupported_report_profile",
        )
    try:
        admitted = admit_report(stored)
    except ReportAdmissionError:
        raise
    return metadata(admitted)


def metadata(admitted: AdmittedReport) -> ReportMetadata:
    content = admitted.content
    modes: list[str] = []
    for item in content.evaluations:
        mode = item.metrics.evidence_mode
        if mode not in modes:
            modes.append(mode)
    return ReportMetadata(
        report_id=admitted.record.id,
        content_hash=admitted.record.content_hash,
        created_at=admitted.record.created_at,
        target_id=content.target.target_id,
        target_kind=content.target.kind,
        raw=content.raw,
        evaluation_ids=admitted.record.evaluation_ids,
        result_snapshot_ids=admitted.record.result_snapshot_ids,
        label_snapshot_ids=admitted.record.label_snapshot_ids,
        comparison_id=admitted.record.comparison_id,
        diagnostic_snapshot_id=admitted.record.diagnostic_snapshot_id,
        check_snapshot_id=admitted.record.check_snapshot_id,
        evidence_modes=tuple(modes),
    )
