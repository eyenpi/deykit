"""Standard CLI/runner behavior with an authored OpenAI HTTP exchange."""

import csv
import json
import shutil

import httpx
import pytest
from test_cli_execution import invoke
from test_image_execution import seed_image

from deykit.application.evaluations import EvaluationService
from deykit.application.labels import LabelService
from deykit.contracts.images import ImagePreparation
from deykit.providers.http import OneShotHttp


def configure(source, monkeypatch):
    monkeypatch.setenv("OFFLINE_OPENAI_KEY", "OFFLINE_SENTINEL")
    result = invoke(
        source,
        "provider",
        "configure",
        "openai-main",
        "--adapter",
        "openai",
        "--model",
        "gpt-6-luna",
        "--credential-env",
        "OFFLINE_OPENAI_KEY",
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]["profile"]
    assert data["compiler"] == {"id": "openai-decisions-choice", "version": "1"}
    assert data["capabilities"]["max_options"] == 255


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
        "openai-main",
        "--attempt-limit",
        "4",
        "--concurrency",
        "1",
        "--rate-retries",
        "0",
        *extra,
    )


def response(answer_type="choice"):
    answer = {"name": "q", "type": answer_type}
    if answer_type == "choice":
        answer.update(
            choice="yes",
            confidence=1,
            probabilities=[
                {"value": "yes", "probability": 1},
                {"value": "no", "probability": 0},
            ],
        )
    return {
        "model": "gpt-6-luna",
        "answers": [answer],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 0,
            "total_tokens": 100,
            "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


def test_openai_profile_and_credentials_are_local(setup, monkeypatch):
    source, *_ = setup(1)
    configure(source, monkeypatch)
    linked = invoke(source, "credential", "set", "--provider", "openai-main", "--env", "NEW_KEY")
    assert linked.exit_code == 0, linked.output
    assert "env:NEW_KEY" in linked.stdout
    forgotten = invoke(source, "credential", "forget", "--provider", "openai-main")
    assert forgotten.exit_code == 0, forgotten.output
    assert invoke(source, "doctor").exit_code == 0


@pytest.mark.parametrize("images", [0, 2, 1024])
def test_openai_preview_unknown_resume_replay_and_report(setup, tmp_path, monkeypatch, images):
    if images:
        source, _, _, _, root, _ = seed_image(
            setup,
            tmp_path,
            preparation=ImagePreparation(mode="pad", min_width=images, min_height=images),
        )
        case_id = "product"
    else:
        source, *_ = setup(1)
        root, case_id = None, "case-00"
    configure(source, monkeypatch)
    calls = []

    def handle(request):
        calls.append(request)
        assert str(request.url) == "https://api.openai.com/v1/decisions"
        assert "TypeSafe-Danger-Zone-Images" not in request.headers
        if len(calls) == 1:
            raise httpx.ReadTimeout("authored unknown outcome")
        return httpx.Response(200, json=response())

    monkeypatch.setattr(
        "deykit.providers.openai_decisions.OneShotHttp",
        lambda: OneShotHttp(httpx.MockTransport(handle)),
    )
    preview = invoke(source, *run_args("--dry-run"))
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.stdout)["data"]["initial_requests"] == 1
    assert not calls and not source.list_ids("runs")
    first = invoke(source, *run_args("--operation-id", "start-openai"))
    assert first.exit_code == 4, first.output
    run_id = json.loads(first.stdout)["data"]["run"]["run_id"]
    assert len(calls) == 1
    body = calls[0].content
    assert b"OFFLINE_SENTINEL" not in body and b"expected" not in body
    if images:
        assert b"data:image/png;base64," in body
        if images == 1024:
            assert len(body) > 2 * 1024 * 1024
        shutil.rmtree(root)
    resume_preview = invoke(source, "runs", "resume", run_id, "--dry-run")
    assert resume_preview.exit_code == 0, resume_preview.output
    assert json.loads(resume_preview.stdout)["data"]["planned_case_ids"] == []
    resumed = invoke(
        source, "runs", "resume", run_id, "--retry-unknown", "--operation-id", "resume-openai"
    )
    assert resumed.exit_code == 0, resumed.output
    assert len(calls) == 2 and calls[1].content == body
    replay = invoke(
        source, "runs", "resume", run_id, "--retry-unknown", "--operation-id", "resume-openai"
    )
    assert replay.exit_code == 0 and len(calls) == 2
    result = invoke(source, "results", "show", run_id, case_id, "--request", "--attempts")
    assert result.exit_code == 0, result.output
    attempts = json.loads(result.stdout)["data"]["attempts"]
    assert len(attempts) == 2 and attempts[1]["request_body_source"] == body.decode()
    destination = tmp_path / "openai-report.json"
    report = invoke(
        source,
        "report",
        "export",
        run_id,
        "--target-kind",
        "run",
        "--preset",
        "classification",
        "--include-raw-requests",
        "--format",
        "json",
        "--output",
        str(destination),
    )
    assert report.exit_code == 0, report.output
    assert "openai" in destination.read_text() and "gpt-6-luna" in destination.read_text()
    assert len(calls) == 2
    assert invoke(source, "project", "validate").exit_code == 0


