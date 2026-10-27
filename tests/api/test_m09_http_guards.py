"""Focused M09 HTTP admission, projection, and protected report regressions."""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI

from deykit.api.app import create_app
from deykit.api.config import LocalServerConfig
from deykit.api.dependencies import ApiDependencies, ApiProjectSource
from deykit.api.recent import RecentProjectsStore
from deykit.api.runtime import SystemClock, new_id
from deykit.api.security import LocalBoundary
from deykit.application.datasets import CaseInput, DatasetService
from deykit.application.definitions import DecisionService
from deykit.application.fixtures import FixtureService
from deykit.application.labels import LabelService
from deykit.application.reports import ReportService
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.json_value import JsonDocument
from deykit.contracts.records import (
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    FixtureBinding,
    NormalizedAnswer,
)
from deykit.domain.definitions import select_input
from deykit.providers.choice import compile_choice
from deykit.providers.configuration import create_provider_operations
from deykit.runner.backends import ProviderBackends
from deykit.storage import FileProjectSource
from deykit.storage.demo_destination import FileDemoDestinationFactory
from deykit.storage.demo_staging import DemoStagingSource
from deykit.storage.source import API_SOURCE_ADMISSION_TIMEOUT_SECONDS


@dataclass(frozen=True)
class _AppContext:
    boundary: LocalBoundary
    api: FastAPI
    origin: str
    dependencies: ApiDependencies
    opened: list[FileProjectSource]


def _app(tmp_path: Path) -> _AppContext:
    origin = "http://127.0.0.1:8743"
    opened: list[FileProjectSource] = []

    def open_source(path: Path, create: bool) -> FileProjectSource:
        source = FileProjectSource(
            path,
            create=create,
            admission_timeout_seconds=API_SOURCE_ADMISSION_TIMEOUT_SECONDS,
        )
        opened.append(source)
        return source

    clock = SystemClock()
    dependencies = ApiDependencies(
        clock=clock,
        id_factory=new_id,
        source_factory=open_source,
        recent_store=RecentProjectsStore(
            clock,
            tmp_path / "recent.json",
        ),
        demo_staging_factory=DemoStagingSource,
        demo_destination_factory=FileDemoDestinationFactory(
            admission_timeout_seconds=API_SOURCE_ADMISSION_TIMEOUT_SECONDS
        ),
        provider_operations_factory=create_provider_operations,
        backends_factory=ProviderBackends,
    )
    boundary = create_app(
        LocalServerConfig(
            "127.0.0.1:8743",
            origin,
        ),
        dependencies,
    )
    return _AppContext(boundary, cast(FastAPI, boundary.app), origin, dependencies, opened)


async def _session(client: httpx.AsyncClient, origin: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/session/bootstrap",
        headers={"x-deykit-bootstrap": "1", "origin": origin},
        json={"schema_version": 1},
    )
    assert response.status_code == 200
    return {
        "x-deykit-capability": response.json()["data"]["capability"],
        "origin": origin,
        "content-type": "application/json",
    }


async def _register_project(
    client: httpx.AsyncClient, headers: dict[str, str], path: Path, name: str
) -> str:
    response = await client.post(
        "/api/v1/projects/register",
        headers=headers,
        json={
            "schema_version": 1,
            "operation_id": f"register-{name.lower().replace(' ', '-')}",
            "action": "create",
            "path": str(path),
            "name": name,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["registration_id"]


@pytest.mark.parametrize(
    "selection",
    [
        {"pricing": {"rates": []}},
        {"category_only": True},
        {"preset": "classification", "target_kind": "check"},
        {"preset": "classification", "target_kind": "diagnostic"},
    ],
)
def test_report_invalid_preset_combinations_are_safe_client_errors(tmp_path, selection):
    context = _app(tmp_path)

    async def exercise():
        async with context.api.router.lifespan_context(context.api):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=context.boundary, raise_app_exceptions=False),
                base_url=context.origin,
            ) as client:
                headers = await _session(client, context.origin)
                registration = await _register_project(
                    client, headers, tmp_path / "invalid-report", "Invalid Report"
                )
                source = context.api.state.project_registry.require(registration).source
                before = source.capture_snapshot()
                response = await client.post(
                    f"/api/v1/projects/{registration}/reports",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "invalid-report",
                        "target_id": "private-sentinel",
                        **selection,
                    },
                )
                assert response.status_code == 422, response.text
                assert response.json()["error"]["code"] == "validation_error"
                assert "private-sentinel" not in response.text
                assert source.capture_snapshot() == before

    asyncio.run(exercise())


