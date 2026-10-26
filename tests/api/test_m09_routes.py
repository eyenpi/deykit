"""Static route inventory and exact query-admission boundaries for M09."""

import asyncio

import httpx

from deykit.api.app import create_app
from deykit.api.config import LocalServerConfig
from deykit.api.security import LocalBoundary


def test_m09_route_inventory_and_binary_report_policy(security_api_dependencies):
    app = create_app(
        LocalServerConfig("127.0.0.1:8741", "http://127.0.0.1:8741"),
        security_api_dependencies(),
    ).app
    openapi = app.openapi()
    expected = {
        ("/api/v1/projects/{registration_id}/runs", "POST"),
        ("/api/v1/projects/{registration_id}/runs", "GET"),
        ("/api/v1/projects/{registration_id}/runs/preview", "POST"),
        ("/api/v1/projects/{registration_id}/runs/{run_id}", "GET"),
        ("/api/v1/projects/{registration_id}/runs/{run_id}/cancel", "POST"),
        ("/api/v1/projects/{registration_id}/runs/{run_id}/resume-preview", "POST"),
        ("/api/v1/projects/{registration_id}/runs/{run_id}/resume", "POST"),
        ("/api/v1/projects/{registration_id}/runs/{run_id}/results", "GET"),
        ("/api/v1/projects/{registration_id}/runs/{run_id}/results/{case_id}", "GET"),
        ("/api/v1/projects/{registration_id}/runs/{run_id}/evaluations", "POST"),
        ("/api/v1/projects/{registration_id}/runs/{run_id}/evaluations", "GET"),
        ("/api/v1/projects/{registration_id}/evaluations/{evaluation_id}", "GET"),
        ("/api/v1/projects/{registration_id}/runs/{run_id}/reevaluations", "POST"),
        ("/api/v1/projects/{registration_id}/runs/{run_id}/annotations", "GET"),
        ("/api/v1/projects/{registration_id}/runs/{run_id}/annotations", "POST"),
        ("/api/v1/projects/{registration_id}/annotations/{annotation_id}", "GET"),
        ("/api/v1/projects/{registration_id}/comparisons", "POST"),
        ("/api/v1/projects/{registration_id}/comparisons", "GET"),
        ("/api/v1/projects/{registration_id}/comparisons/{comparison_id}", "GET"),
        ("/api/v1/projects/{registration_id}/decisions/{decision_id}/regressions", "POST"),
        ("/api/v1/projects/{registration_id}/decisions/{decision_id}/regressions", "GET"),
        (
            "/api/v1/projects/{registration_id}/decisions/{decision_id}/regressions/{regression_id}/remove",
            "POST",
        ),
        ("/api/v1/projects/{registration_id}/diagnostics/choice-order", "POST"),
        ("/api/v1/projects/{registration_id}/diagnostics/choice-order/preview", "POST"),
        ("/api/v1/projects/{registration_id}/diagnostics/{group_id}", "GET"),
        ("/api/v1/projects/{registration_id}/diagnostics/{group_id}/cancel", "POST"),
        ("/api/v1/projects/{registration_id}/diagnostics/{group_id}/resume-preview", "POST"),
        ("/api/v1/projects/{registration_id}/diagnostics/{group_id}/resume", "POST"),
        ("/api/v1/projects/{registration_id}/checks", "POST"),
        ("/api/v1/projects/{registration_id}/checks/preview", "POST"),
        ("/api/v1/projects/{registration_id}/checks/{group_id}", "GET"),
        ("/api/v1/projects/{registration_id}/checks/{group_id}/cancel", "POST"),
        ("/api/v1/projects/{registration_id}/checks/{group_id}/resume-preview", "POST"),
        ("/api/v1/projects/{registration_id}/checks/{group_id}/resume", "POST"),
        ("/api/v1/projects/{registration_id}/reports", "POST"),
        ("/api/v1/projects/{registration_id}/reports", "GET"),
        ("/api/v1/projects/{registration_id}/reports/{report_id}", "GET"),
        (
            "/api/v1/projects/{registration_id}/reports/{report_id}/download",
            "GET",
        ),
    }
    m09_operation_ids = {
        "startRun",
        "previewRun",
        "listRuns",
        "readRun",
        "cancelRun",
        "previewRunResume",
        "resumeRun",
        "listResults",
        "readResult",
        "createEvaluation",
        "listEvaluations",
        "readEvaluation",
        "reevaluateRun",
        "listAnnotations",
        "addAnnotation",
        "readAnnotation",
        "createComparison",
        "listComparisons",
        "readComparison",
        "addRegression",
        "listRegressions",
        "removeRegression",
        "startChoiceOrder",
        "previewChoiceOrder",
        "readChoiceOrder",
        "cancelChoiceOrder",
        "previewChoiceOrderResume",
        "resumeChoiceOrder",
        "startRegressionCheck",
        "previewRegressionCheck",
        "readCheck",
        "cancelCheck",
        "previewCheckResume",
        "resumeCheck",
        "createReport",
        "listReports",
        "readReport",
        "downloadReport",
    }
    operations = {
        (path, method.upper()): operation
        for path, path_item in openapi["paths"].items()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
        and operation.get("operationId") in m09_operation_ids
    }
    actual = set(operations)
    assert actual == expected
    for key in (
        ("/api/v1/projects/{registration_id}/runs", "POST"),
        ("/api/v1/projects/{registration_id}/diagnostics/choice-order", "POST"),
        ("/api/v1/projects/{registration_id}/checks", "POST"),
    ):
        assert "202" in operations[key]["responses"]
    download = operations[
        ("/api/v1/projects/{registration_id}/reports/{report_id}/download", "GET")
    ]
    assert download["operationId"] == "downloadReport"
    assert download["x-deykit-report-download-v1"] == {
        "formatParameter": "format",
        "reportIdParameter": "report_id",
        "maxBytes": 41943040,
        "formats": {
            "json": {"contentType": "application/octet-stream", "extension": "json"},
            "markdown": {"contentType": "text/plain; charset=utf-8", "extension": "md"},
            "csv": {"contentType": "text/csv; charset=utf-8", "extension": "csv"},
        },
    }
    content = download["responses"]["200"]["content"]
    for media_type in (
        "application/octet-stream",
        "text/plain; charset=utf-8",
        "text/csv; charset=utf-8",
    ):
        assert content[media_type]["schema"] == {"type": "string", "format": "binary"}


