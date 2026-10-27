"""Classification reports over frozen evidence, without provider execution."""

import csv
import io
import json
import shutil
from dataclasses import replace

import pytest
from pydantic import ValidationError
from test_reports import MemorySnapshotSource
from typer.testing import CliRunner

from deykit.application.errors import ServiceFailure
from deykit.application.reports import ReportService
from deykit.cli.context import SystemClock
from deykit.cli.main import app
from deykit.contracts.codec import dump_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import bytes_hash, dump_json, parse_json
from deykit.contracts.ports import ResourceKey, StoredRecord
from deykit.contracts.redaction import Sanitizer
from deykit.reports.admission import report_hash
from deykit.reports.classification import classification_report, classify_evaluation
from deykit.reports.classification_render import classification_csv
from deykit.reports.models import (
    ClassificationPricing,
    ClassificationReport,
    ReportRequest,
    TokenPrice,
)
from deykit.reports.render import render_content


def test_classification_preset_freezes_and_exports_same_case_identities(fixture_graph):
    source = MemorySnapshotSource.from_records(fixture_graph.records)
    service = ReportService(source, SystemClock())
    request = ReportRequest(
        target_id=fixture_graph.comparison_id, target_kind="comparison", preset="classification"
    )
    report = service.create(request, operation_id="classification-report")
    saved = service.read(report.record.id)
    assert saved.content.classification == report.content.classification
    assert saved.content.classification.comparison_policy == "compatible_pairs_only"
    left, right = saved.content.classification.evaluations
    assert (left.selected_count, left.applicable_count, left.excluded_count) == (12, 9, 3)
    assert (
        left.full_cohort_strict_accuracy.numerator,
        left.full_cohort_strict_accuracy.denominator,
    ) == (6, 9)
    assert (
        right.full_cohort_strict_accuracy.numerator,
        right.full_cohort_strict_accuracy.denominator,
    ) == (7, 9)
    assert saved.content.comparison.quality_denominator == 8
    assert saved.content.comparison.primary_counts["improved"] == 1
    assert saved.content.comparison.primary_counts["unavailable_answer"] == 2
    assert left.applicable_status_counts.valid == 8 and left.failed_count == 1
    rows = list(
        csv.DictReader(io.StringIO(service.render(report.record.id, format="csv").body.decode()))
    )
    assert len(rows) == sum(len(e.cases) for e in report.content.evaluations)
    assert {r["report_id"] for r in rows} == {report.record.id}
    assert {r["content_hash"] for r in rows} == {report.record.content_hash}
    assert {r["evaluation_id"] for r in rows} == set(report.record.evaluation_ids)
    assert service.create(request, operation_id="classification-report").replayed
    markdown = service.render(report.record.id, format="markdown").body.decode()
    assert "Full-cohort strict accuracy" in markdown
    assert "compatible_pairs_only" in markdown


def _evaluation(graph):
    service = ReportService(MemorySnapshotSource.from_records(graph.records), SystemClock())
    return service.create(
        ReportRequest(target_id=graph.evaluation_id, target_kind="evaluation"),
        operation_id="base-report",
    ).content.evaluations[0]