def _seed_one_case(source: ApiProjectSource, dependencies: ApiDependencies) -> None:
    definition = ChoiceDefinition(
        input_kind="json",
        selected_fields=("text",),
        input_schema_source=(
            '{"type":"object","required":["text"],"properties":{"text":{"type":"string"}}}'
        ),
        questions=(
            ChoiceQuestion(
                id="question",
                instructions="Choose one option.",
                options=(
                    ChoiceOption(id="yes", name="Yes"),
                    ChoiceOption(id="no", name="No"),
                ),
            ),
        ),
    )
    decisions = DecisionService(source, dependencies.clock, dependencies.id_factory)
    decisions.create(
        "decision",
        "Decision",
        dump_record(definition).decode("utf-8"),
        operation_id="seed-decision",
    )
    datasets = DatasetService(source, dependencies.clock, dependencies.id_factory)
    dataset = datasets.create("Dataset", dataset_id="dataset", operation_id="seed-dataset")
    case_source = '{"text":"hello"}'
    case = datasets.add_case(
        "dataset",
        CaseInput(
            input_kind="json",
            input_source=case_source,
            tags=("gold",),
            split="development",
        ),
        expected_dataset_etag=dataset.etag,
        operation_id="seed-case",
        case_id="case",
    )
    assert case.case is not None
    fixtures = FixtureService(source, dependencies.clock)
    fixtures.create_profile("fixture-provider", "authored-api-v1", operation_id="seed-profile")
    compiled = compile_choice(
        definition,
        select_input(definition, JsonDocument(case_source)).value,
        "authored-api-v1",
        adapter="fixture",
    )
    binding = FixtureBinding(
        id="binding",
        case_id="case",
        request=compiled,
        answer=NormalizedAnswer(
            question_id="question", option_id="yes", reported_model="authored-api-v1"
        ),
    )
    fixtures.create(
        "fixture-set",
        "decision",
        "dataset",
        "Authored fixture",
        "authored-api-v1",
        (dump_record(binding),),
        operation_id="seed-fixture-set",
    )
    labels = LabelService(source, dependencies.clock, dependencies.id_factory)
    review = labels.read("decision", "dataset", "case").review
    labels.set(
        review,
        ("yes",),
        provenance="human",
        operation_id="seed-label",
    )


def _add_second_case_order_fixture(source: ApiProjectSource, dependencies: ApiDependencies) -> None:
    decision = DecisionService(source, dependencies.clock, dependencies.id_factory).read("decision")
    definition = load_record(ChoiceDefinition, decision.draft.record.editor_source)
    datasets = DatasetService(source, dependencies.clock, dependencies.id_factory)
    dataset = datasets.read("dataset")
    case_source = '{"text":"world"}'
    case = datasets.add_case(
        "dataset",
        CaseInput(
            input_kind="json",
            input_source=case_source,
            tags=("gold",),
            split="development",
        ),
        expected_dataset_etag=dataset.etag,
        operation_id="seed-second-case",
        case_id="case-two",
    )
    assert case.case is not None
    bindings = []
    for case_id, input_source in (("case", '{"text":"hello"}'), ("case-two", case_source)):
        compiled = compile_choice(
            definition,
            select_input(definition, JsonDocument(input_source)).value,
            "authored-api-v1",
            adapter="fixture",
        )
        bindings.append(
            FixtureBinding(
                id=f"binding-{case_id}",
                case_id=case_id,
                request=compiled,
                answer=NormalizedAnswer(
                    question_id="question", option_id="yes", reported_model="authored-api-v1"
                ),
            )
        )
    FixtureService(source, dependencies.clock).create(
        "fixture-set-two-cases",
        "decision",
        "dataset",
        "Authored two-case fixture",
        "authored-api-v1",
        tuple(dump_record(binding) for binding in bindings),
        operation_id="seed-two-case-fixture-set",
    )


def _run_request() -> dict[str, object]:
    return {
        "decision_id": "decision",
        "dataset_id": "dataset",
        "mode": "fixture",
        "provider_id": "fixture-provider",
        "fixture_set_id": "fixture-set",
        "settings": {"max_attempts": 1, "concurrency": 1},
    }