def test_m09_query_keys_are_exact_and_route_specific():
    boundary = LocalBoundary.query_keys
    assert boundary("/api/v1/projects/p/runs/r/resume-preview", "POST") == {
        "retry_unknown",
        "max_attempts",
    }
    assert boundary("/api/v1/projects/p/runs", "GET") == {
        "decision_id",
        "status",
        "cursor",
        "limit",
    }
    assert boundary("/api/v1/projects/p/runs", "POST") == set()
    assert boundary("/api/v1/projects/p/runs/r/results/c", "GET") == {
        "evaluation_id",
        "expected_result_snapshot_id",
        "expected_label_snapshot_id",
        "include_input",
        "include_request",
        "include_response",
        "include_attempts",
    }
    assert boundary("/api/v1/projects/p/reports/report/download", "GET") == {"format"}
    assert boundary("/api/v1/projects/p/reports/report/download", "POST") == set()
    assert boundary("/api/v1/projects/p/reports/report/download/extra") == set()


def test_all_post_resume_previews_require_versioned_json_before_project_lookup(
    security_api_dependencies,
):
    origin = "http://127.0.0.1:8742"
    app = create_app(
        LocalServerConfig("127.0.0.1:8742", origin),
        security_api_dependencies(),
    )
    paths = (
        "/api/v1/projects/registration/runs/run/resume-preview",
        "/api/v1/projects/registration/diagnostics/group/resume-preview",
        "/api/v1/projects/registration/checks/group/resume-preview",
    )

    async def exercise() -> None:
        async with app.app.router.lifespan_context(app.app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=origin
            ) as client:
                bootstrap = await client.post(
                    "/api/v1/session/bootstrap",
                    headers={"x-deykit-bootstrap": "1", "origin": origin},
                    json={"schema_version": 1},
                )
                capability = bootstrap.json()["data"]["capability"]
                headers = {
                    "x-deykit-capability": capability,
                    "origin": origin,
                    "content-type": "application/json",
                }
                for path in paths:
                    missing = await client.post(path, headers=headers, content=b"")
                    wrong_version = await client.post(
                        path, headers=headers, json={"schema_version": 2}
                    )
                    assert missing.status_code == 422
                    assert wrong_version.status_code == 422
                wrong_media = await client.post(
                    paths[0],
                    headers={**headers, "content-type": "text/plain"},
                    content=b'{"schema_version":1}',
                )
                assert wrong_media.status_code == 415

    asyncio.run(exercise())