def test_full_cohort_denominators_and_class_failures(fixture_graph):
    evaluation = _evaluation(fixture_graph)
    a, b = evaluation.context.option_ids[:2]
    base = evaluation.cases[0]

    def case(n, status, expected, answer=None, reasons=(), correct=None):
        return base.model_copy(
            update={
                "case_id": f"case-{n}",
                "status": status,
                "expected_option_ids": expected,
                "answer_option_id": answer,
                "exclusion_reasons": reasons,
                "correct": correct,
            }
        )

    cases = (
        case(0, "valid", (a,), a, correct=True),
        case(1, "valid", (a,), b, correct=False),
        case(2, "response_error", (a,), reasons=("no_valid_answer",)),
        case(3, "pending", (b,), reasons=("no_valid_answer",)),
        case(4, "unknown", (b,), reasons=("no_valid_answer",)),
        case(5, "input_invalid", (a,), reasons=("no_valid_answer",)),
        case(6, "valid", (), a, reasons=("unlabelled",)),
        case(7, "valid", (a,), a, reasons=("disputed",)),
        case(8, "valid", (a,), a, reasons=("stale",)),
        case(9, "valid", (a,), a, reasons=("incompatible",)),
        case(
            10,
            "valid",
            (a, b),
            b,
            reasons=("acceptable_set_excluded_from_class_metrics",),
            correct=True,
        ),
    )
    summary = classify_evaluation(
        evaluation.model_copy(update={"cases": cases}), ClassificationPricing()
    )
    assert (summary.selected_count, summary.applicable_count, summary.excluded_count) == (11, 7, 4)
    assert summary.full_cohort_strict_accuracy.numerator == 2
    assert summary.full_cohort_strict_accuracy.denominator == 7
    assert summary.valid_answer_accuracy.denominator == 3
    assert summary.failed_count == 2 and summary.missing_count == 1
    assert summary.applicable_status_counts.unknown == 1
    assert summary.refused_count == 0
    assert summary.class_count == 6
    first, second = summary.classes[:2]
    assert (first.support, first.predicted, first.true_positive) == (4, 1, 1)
    assert (first.recall.numerator, first.recall.denominator) == (1, 4)
    assert (first.f1.numerator, first.f1.denominator) == (2, 5)
    assert (second.support, second.predicted, second.true_positive) == (2, 1, 0)
    assert [item.strict_correct for item in summary.cases] == [
        True,
        False,
        False,
        False,
        False,
        False,
        None,
        None,
        None,
        None,
        True,
    ]


def test_category_only_scoring_has_explicit_cohorts_and_preserves_strict_results(fixture_graph):
    evaluation = _evaluation(fixture_graph)
    a, b = evaluation.context.option_ids[:2]
    base = evaluation.cases[0]

    def case(n, status, expected, answer=None, salvage=None, reasons=(), correct=None):
        return base.model_copy(
            update={
                "case_id": f"category-{n}",
                "status": status,
                "expected_option_ids": expected,
                "answer_question_id": evaluation.context.question_id if answer else None,
                "answer_option_id": answer,
                "category_only_option_id": salvage,
                "exclusion_reasons": reasons,
                "correct": correct,
            }
        )

    cases = (
        case(0, "valid", (a,), answer=a, correct=True),
        case(1, "valid", (a,), answer=b, correct=False),
        case(2, "response_error", (a,), salvage=a, reasons=("no_valid_answer",)),
        case(3, "response_error", (a,), salvage=b, reasons=("no_valid_answer",)),
        case(4, "response_error", (a,), reasons=("no_valid_answer",)),
        case(5, "unknown", (b,), reasons=("no_valid_answer",)),
        case(6, "response_error", (), salvage=a, reasons=("unlabelled", "no_valid_answer")),
        case(7, "response_error", (a,), salvage=a, reasons=("disputed", "no_valid_answer")),
    )
    selected = evaluation.model_copy(update={"cases": cases})
    strict = classify_evaluation(
        selected, ClassificationPricing(), policy="classification-strict-v4"
    )
    scored = classify_evaluation(
        selected, ClassificationPricing(), policy="classification-strict-v4", category_only=True
    )
    assert scored.full_cohort_strict_accuracy == strict.full_cohort_strict_accuracy
    assert scored.valid_answer_accuracy == strict.valid_answer_accuracy
    assert scored.classes == strict.classes
    assert (scored.full_cohort_strict_accuracy.numerator, scored.applicable_count) == (1, 6)
    assert (scored.category_only.salvaged_count, scored.category_only.usable_count) == (2, 4)
    assert (
        scored.category_only.full_cohort_accuracy.numerator,
        scored.category_only.full_cohort_accuracy.denominator,
    ) == (2, 6)
    assert (
        scored.category_only.usable_accuracy.numerator,
        scored.category_only.usable_accuracy.denominator,
    ) == (2, 4)
    assert [case.category_only.correct for case in scored.cases] == [
        True,
        False,
        True,
        False,
        None,
        None,
        None,
        None,
    ]
    assert strict.category_only is None

    no_usable = classify_evaluation(
        selected.model_copy(update={"cases": (cases[4], cases[6])}),
        ClassificationPricing(),
        policy="classification-strict-v4",
        category_only=True,
    )
    assert no_usable.category_only.full_cohort_accuracy.denominator == 1
    assert no_usable.category_only.usable_accuracy.reason == "no_usable_category_answers"
    no_labels = classify_evaluation(
        selected.model_copy(update={"cases": (cases[6],)}),
        ClassificationPricing(),
        policy="classification-strict-v4",
        category_only=True,
    )
    assert no_labels.category_only.full_cohort_accuracy.reason == "no_applicable_expectations"


