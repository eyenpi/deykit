"""Real CLI/runner integration with only the outbound HTTP exchange mocked."""

import json
import shutil
from dataclasses import replace

import httpx
import pytest
from test_cli_execution import invoke
from test_image_execution import seed_image

from deykit.application.errors import ServiceFailure
from deykit.application.execution import ExecutionService
from deykit.contracts.images import ImagePreparation
from deykit.contracts.json_value import parse_json
from deykit.providers.choice import JevChoiceCompiler
from deykit.providers.http import OneShotHttp
from deykit.providers.jev_images import IMAGE_HEADERS_SOURCE
from deykit.runner.backends import ProviderBackends
from deykit.runner.planner import RunRequest
from deykit.runner.review import run_review_hash


def configure(source, monkeypatch):
    monkeypatch.setenv("OFFLINE_IMAGE_TEST_KEY", "OFFLINE_SENTINEL")
    result = invoke(
        source,
        "provider",
        "configure",
        "jev-images",
        "--adapter",
        "jev",
        "--model",
        "jev-1.14.0",
        "--credential-env",
        "OFFLINE_IMAGE_TEST_KEY",
    )
    assert result.exit_code == 0, result.output


def run_args(*extra):
    return (
        "run",
        "--decision",
        "decision",
        "--dataset",
        "data",
        "--mode",
        "live",
        "--provider",
        "jev-images",
        "--attempt-limit",
        "2",
        "--concurrency",
        "1",
        "--rate-retries",
        "0",
        *extra,
    )


@pytest.mark.parametrize("dimension", [280, 1024])
def test_cli_image_preview_unknown_resume_replay_and_raw_evidence(
    tmp_path, setup, monkeypatch, dimension
):
    source, _, _, clock, root, _ = seed_image(
        setup,
        tmp_path,
        preparation=ImagePreparation(mode="pad", min_width=dimension, min_height=dimension),
    )
    configure(source, monkeypatch)
    calls = []

    def handle(request):
        calls.append(request)
        assert request.headers["TypeSafe-Danger-Zone-Images"] == "true"
        if len(calls) == 1:
            raise httpx.ReadTimeout("authored unknown outcome")
        return httpx.Response(
            200,
            content=b'{"model":"jev-1.14.0","answers":{"q":'
            b'{"type":"choice","choice":"yes","probabilities":{"yes":1,"no":0},'
            b'"confidence":1}},"usage":{"input_tokens":100,"output_tokens":10}}',
        )

    monkeypatch.setattr(
        "deykit.providers.jev.OneShotHttp", lambda: OneShotHttp(httpx.MockTransport(handle))
    )
    preview = invoke(source, *run_args("--dry-run"))
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.stdout)["data"]["initial_requests"] == 1
    assert json.loads(preview.stdout)["data"]["semantic_headers_sources"] == [IMAGE_HEADERS_SOURCE]
    assert not calls and not source.list_ids("runs")
    service = ExecutionService(source, source, ProviderBackends(source, clock), clock)
    reviewed = service.review_preview(
        RunRequest(
            decision_id="decision", dataset_id="data", mode="live", provider_id="jev-images"
        ),
        include_request_source=True,
    )
    assert reviewed.case_reviews[0].semantic_headers_source == IMAGE_HEADERS_SOURCE
    assert "assets" in json.loads(reviewed.case_reviews[0].request_source)
    first = invoke(source, *run_args("--operation-id", "start-image"))
    assert first.exit_code == 4, first.output
    run_id = json.loads(first.stdout)["data"]["run"]["run_id"]
    assert len(calls) == 1
    initial_body = calls[0].content
    if dimension == 1024:
        assert len(initial_body) > 2 * 1024 * 1024
    assert b"expected" not in initial_body and b"OFFLINE_SENTINEL" not in initial_body
    shutil.rmtree(root)
    resumed_preview = invoke(source, "runs", "resume", run_id, "--dry-run")
    assert resumed_preview.exit_code == 0, resumed_preview.output
    assert json.loads(resumed_preview.stdout)["data"]["planned_case_ids"] == []
    resumed = invoke(
        source, "runs", "resume", run_id, "--retry-unknown", "--operation-id", "resume-image"
    )
    assert resumed.exit_code == 0, resumed.output
    assert len(calls) == 2 and calls[1].content == initial_body
    replayed = invoke(
        source, "runs", "resume", run_id, "--retry-unknown", "--operation-id", "resume-image"
    )
    assert replayed.exit_code == 0 and len(calls) == 2
    result = invoke(source, "results", "show", run_id, "product", "--request", "--attempts")
    assert result.exit_code == 0, result.output
    attempts = json.loads(result.stdout)["data"]["attempts"]
    assert len(attempts) == 2
    for attempt in attempts:
        assert json.loads(attempt["request_body_source"]) == json.loads(initial_body)
        assert attempt["request_semantic_headers_source"] == IMAGE_HEADERS_SOURCE
    assert "OFFLINE_SENTINEL" not in result.stdout
    labels = invoke(
        source, "label", "show", "product", "--decision", "decision", "--dataset", "data"
    )
    assert labels.exit_code == 0, labels.output
    assert "imported_unknown" in labels.stdout
    assert invoke(source, "project", "validate").exit_code == 0


def test_provider_dimensions_block_preview(setup, tmp_path, monkeypatch):
    source, _, _, clock, _, _ = seed_image(setup, tmp_path)
    configure(source, monkeypatch)
    service = ExecutionService(source, source, ProviderBackends(source, clock), clock)
    request = RunRequest(
        decision_id="decision", dataset_id="data", mode="live", provider_id="jev-images"
    )
    with pytest.raises(ServiceFailure) as error:
        service.preview(request)
    assert error.value.error.reason == "unsupported_request_configuration"
    assert not source.list_ids("runs")


def test_image_headers_participate_in_review_identity(setup, tmp_path):
    source, execution, factory, _, _, _ = seed_image(
        setup, tmp_path, preparation=ImagePreparation(mode="pad", min_width=280, min_height=280)
    )
    factory.compiler = JevChoiceCompiler()
    request = RunRequest(
        decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
    )
    plan = execution.planner.prepare(request)
    changed = replace(
        plan.prepared[0],
        request=plan.prepared[0].request.model_copy(update={"semantic_headers_source": "{}"}),
    )
    assert run_review_hash(replace(plan, prepared=(changed,))) != run_review_hash(plan)
    assert parse_json(plan.prepared[0].request.semantic_headers_source) == {
        "TypeSafe-Danger-Zone-Images": "true"
    }