def test_refusal_is_final_retains_usage_and_does_not_stop_other_cases(setup, monkeypatch, tmp_path):
    source, _, _, clock = setup(2)
    configure(source, monkeypatch)
    labels = LabelService(source, clock)
    for case_id in ("case-00", "case-01"):
        labels.set(
            labels.read("decision", "data", case_id).review,
            ("yes",),
            provenance="model_generated",
            operation_id=f"label-{case_id}",
        )
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=response("refusal" if len(calls) == 1 else "choice"))

    monkeypatch.setattr(
        "deykit.providers.openai_decisions.OneShotHttp",
        lambda: OneShotHttp(httpx.MockTransport(handle)),
    )
    result = invoke(source, *run_args("--operation-id", "refusal-run"))
    assert result.exit_code == 3, result.output
    run = json.loads(result.stdout)["data"]["run"]
    assert [case["status"] for case in run["cases"]] == ["response_error", "valid"]
    assert run["cases"][0]["error"]["reason"] == "provider_refusal"
    shown = invoke(source, "results", "show", run["run_id"], "case-00", "--attempts", "--response")
    attempt = json.loads(shown.stdout)["data"]["attempts"][0]
    assert json.loads(attempt["response_source"])["answers"][0]["type"] == "refusal"
    evaluation = EvaluationService(source, clock).read(
        json.loads(result.stdout)["data"]["evaluation_id"]
    )
    assert evaluation.metrics["usage"]["total_input_tokens"] == 200
    assert evaluation.metrics["usage"]["reported_attempt_count"] == 2
    assert len(calls) == 2
    destination = tmp_path / "refusals.json"
    exported = invoke(
        source,
        "report",
        "export",
        run["run_id"],
        "--target-kind",
        "run",
        "--preset",
        "classification",
        "--output",
        str(destination),
        "--format",
        "json",
        "--operation-id",
        "refusal-report",
    )
    assert exported.exit_code == 0, exported.output
    saved = json.loads(destination.read_text())
    classification = saved["content"]["classification"]
    assert classification["policy"] == "classification-strict-v4"
    summary = classification["evaluations"][0]
    assert summary["refused_count"] == summary["failed_count"] == 1
    assert summary["full_cohort_strict_accuracy"]["numerator"] == 1
    assert summary["full_cohort_strict_accuracy"]["denominator"] == 2
    report_id = saved["report_id"]
    for format_name in ("markdown", "csv"):
        path = tmp_path / f"refusals.{format_name}"
        result = invoke(
            source,
            "report",
            "export",
            "--report-id",
            report_id,
            "--format",
            format_name,
            "--output",
            str(path),
        )
        assert result.exit_code == 0, result.output
        if format_name == "markdown":
            assert "explicit refusals 1" in path.read_text()
        else:
            with path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            assert [row["explicit_refusal"] for row in rows] == ["true", "false"]
            assert {row["refused_count"] for row in rows} == {"1"}
            assert {row["refusal_reason"] for row in rows} == {"explicit_provider_refusals_only"}
    assert invoke(source, "project", "validate").exit_code == 0
    assert len(calls) == 2