def test_category_only_policy_is_frozen_in_operation_intent(fixture_graph):
    source = MemorySnapshotSource.from_records(fixture_graph.records)
    service = ReportService(source, SystemClock())
    request = ReportRequest(
        target_id=fixture_graph.evaluation_id, preset="classification", category_only=True
    )
    saved = service.create(request, operation_id="pin-category-policy")
    assert saved.content.classification.policy == "classification-strict-v4"
    assert saved.content.classification.category_only_scoring == "jev_probability_only_v1"
    assert (
        "selected_input_reconstructed_from_frozen_case_and_definition"
        not in saved.content.classification.treatment_limitations
    )
    assert (
        "input_hash_compares_selected_json_only"
        not in saved.content.classification.treatment_limitations
    )
    assert (
        "case_input_hash_covers_original_input_and_source_images"
        in saved.content.classification.treatment_limitations
    )
    assert not any(
        "experimental_pairs" in item for item in saved.content.classification.treatment_limitations
    )
    assert service.create(request, operation_id="pin-category-policy").replayed
    with pytest.raises(ServiceFailure) as error:
        service.create(
            request.model_copy(update={"category_only": False}), operation_id="pin-category-policy"
        )
    assert error.value.error.code == "conflict"


def test_legacy_v2_single_report_replays_and_keeps_its_original_markdown(fixture_graph):
    source = MemorySnapshotSource.from_records(fixture_graph.records)
    service = ReportService(source, SystemClock())
    request = ReportRequest(target_id=fixture_graph.evaluation_id, preset="classification")
    saved = service.create(request, operation_id="legacy-v2-single")
    parsed = parse_json(saved.record.content_source)
    for evaluation in parsed["evaluations"]:
        evaluation["context"].pop("cohort_selection", None)
        for case in evaluation["cases"]:
            case.pop("legacy_label_provenances", None)
    parsed["classification"]["policy"] = "classification-strict-v2"
    parsed["classification"]["treatment_limitations"] = list(
        ClassificationReport.model_fields["treatment_limitations"].default
    )
    record = saved.record.model_copy(update={"content_source": dump_json(parsed)})
    record = record.model_copy(update={"content_hash": report_hash(record, saved.content)})
    body = dump_record(record)
    key = ResourceKey("reports", record.id)
    legacy = StoredRecord(key, body, bytes_hash(body))
    source.records[key] = legacy
    intent, receipt = source.operations["legacy-v2-single"]
    source.operations["legacy-v2-single"] = (intent, replace(receipt, changes=(legacy,)))
    assert service.read(record.id).content.classification.policy == "classification-strict-v2"
    assert service.create(request, operation_id="legacy-v2-single").replayed
    markdown = service.render(record.id, format="markdown").body.decode()
    assert "| Case | Status | Answer | Expected | Correct | Exclusions or error |" in markdown
    assert "Original evaluation cost:" not in markdown
    assert source.records[key].body == body


def test_no_applicable_labels_is_unavailable_not_zero(fixture_graph):
    evaluation = _evaluation(fixture_graph)
    cases = tuple(case.model_copy(update={"expected_option_ids": ()}) for case in evaluation.cases)
    summary = classify_evaluation(
        evaluation.model_copy(update={"cases": cases}), ClassificationPricing()
    )
    assert summary.applicable_count == 0
    assert summary.full_cohort_strict_accuracy.value is None
    assert summary.full_cohort_strict_accuracy.reason == "no_applicable_expectations"