def test_http_review_hash_and_group_cap_reject_without_business_writes(tmp_path: Path) -> None:
    context = _app(tmp_path)

    async def exercise() -> None:
        async with context.api.router.lifespan_context(context.api):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=context.boundary), base_url=context.origin
            ) as client:
                headers = await _session(client, context.origin)
                registration_id = await _register_project(
                    client, headers, tmp_path / "review-project", "Review Project"
                )
                source: ApiProjectSource = context.api.state.project_registry.require(
                    registration_id
                ).source
                _seed_one_case(source, context.dependencies)
                _add_second_case_order_fixture(source, context.dependencies)
                base = f"/api/v1/projects/{registration_id}"
                run_request = {
                    **_run_request(),
                    "fixture_set_id": "fixture-set-two-cases",
                    "settings": {"max_attempts": 3, "concurrency": 1},
                }
                preview = await client.post(
                    f"{base}/runs/preview",
                    headers=headers,
                    json={"schema_version": 1, "request": run_request},
                )
                assert preview.status_code == 200, preview.text
                before = source.capture_snapshot()
                stale = await client.post(
                    f"{base}/runs",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "stale-run",
                        "expected_review_context_hash": "0" * 64,
                        "request": run_request,
                    },
                )
                assert stale.status_code == 409
                assert stale.json()["error"]["reason"] == "run_source_changed"
                assert source.capture_snapshot() == before

                choice_preview_request = {
                    "run": {**run_request, "settings": {"max_attempts": 4, "concurrency": 1}},
                    "orders": 2,
                    "seed": "0",
                }
                group_preview = await client.post(
                    f"{base}/diagnostics/choice-order/preview",
                    headers=headers,
                    json={"schema_version": 1, "request": choice_preview_request},
                )
                assert group_preview.status_code == 200, group_preview.text
                assert group_preview.json()["data"]["initial_requests"] == "4"
                choice_start_request = {
                    **choice_preview_request,
                    "run": {**run_request, "settings": {"max_attempts": 3, "concurrency": 1}},
                }
                cap_rejected_preview = await client.post(
                    f"{base}/diagnostics/choice-order/preview",
                    headers=headers,
                    json={"schema_version": 1, "request": choice_start_request},
                )
                assert cap_rejected_preview.status_code == 422, cap_rejected_preview.text
                assert cap_rejected_preview.json()["error"]["reason"] == (
                    "group_initial_requests_exceed_cap"
                )
                assert source.capture_snapshot() == before
                group_start = await client.post(
                    f"{base}/diagnostics/choice-order",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "cap-three-group",
                        "expected_review_context_hash": group_preview.json()["data"][
                            "review_context_hash"
                        ],
                        "request": choice_start_request,
                    },
                )
                assert group_start.status_code == 409, group_start.text
                assert group_start.json()["error"]["reason"] == "run_source_changed"
                assert source.capture_snapshot() == before

    asyncio.run(exercise())


