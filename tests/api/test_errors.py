import json

from deykit.api.errors import error_response
from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError
from deykit.contracts.selection import ResourceChoice, SelectionDetails


def test_api_failure_preserves_transient_selection_at_top_level() -> None:
    selection = SelectionDetails(
        choices=(
            ResourceChoice(kind="decision", resource_id="decision-1", scope=("project-1",)),
            ResourceChoice(kind="decision", resource_id="decision-2", scope=("project-1",)),
        )
    )
    response = error_response(
        ServiceFailure(
            ServiceError(code="not_found", reason="resource_missing", resource_id="missing"),
            selection=selection,
        )
    )

    assert response.status_code == 404
    body = json.loads(response.body)
    assert body["error"] == {
        "schema_version": 1,
        "code": "not_found",
        "message": "The requested resource was not found.",
        "resource_id": "missing",
        "row": None,
        "reason": "resource_missing",
        "correlation_id": None,
    }
    assert body["selection"] == {
        "choices": [
            {"kind": "decision", "resource_id": "decision-1", "scope": ["project-1"]},
            {"kind": "decision", "resource_id": "decision-2", "scope": ["project-1"]},
        ]
    }


def test_api_failure_keeps_selection_out_of_persisted_error_record() -> None:
    response = error_response(
        ServiceFailure(
            ServiceError(code="not_found", reason="resource_missing"),
            selection=SelectionDetails(
                choices=(ResourceChoice(kind="dataset", resource_id="dataset-1"),)
            ),
        )
    )
    body = json.loads(response.body)

    assert "selection" not in body["error"]
    assert body["selection"] == {
        "choices": [{"kind": "dataset", "resource_id": "dataset-1", "scope": []}]
    }