def test_explicit_refusals_count_only_applicable_response_failures(fixture_graph):
    evaluation = _evaluation(fixture_graph)
    base = evaluation.cases[0]
    refusal = ServiceError(code="response_invalid", reason="provider_refusal")
    cases = tuple(
        base.model_copy(
            update={
                "case_id": f"refusal-{n}",
                "status": status,
                "error": error,
                "expected_option_ids": expected,
                "exclusion_reasons": reasons,
                "correct": None,
                "answer_option_id": None,
            }
        )
        for n, (status, error, expected, reasons) in enumerate(
            (
                ("response_error", refusal, ("yes",), ("no_valid_answer",)),
                ("response_error", None, ("yes",), ("no_valid_answer",)),
                (
                    "response_error",
                    ServiceError(code="provider_rejected", reason="provider_refusal"),
                    ("yes",),
                    ("no_valid_answer",),
                ),
                ("unknown", refusal, ("yes",), ("no_valid_answer",)),
                ("input_invalid", refusal, ("yes",), ("no_valid_answer",)),
                ("response_error", refusal, (), ("unlabelled", "no_valid_answer")),
                ("response_error", refusal, ("yes",), ("disputed", "no_valid_answer")),
                ("response_error", refusal, ("yes",), ("stale", "no_valid_answer")),
                ("response_error", refusal, ("yes",), ("incompatible", "no_valid_answer")),
            )
        )
    )
    summary = classify_evaluation(
        evaluation.model_copy(update={"cases": cases}), ClassificationPricing()
    )
    assert summary.refused_count == 1
    assert summary.refusal_reason == "explicit_provider_refusals_only"
    assert summary.failed_count == 4
    assert summary.full_cohort_strict_accuracy.numerator == 0
    assert summary.full_cohort_strict_accuracy.denominator == 5


def test_saved_v1_refusal_policy_remains_readable_and_replayable(fixture_graph):
    source = MemorySnapshotSource.from_records(fixture_graph.records)
    service = ReportService(source, SystemClock())
    request = ReportRequest(target_id=fixture_graph.evaluation_id, preset="classification")
    saved = service.create(request, operation_id="legacy-refusals")
    parsed = parse_json(saved.record.content_source)
    for evaluation in parsed["evaluations"]:
        evaluation["context"].pop("cohort_selection", None)
        for case in evaluation["cases"]:
            case.pop("legacy_label_provenances", None)
    classification = parsed["classification"]
    classification["policy"] = "classification-strict-v1"
    classification["treatment_limitations"] = list(
        ClassificationReport.model_fields["treatment_limitations"].default
    )
    for evaluation in classification["evaluations"]:
        evaluation["refused_count"] = None
        evaluation["refusal_reason"] = "distinct_refusal_status_not_recorded"
    record = saved.record.model_copy(update={"content_source": dump_json(parsed)})
    record = record.model_copy(update={"content_hash": report_hash(record, saved.content)})
    body = dump_record(record)
    key = ResourceKey("reports", record.id)
    legacy = StoredRecord(key, body, bytes_hash(body))
    source.records[key] = legacy
    # Preserve the original operation's durable receipt as an old writer would.
    intent, receipt = source.operations["legacy-refusals"]
    source.operations["legacy-refusals"] = (intent, replace(receipt, changes=(legacy,)))
    read = service.read(record.id)
    assert read.content.classification.policy == "classification-strict-v1"
    assert read.content.classification.evaluations[0].refused_count is None
    assert service.create(request, operation_id="legacy-refusals").replayed
    assert source.records[key].body == body
    assert "refused unavailable" in service.render(record.id, format="markdown").body.decode()
    csv_body = service.render(record.id, format="csv").body.decode()
    assert "explicit_refusal" not in next(csv.reader(io.StringIO(csv_body)))