def test_http_results_evaluation_pin_and_report_download_are_protected(tmp_path: Path) -> None:
    context = _app(tmp_path)

    async def exercise() -> None:
        async with context.api.router.lifespan_context(context.api):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=context.boundary), base_url=context.origin
            ) as client:
                headers = await _session(client, context.origin)
                registration_id = await _register_project(
                    client, headers, tmp_path / "evidence-project", "Evidence Project"
                )
                source: ApiProjectSource = context.api.state.project_registry.require(
                    registration_id
                ).source
                _seed_one_case(source, context.dependencies)
                base = f"/api/v1/projects/{registration_id}"
                run_request = _run_request()
                preview = await client.post(
                    f"{base}/runs/preview",
                    headers=headers,
                    json={"schema_version": 1, "request": run_request},
                )
                assert preview.status_code == 200, preview.text
                accepted = await client.post(
                    f"{base}/runs",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "http-run",
                        "expected_review_context_hash": preview.json()["data"][
                            "review_context_hash"
                        ],
                        "request": run_request,
                    },
                )
                assert accepted.status_code == 202, accepted.text
                run_id = accepted.json()["data"]["run_id"]
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    run = await client.get(f"{base}/runs/{run_id}", headers=headers)
                    if (
                        run.status_code == 409
                        and run.json().get("error", {}).get("reason") == "source_busy"
                    ):
                        await asyncio.sleep(0.01)
                        continue
                    assert run.status_code == 200, run.text
                    run_data = run.json()["data"]
                    if not run_data["execution_active"] and run_data["latest_result_snapshot_id"]:
                        break
                    await asyncio.sleep(0.01)
                else:
                    raise AssertionError("authored fixture run did not settle")

                evaluation = await client.post(
                    f"{base}/runs/{run_id}/evaluations",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "http-evaluation",
                        "result_snapshot_id": run_data["latest_result_snapshot_id"],
                    },
                )
                assert evaluation.status_code == 200, evaluation.text
                evaluation_id = evaluation.json()["data"]["evaluation_id"]
                filtered = await client.get(
                    f"{base}/runs/{run_id}/results",
                    params={
                        "evaluation_id": evaluation_id,
                        "status": "valid",
                        "split": "development",
                        "tag": "gold",
                        "limit": "1",
                    },
                    headers=headers,
                )
                assert filtered.status_code == 200, filtered.text
                filtered_data = filtered.json()["data"]
                assert filtered_data["evaluation_id"] == evaluation_id
                assert filtered_data["selected_count"] == "1"
                assert filtered_data["filtered_count"] == "1"
                assert filtered_data["next_cursor"] is None
                assert [row["source"]["case_id"] for row in filtered_data["items"]] == ["case"]

                default = await client.get(f"{base}/runs/{run_id}/results/case", headers=headers)
                assert default.status_code == 200, default.text
                assert default.json()["data"]["source"]["input_source"] is None
                detailed = await client.get(
                    f"{base}/runs/{run_id}/results/case",
                    params={
                        "evaluation_id": evaluation_id,
                        "include_input": "true",
                        "include_request": "true",
                        "include_response": "true",
                        "include_attempts": "true",
                    },
                    headers=headers,
                )
                assert detailed.status_code == 200, detailed.text
                details = detailed.json()["data"]["source"]
                assert details["input_source"] == '{"text":"hello"}'
                assert details["attempts"][0]["request_body_source"]
                assert "response_source" in details["attempts"][0]
                invalid_filter = await client.get(
                    f"{base}/runs/{run_id}/results",
                    params={"status": "Bearer-private-sentinel"},
                    headers=headers,
                )
                assert invalid_filter.status_code == 422
                assert "Bearer-private-sentinel" not in invalid_filter.text

                report = await client.post(
                    f"{base}/reports",
                    headers=headers,
                    json={
                        "schema_version": 1,
                        "operation_id": "http-report",
                        "target_id": evaluation_id,
                        "target_kind": "evaluation",
                        "preset": "classification",
                        "pricing": {"rates": []},
                        "category_only": True,
                    },
                )
                assert report.status_code == 200, report.text
                report_id = report.json()["data"]["report_id"]
                before = source.capture_snapshot()
                expected_json = (
                    ReportService(source, context.dependencies.clock)
                    .render(report_id, format="json")
                    .body
                )
                other_registration = await _register_project(
                    client, headers, tmp_path / "other-project", "Other Project"
                )
                cross_registration = await client.get(
                    f"/api/v1/projects/{other_registration}/reports/{report_id}/download"
                    "?format=json",
                    headers=headers,
                )
                assert cross_registration.status_code == 404
                download = await client.get(
                    f"{base}/reports/{report_id}/download?format=json", headers=headers
                )
                assert download.status_code == 200
                assert download.content == expected_json
                assert download.json()["content"]["classification"]["category_only_scoring"] == (
                    "jev_probability_only_v1"
                )
                assert download.headers["content-type"] == "application/octet-stream"
                assert download.headers["cache-control"] == "no-store"
                assert download.headers["x-content-type-options"] == "nosniff"
                assert download.headers["content-disposition"] == (
                    f'attachment; filename="report-{report_id}.json"'
                )
                markdown = await client.get(
                    f"{base}/reports/{report_id}/download?format=markdown", headers=headers
                )
                expected_markdown = (
                    ReportService(source, context.dependencies.clock)
                    .render(report_id, format="markdown")
                    .body
                )
                assert markdown.status_code == 200
                assert markdown.content == expected_markdown
                assert markdown.headers["content-type"] == "text/plain; charset=utf-8"
                csv_download = await client.get(
                    f"{base}/reports/{report_id}/download?format=csv", headers=headers
                )
                assert csv_download.status_code == 200
                assert csv_download.content == (
                    ReportService(source, context.dependencies.clock)
                    .render(report_id, format="csv")
                    .body
                )
                assert csv_download.headers["content-type"] == "text/csv; charset=utf-8"
                assert csv_download.headers["cache-control"] == "no-store"
                assert csv_download.headers["content-disposition"] == (
                    f'attachment; filename="report-{report_id}.csv"'
                )

                missing = await client.get(
                    f"{base}/reports/missing-report/download?format=markdown", headers=headers
                )
                assert missing.status_code == 404
                assert missing.json()["error"]["resource_id"] == "missing-report"
                token_query = await client.get(
                    f"{base}/reports/{report_id}/download?format=json&token=private-sentinel",
                    headers=headers,
                )
                assert token_query.status_code == 422
                assert "private-sentinel" not in token_query.text
                assert source.capture_snapshot() == before

    asyncio.run(exercise())


def test_report_download_authorizes_before_project_and_report_lookup(tmp_path: Path) -> None:
    context = _app(tmp_path)

    async def exercise() -> None:
        async with context.api.router.lifespan_context(context.api):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=context.boundary), base_url=context.origin
            ) as client:
                source_opens = len(context.opened)
                denied = await client.get(
                    "/api/v1/projects/not-registered/reports/guess/download?format=json",
                    headers={"origin": context.origin},
                )
                assert denied.status_code == 403
                assert len(context.opened) == source_opens
                headers = await _session(client, context.origin)
                unknown_registration = await client.get(
                    "/api/v1/projects/not-registered/reports/guess/download?format=json",
                    headers=headers,
                )
                assert unknown_registration.status_code == 404
                assert unknown_registration.json()["error"]["resource_id"] == "not-registered"
                assert len(context.opened) == source_opens

    asyncio.run(exercise())