def test_openai_cancel_resume_and_retry_share_the_lifetime_attempt_limit(setup, monkeypatch):
    import asyncio

    from deykit.application.execution import ExecutionService
    from deykit.contracts.records import ExecutionSettings
    from deykit.runner.backends import ProviderBackends
    from deykit.runner.planner import RunRequest

    source, _, _, clock = setup(2)
    configure(source, monkeypatch)
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=response())

    monkeypatch.setattr(
        "deykit.providers.openai_decisions.OneShotHttp",
        lambda: OneShotHttp(httpx.MockTransport(handle)),
    )
    service = ExecutionService(source, source, ProviderBackends(source, clock), clock)
    request = RunRequest(
        decision_id="decision",
        dataset_id="data",
        mode="live",
        provider_id="openai-main",
        settings=ExecutionSettings(max_attempts=2, concurrency=1),
    )
    stopped = asyncio.run(
        service.start(
            request,
            operation_id="cancel-before-dispatch",
            on_created=lambda created: service.cancel(created.run_id, operation_id="cancel"),
        )
    )
    assert stopped.state == "cancelled" and stopped.attempts_used == 0 and not calls
    resumed = asyncio.run(service.resume(stopped.run_id, operation_id="resume-cancelled"))
    assert len(calls) == resumed.attempts_used == 2
    assert resumed.state == "budget_exhausted" and resumed.attempts_remaining == 0
    assert resumed.exit_code == 4
    replay = asyncio.run(service.resume(stopped.run_id, operation_id="resume-cancelled"))
    assert replay.replayed and len(calls) == 2


def test_openai_diagnostic_and_regression_groups_are_readable_replayable_and_reportable(
    setup,
    tmp_path,
    monkeypatch,
):
    source, *_ = setup(1)
    configure(source, monkeypatch)
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=response())

    monkeypatch.setattr(
        "deykit.providers.openai_decisions.OneShotHttp",
        lambda: OneShotHttp(httpx.MockTransport(handle)),
    )
    arguments = (
        "diagnose",
        "choice-order",
        "--decision",
        "decision",
        "--dataset",
        "data",
        "--mode",
        "live",
        "--provider",
        "openai-main",
        "--orders",
        "2",
        "--attempt-limit",
        "2",
        "--concurrency",
        "1",
        "--rate-retries",
        "0",
    )
    preview = invoke(source, *arguments, "--dry-run")
    assert preview.exit_code == 0 and not calls, preview.output
    first = invoke(source, *arguments, "--operation-id", "openai-diagnostic")
    assert first.exit_code == 0, first.output
    data = json.loads(first.stdout)["data"]
    group_id = data["group"]["group_id"]
    assert len(calls) == 2
    assert [
        choice["value"] for choice in json.loads(calls[0].content)["questions"][0]["choices"]
    ] == ["yes", "no"]
    assert [
        choice["value"] for choice in json.loads(calls[1].content)["questions"][0]["choices"]
    ] == ["no", "yes"]
    assert invoke(source, "diagnose", "show", group_id).exit_code == 0
    replay = invoke(source, *arguments, "--operation-id", "openai-diagnostic")
    assert replay.exit_code == 0 and len(calls) == 2, replay.output
    resumed = invoke(source, "diagnose", "resume", group_id, "--operation-id", "diagnostic-resume")
    assert resumed.exit_code == 0 and len(calls) == 2, resumed.output
    report = invoke(
        source,
        "report",
        "export",
        group_id,
        "--target-kind",
        "diagnostic",
        "--format",
        "json",
        "--output",
        str(tmp_path / "diagnostic.json"),
    )
    assert report.exit_code == 0 and len(calls) == 2, report.output
    run_id = data["group"]["members"][0]["run_id"]
    added = invoke(
        source,
        "regression",
        "add",
        run_id,
        "case-00",
        "--expected",
        "yes",
        "--reason",
        "Authored expected result",
        "--provenance",
        "model_generated",
        "--operation-id",
        "openai-regression",
    )
    assert added.exit_code == 0, added.output
    check_args = (
        "check",
        "--decision",
        "decision",
        "--mode",
        "live",
        "--provider",
        "openai-main",
        "--attempt-limit",
        "1",
        "--concurrency",
        "1",
        "--rate-retries",
        "0",
    )
    checked = invoke(source, *check_args, "--operation-id", "openai-check")
    assert checked.exit_code == 0 and len(calls) == 3, checked.output
    check_id = json.loads(checked.stdout)["data"]["group"]["group_id"]
    assert invoke(source, "checks", "show", check_id).exit_code == 0
    replay = invoke(source, *check_args, "--operation-id", "openai-check")
    assert replay.exit_code == 0 and len(calls) == 3, replay.output
    exported = invoke(
        source,
        "report",
        "export",
        check_id,
        "--target-kind",
        "check",
        "--output",
        str(tmp_path / "check.json"),
    )
    assert exported.exit_code == 0 and len(calls) == 3, exported.output
    assert invoke(source, "project", "validate").exit_code == 0