def _price(evaluation, **overrides):
    return TokenPrice(
        **{
            "adapter": evaluation.context.adapter,
            "requested_model": evaluation.context.requested_model,
            "currency": "USD",
            "input_per_million": "1.25",
            "output_per_million": "5",
            "source": "authored test price",
            "as_of": "2026-10-20T00:00:00Z",
            **overrides,
        }
    )


@pytest.mark.parametrize("complete", [True, False])
def test_frozen_token_list_cost_preserves_partial_usage_and_retries(fixture_graph, complete):
    evaluation = _evaluation(fixture_graph)
    usage = evaluation.metrics.usage.model_copy(
        update={
            "mode": "live",
            "dispatched_attempt_count": 3,
            "reported_attempt_count": 3 if complete else 2,
            "reported_input_tokens": 1000,
            "reported_output_tokens": 200,
            "total_input_tokens": 1000 if complete else None,
            "total_output_tokens": 200 if complete else None,
        }
    )
    live = evaluation.model_copy(
        update={
            "context": evaluation.context.model_copy(update={"evidence_mode": "live"}),
            "metrics": evaluation.metrics.model_copy(update={"usage": usage}),
        }
    )
    pricing = ClassificationPricing(rates=(_price(evaluation),))
    cost = classify_evaluation(live, pricing).cost
    assert cost.reported_subtotal == "0.00225"
    assert cost.total == ("0.00225" if complete else None)
    assert cost.unknown_attempt_count == (0 if complete else 1)
    assert cost.reason == (None if complete else "partial_reported_usage")
    assert classify_evaluation(live, ClassificationPricing()).cost.total is None
    assert classify_evaluation(evaluation, pricing).cost.reason == "fixture_no_usage"


def test_markdown_distinguishes_original_evaluation_cost_from_frozen_estimate(fixture_graph):
    service = ReportService(MemorySnapshotSource.from_records(fixture_graph.records), SystemClock())
    report = service.create(
        ReportRequest(target_id=fixture_graph.evaluation_id, preset="classification"),
        operation_id="priced-markdown",
    )
    evaluation = report.content.evaluations[0]
    usage = evaluation.metrics.usage.model_copy(
        update={
            "mode": "live",
            "dispatched_attempt_count": 1,
            "reported_attempt_count": 1,
            "reported_input_tokens": 1000,
            "reported_output_tokens": 200,
            "total_input_tokens": 1000,
            "total_output_tokens": 200,
        }
    )
    live = evaluation.model_copy(
        update={
            "context": evaluation.context.model_copy(update={"evidence_mode": "live"}),
            "metrics": evaluation.metrics.model_copy(update={"usage": usage}),
        }
    )
    summary = classification_report(
        (live,), ClassificationPricing(rates=(_price(live),)), policy="classification-strict-v4"
    )
    content = report.content.model_copy(update={"evaluations": (live,), "classification": summary})
    markdown = render_content(report.record, content, "markdown").body.decode()
    assert "total: 0.00225" in markdown
    assert "Original evaluation cost: unavailable" in markdown
    assert "See the token-list estimate" in markdown
    assert "\n- Cost: unavailable (pricing_source_unavailable)" not in markdown


