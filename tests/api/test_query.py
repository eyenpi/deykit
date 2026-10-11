"""The local boundary admits query keys only for implemented list/read routes."""

import pytest

from deykit.api.security import LocalBoundary


@pytest.mark.parametrize(
    ("path", "keys"),
    [
        (
            "/api/v1/projects/reg/decisions",
            {"include_archived", "cursor", "limit"},
        ),
        (
            "/api/v1/projects/reg/decisions/decision/diff",
            {"before", "after"},
        ),
        (
            "/api/v1/projects/reg/datasets/dataset/cases",
            {"cursor", "limit", "tag", "group_id", "split"},
        ),
        (
            "/api/v1/projects/reg/decisions/decision/datasets/dataset/labels",
            {"status", "cursor", "limit"},
        ),
        (
            "/api/v1/projects/reg/decisions/decision/datasets/dataset/labels/case/history",
            {"question_id"},
        ),
        (
            "/api/v1/projects/reg/providers/profile/models",
            {"timeout_seconds"},
        ),
    ],
)
def test_query_key_allowlist_matches_registered_routes(path: str, keys: set[str]) -> None:
    assert LocalBoundary.query_keys(path) == keys


def test_run_preview_admits_only_its_request_projection_flag() -> None:
    path = "/api/v1/projects/reg/runs/preview"
    assert LocalBoundary.query_keys(path, "POST") == {"include_request"}
    assert LocalBoundary.query_keys(path, "GET") == set()
    assert LocalBoundary.query_keys("/api/v1/projects/reg/fixtures") == {
        "cursor",
        "limit",
    }
