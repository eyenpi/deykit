"""Typed transport contract for the M12 result and pinned snapshot projections."""

from deykit.api.dto.groups import SnapshotMetadataDTO, SnapshotResultDTO
from deykit.api.dto.results import AssessmentCountsDTO, ResultContextDTO
from deykit.api.security import LocalBoundary


def test_result_routes_allow_only_paired_context_selectors_and_assessment_filter():
    result_path = "/api/v1/projects/reg-1/runs/run-1/results"
    detail_path = f"{result_path}/case-1"
    assert LocalBoundary.query_keys(result_path, "GET") == {
        "evaluation_id",
        "status",
        "split",
        "tag",
        "assessment_filter",
        "expected_result_snapshot_id",
        "expected_label_snapshot_id",
        "cursor",
        "limit",
    }
    assert LocalBoundary.query_keys(detail_path, "GET") == {
        "evaluation_id",
        "expected_result_snapshot_id",
        "expected_label_snapshot_id",
        "include_input",
        "include_request",
        "include_response",
        "include_attempts",
    }
    assert "credential" not in LocalBoundary.query_keys(result_path, "GET")
    assert LocalBoundary.query_keys(result_path, "POST") == set()


def test_context_and_snapshot_transport_keep_numeric_values_as_text():
    digest = "a" * 64
    counts = AssessmentCountsDTO(all="12", inspect="4", incorrect="2", unlabelled="3")
    context = ResultContextDTO(
        run_id="run-1",
        result_snapshot_id="result-1",
        label_snapshot_id="label-1",
        evaluation_id=None,
        decision_id="decision-1",
        dataset_id="dataset-1",
        decision_revision_id="revision-1",
        decision_definition_hash=digest,
        dataset_snapshot_id="dataset-snapshot-1",
        dataset_content_hash=digest,
        label_content_hash=digest,
        result_content_hash=digest,
        evaluation_mode="original",
        through_event_sequence="9007199254740993",
    )
    snapshot = SnapshotMetadataDTO(
        id="snapshot-1",
        sequence="9007199254740993",
        group_id="group-1",
        segment_id=None,
        content_hash=digest,
        created_at="2026-10-11T00:00:00Z",
        results=(SnapshotResultDTO(run_id="run-1", result_snapshot_id="result-1"),),
    )
    assert counts.all == "12"
    assert context.through_event_sequence == "9007199254740993"
    assert snapshot.sequence == "9007199254740993"