@pytest.mark.parametrize("value", [1.25, "NaN", "-1", "1e2", "0.0000000000001"])
def test_token_prices_require_bounded_exact_decimal_strings(fixture_graph, value):
    with pytest.raises(ValidationError):
        _price(_evaluation(fixture_graph), input_per_million=value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("applicable_count", 99),
        ("refused_count", 99),
        ("refusal_reason", "distinct_refusal_status_not_recorded"),
    ],
)
def test_classification_is_recomputed_on_admission_and_prices_pin_replay(
    fixture_graph, field, value
):
    source = MemorySnapshotSource.from_records(fixture_graph.records)
    service = ReportService(source, SystemClock())
    pricing = ClassificationPricing(rates=(_price(_evaluation(fixture_graph)),))
    request = ReportRequest(
        target_id=fixture_graph.evaluation_id, preset="classification", pricing=pricing
    )
    saved = service.create(request, operation_id="pin-prices")
    with pytest.raises(ServiceFailure):
        service.create(
            request.model_copy(update={"pricing": ClassificationPricing()}),
            operation_id="pin-prices",
        )
    classification = saved.content.classification
    bad = classification.evaluations[0].model_copy(update={field: value})
    content = saved.content.model_copy(
        update={"classification": classification.model_copy(update={"evaluations": (bad,)})}
    )
    record = saved.record.model_copy(update={"content_source": content.model_dump_json()})
    record = record.model_copy(update={"content_hash": report_hash(record, content)})
    body = dump_record(record)
    key = ResourceKey("reports", record.id)
    source.records[key] = StoredRecord(key, body, bytes_hash(body))
    with pytest.raises(ServiceFailure) as error:
        service.read(record.id)
    assert error.value.error.reason == "report_classification_mismatch"


def test_legacy_reports_remain_readable_without_preset_field(fixture_graph):
    source = MemorySnapshotSource.from_records(fixture_graph.records)
    service = ReportService(source, SystemClock())
    saved = service.create(
        ReportRequest(target_id=fixture_graph.evaluation_id), operation_id="legacy"
    )
    parsed = parse_json(saved.record.content_source)
    del parsed["classification"]
    record = saved.record.model_copy(update={"content_source": dump_json(parsed)})
    record = record.model_copy(update={"content_hash": report_hash(record, saved.content)})
    body = dump_record(record)
    key = ResourceKey("reports", record.id)
    source.records[key] = StoredRecord(key, body, bytes_hash(body))
    assert service.read(record.id).content.classification is None
    with pytest.raises(ServiceFailure) as error:
        service.render(record.id, format="csv")
    assert error.value.error.reason == "csv_requires_classification"


def test_cli_classification_exports_frozen_identity_in_all_formats(fixture_graph, tmp_path):
    project = tmp_path / "project"
    shutil.copytree(fixture_graph.root, project)
    pricing = tmp_path / "prices.json"
    pricing.write_text(
        ClassificationPricing(rates=(_price(_evaluation(fixture_graph)),)).model_dump_json()
    )
    runner = CliRunner()
    base = ["--project", str(project), "--json", "report", "export"]
    result = runner.invoke(
        app,
        [
            *base,
            fixture_graph.comparison_id,
            "--preset",
            "classification",
            "--pricing",
            str(pricing),
            "--format",
            "csv",
            "--output",
            str(tmp_path / "cases.csv"),
            "--operation-id",
            "cli-classification",
        ],
    )
    assert result.exit_code == 0, result.output
    report_id = json.loads(result.stdout)["data"]["report"]["report_id"]
    for format_name in ("json", "markdown"):
        destination = tmp_path / f"report.{format_name}"
        result = runner.invoke(
            app,
            [
                *base,
                "--report-id",
                report_id,
                "--format",
                format_name,
                "--output",
                str(destination),
            ],
        )
        assert result.exit_code == 0, result.output
        if format_name == "json":
            exported = json.loads(destination.read_text())
            assert exported["report_id"] == report_id
            assert (
                exported["content"]["classification"]["pricing"]["rates"][0]["input_per_million"]
                == "1.25"
            )
    rows = list(csv.DictReader(io.StringIO((tmp_path / "cases.csv").read_text())))
    assert {row["report_id"] for row in rows} == {report_id}
    assert {row["comparison_bucket"] for row in rows} >= {"both_correct", "improved"}