def test_malformed_response_evidence_survives_inspection_and_report(setup, tmp_path, monkeypatch):
    source, *_ = setup(1)
    configure(source, monkeypatch)
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, content=b'{"answer":"OFFLINE_SENTINEL')

    monkeypatch.setattr(
        "deykit.providers.openai_decisions.OneShotHttp",
        lambda: OneShotHttp(httpx.MockTransport(handle)),
    )
    completed = invoke(source, *run_args("--operation-id", "malformed-openai"))
    assert completed.exit_code == 3, completed.output
    run_id = json.loads(completed.stdout)["data"]["run"]["run_id"]
    shown = invoke(source, "results", "show", run_id, "case-00", "--attempts", "--response")
    assert shown.exit_code == 0, shown.output
    raw = json.loads(shown.stdout)["data"]["attempts"][0]["response_source"]
    evidence = json.loads(raw)["deykit_unparsed_response"]
    assert evidence["body"] == '{"answer":"[REDACTED]'
    destination = tmp_path / "malformed-report.json"
    exported = invoke(
        source,
        "report",
        "export",
        run_id,
        "--target-kind",
        "run",
        "--format",
        "json",
        "--include-raw-responses",
        "--output",
        str(destination),
    )
    assert exported.exit_code == 0, exported.output
    material = json.loads(destination.read_text())["content"]["raw_material"]
    assert len(material) == 1 and material[0]["category"] == "response"
    assert json.loads(material[0]["source"]) == json.loads(raw)
    assert len(calls) == 1 and "OFFLINE_SENTINEL" not in destination.read_text()


def test_malformed_response_obeys_additional_report_redaction(setup, monkeypatch):
    from deykit.application.errors import ServiceFailure
    from deykit.application.reports import ReportService
    from deykit.cli.context import SystemClock
    from deykit.contracts.redaction import Sanitizer
    from deykit.reports.models import RawChoices, ReportRequest

    source, *_ = setup(1)
    configure(source, monkeypatch)
    monkeypatch.setattr(
        "deykit.providers.openai_decisions.OneShotHttp",
        lambda: OneShotHttp(
            httpx.MockTransport(
                lambda req: httpx.Response(
                    200, content=rb'{"broken":"additional-\u0070rivate-value'
                )
            )
        ),
    )
    completed = invoke(source, *run_args("--operation-id", "malformed-report-redaction"))
    assert completed.exit_code == 3, completed.output
    run_id = json.loads(completed.stdout)["data"]["run"]["run_id"]
    request = ReportRequest(target_id=run_id, target_kind="run", raw=RawChoices(responses=True))
    saved = ReportService(source, SystemClock()).create(request, operation_id="before-redaction")
    strict = ReportService(
        source, SystemClock(), sanitizer=Sanitizer(("additional-private-value",))
    )
    with pytest.raises(ServiceFailure) as failure:
        strict.read(saved.record.id)
    assert failure.value.error.reason == "report_redaction_context_mismatch"
    with pytest.raises(ServiceFailure) as failure:
        strict.create(request, operation_id="before-redaction")
    assert failure.value.error.reason == "report_redaction_context_mismatch"
    redacted = strict.create(request, operation_id="after-redaction")
    raw = redacted.content.raw_material[0]
    assert raw.changed_by_redaction
    assert "[REDACTED]" in json.loads(raw.source)["deykit_unparsed_response"]["body"]
    assert "additional-private-value" not in raw.source