def test_invalid_answer_is_a_class_false_negative(fixture_graph):
    evaluation = _evaluation(fixture_graph)
    option = evaluation.context.option_ids[0]
    case = evaluation.cases[0].model_copy(
        update={
            "status": "valid",
            "answer_option_id": option,
            "expected_option_ids": (option,),
            "correct": None,
            "exclusion_reasons": ("incompatible_answer",),
        }
    )
    summary = classify_evaluation(
        evaluation.model_copy(update={"cases": (case,)}), ClassificationPricing()
    )
    assert summary.full_cohort_strict_accuracy.numerator == 0
    assert summary.full_cohort_strict_accuracy.denominator == 1
    assert (
        summary.classes[0].support,
        summary.classes[0].predicted,
        summary.classes[0].true_positive,
    ) == (1, 0, 0)
    scored = classify_evaluation(
        evaluation.model_copy(update={"cases": (case,)}),
        ClassificationPricing(),
        policy="classification-strict-v4",
        category_only=True,
    )
    assert scored.cases[0].category_only.source == "unavailable"
    assert scored.category_only.usable_count == 0


def test_cost_does_not_round_large_exact_token_counts(fixture_graph):
    evaluation = _evaluation(fixture_graph)
    usage = evaluation.metrics.usage.model_copy(
        update={
            "mode": "live",
            "dispatched_attempt_count": 1,
            "reported_attempt_count": 1,
            "reported_input_tokens": 10**40 + 1,
            "reported_output_tokens": 0,
            "total_input_tokens": 10**40 + 1,
            "total_output_tokens": 0,
        }
    )
    live = evaluation.model_copy(
        update={
            "context": evaluation.context.model_copy(update={"evidence_mode": "live"}),
            "metrics": evaluation.metrics.model_copy(update={"usage": usage}),
        }
    )
    price = _price(evaluation, input_per_million="0.000000000001")
    assert classify_evaluation(live, ClassificationPricing(rates=(price,))).cost.total == (
        "10000000000000000000000.000000000000000001"
    )


def test_prices_reject_duplicates_and_sensitive_attribution(fixture_graph):
    evaluation = _evaluation(fixture_graph)
    price = _price(evaluation)
    with pytest.raises(ValidationError):
        ClassificationPricing(rates=(price, price))
    source = MemorySnapshotSource.from_records(fixture_graph.records)
    service = ReportService(source, SystemClock(), sanitizer=Sanitizer(("sensitive-attribution",)))
    with pytest.raises(ServiceFailure) as error:
        service.create(
            ReportRequest(
                target_id=fixture_graph.evaluation_id,
                preset="classification",
                pricing=ClassificationPricing(
                    rates=(_price(evaluation, source="sensitive-attribution"),)
                ),
            ),
            operation_id="sensitive-price",
        )
    assert error.value.error.reason == "report_sensitive_identity"
    assert source.commit_calls == 0


def test_csv_escapes_formula_cells_and_omits_raw_data(fixture_graph):
    service = ReportService(MemorySnapshotSource.from_records(fixture_graph.records), SystemClock())
    saved = service.create(
        ReportRequest(target_id=fixture_graph.evaluation_id, preset="classification"),
        operation_id="csv-escaping",
    )
    evaluation = saved.content.evaluations[0]
    case = evaluation.cases[0].model_copy(update={"label_provenance": " \t=HYPERLINK(1)"})
    evaluation = evaluation.model_copy(update={"cases": (case, *evaluation.cases[1:])})
    content = saved.content.model_copy(update={"evaluations": (evaluation,)})
    rows = list(csv.DictReader(io.StringIO(classification_csv(saved.record, content).decode())))
    assert rows[0]["label_provenance"] == "' \t=HYPERLINK(1)"
    assert "raw_input" not in rows[0] and "raw_response" not in rows[0]


@pytest.mark.parametrize(
    "extra",
    [
        ["--preset", "other"],
        ["--pricing", "missing.json"],
        ["--category-only"],
        ["--preset", "classification", "--target-kind", "diagnostic"],
        ["--report-id", "saved-report", "--preset", "classification"],
    ],
)
def test_invalid_preset_cli_requests_do_not_create_a_project(tmp_path, extra):
    project = tmp_path / "missing-project"
    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(project),
            "--json",
            "report",
            "export",
            "target",
            "--output",
            str(tmp_path / "out.csv"),
            *extra,
        ],
    )
    assert result.exit_code == 2, result.output
    assert not project.exists()
