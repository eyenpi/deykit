"""Experimental comparisons use frozen evidence and keep strict pairs separate."""

import csv
import io
import json
import shutil
from dataclasses import replace

import pytest
from test_reports import MemorySnapshotSource
from typer.testing import CliRunner

from deykit.application.errors import ServiceFailure
from deykit.application.reports import ReportService
from deykit.cli.context import SystemClock
from deykit.cli.main import app
from deykit.comparisons.models import ComparisonCaseSide
from deykit.comparisons.pairing import pair_cases
from deykit.contracts.codec import dump_record
from deykit.contracts.images import (
    ImageIdentity,
    ImageInfo,
    ImagePreparation,
    SelectedImage,
    image_asset_id,
)
from deykit.contracts.json_value import bytes_hash, dump_json, parse_json
from deykit.contracts.ports import ResourceKey, StoredRecord
from deykit.contracts.redaction import Sanitizer
from deykit.reports.admission import report_hash
from deykit.reports.classification import classification_report
from deykit.reports.classification_render import classification_csv
from deykit.reports.experimental_pairs import experimental_comparison
from deykit.reports.models import ClassificationPricing, ClassificationReport, ReportRequest
from deykit.reports.projection import safe_comparison_outcomes


def test_classification_comparison_includes_auditable_experimental_pairs(fixture_graph):
    source = MemorySnapshotSource.from_records(fixture_graph.records)
    service = ReportService(source, SystemClock())
    request = ReportRequest(
        target_id=fixture_graph.comparison_id, target_kind="comparison", preset="classification"
    )
    report = service.create(request, operation_id="experimental-pairs")
    classification = report.content.classification
    assert classification.policy == "classification-strict-v4"
    experimental = classification.experimental_comparison
    assert experimental.policy == "matching_labels_allow_changed_inputs_v1"
    assert experimental.selected_input_comparison == "reconstructed_selection_v1"
    assert "input_hash_compares_selected_json_only" not in classification.treatment_limitations
    assert experimental.quality_denominator == 8
    assert experimental.counts["improved"] == 1
    assert experimental.counts["unavailable_answer"] == 2
    assert experimental.counts["excluded_expectation"] == 2
    assert report.content.comparison.quality_denominator == 8
    assert service.read(report.record.id).content == report.content
    assert service.create(request, operation_id="experimental-pairs").replayed

    markdown = service.render(report.record.id, format="markdown").body.decode()
    assert "Experimental paired comparison" in markdown
    assert "matching_labels_allow_changed_inputs_v1" in markdown
    rows = list(
        csv.DictReader(io.StringIO(service.render(report.record.id, format="csv").body.decode()))
    )
    assert len(rows) == 24
    assert all(row["experimental_pair_bucket"] for row in rows)
    assert {row["experimental_quality_denominator"] for row in rows} == {"8"}
    assert {row["selected_input_comparison"] for row in rows} == {"reconstructed_selection_v1"}
    assert {row["definition_changed"] for row in rows} == {"false"}
    assert sum(row["experimental_pair_row"] == "true" for row in rows) == 12
    assert (
        sum(
            row["experimental_pair_row"] == "true" and row["experimental_pair_bucket"] == "improved"
            for row in rows
        )
        == 1
    )


def _image(source_hash, *, padded=False):
    source = ImageInfo(
        content_hash=source_hash * 64,
        byte_count=10,
        width=10,
        height=10,
        format="PNG",
        mode="RGB",
    )
    prepared = (
        source.model_copy(update={"content_hash": "f" * 64, "width": 12, "height": 12})
        if padded
        else source
    )
    preparation = (
        ImagePreparation(mode="pad", min_width=12, min_height=12) if padded else ImagePreparation()
    )
    asset = ImageIdentity(
        id=image_asset_id(source, prepared, preparation),
        source=source,
        prepared=prepared,
        preparation=preparation,
    )
    return SelectedImage(name="photo", asset=asset)


def _changed_evidence(fixture_graph):
    source = MemorySnapshotSource.from_records(fixture_graph.records)
    report = (
        ReportService(source, SystemClock())
        .create(
            ReportRequest(target_id=fixture_graph.comparison_id, preset="classification"),
            operation_id="treatment-base",
        )
        .content
    )
    original = report.comparison
    option_a, option_b = original.left.option_ids[:2]
    original_image = _image("1")
    padded_image = _image("1", padded=True)
    different_image = _image("2")

    def side(
        *,
        expected=None,
        answer=None,
        correct=True,
        input_hash="a",
        request_hash="c",
        status="valid",
        reasons=(),
        image_hash=None,
    ):
        return ComparisonCaseSide(
            input_hash=input_hash * 64,
            image_treatment_hash=None if image_hash is None else image_hash * 64,
            request_hash=None if request_hash is None else request_hash * 64,
            status=status,
            answer_option_id=option_a if answer is None and status == "valid" else answer,
            expected_option_ids=(option_a,) if expected is None else expected,
            label_provenance="model_generated",
            exclusion_reasons=reasons,
            correct=correct,
        )

    both = side()
    wrong = side(answer=option_b, correct=False)
    changed_label = side(expected=(option_b,), answer=option_b)
    disputed = side(correct=None, reasons=("disputed",))
    missing = side(
        status="response_error", correct=None, request_hash=None, reasons=("no_valid_answer",)
    )
    cases = {
        "same": (both, both, (), ()),
        "changed-input": (wrong, side(input_hash="b", request_hash="d"), (), ()),
        "image-added": (
            both,
            side(answer=option_b, correct=False, image_hash="1"),
            (),
            (original_image,),
        ),
        "image-padded": (
            side(answer=option_b, correct=False, image_hash="1"),
            side(answer=option_b, correct=False, image_hash="2"),
            (original_image,),
            (padded_image,),
        ),
        "changed-label": (both, changed_label, (), ()),
        "missing": (both, missing, (), ()),
        "disputed": (disputed, disputed, (), ()),
        "input-and-label": (
            both,
            side(expected=(option_b,), answer=option_b, input_hash="b"),
            (),
            (),
        ),
        "image-source": (
            side(image_hash="1"),
            side(input_hash="b", image_hash="3"),
            (original_image,),
            (different_image,),
        ),
        "left-only": (both, None, (), ()),
        "right-only": (None, both, (), ()),
    }
    left_sides = {name: values[0] for name, values in cases.items() if values[0] is not None}
    right_sides = {name: values[1] for name, values in cases.items() if values[1] is not None}
    left_context = original.left.model_copy(update={"selected_case_ids": tuple(left_sides)})
    right_context = original.right.model_copy(
        update={"selected_case_ids": tuple(right_sides), "definition_hash": "e" * 64}
    )
    comparison = pair_cases(left_context, right_context, left_sides, right_sides)
    evaluations = []
    for index, sides in enumerate((left_sides, right_sides)):
        evaluation = report.evaluations[index]
        report_cases = tuple(
            evaluation.cases[0].model_copy(
                update={
                    "case_id": name,
                    "input_hash": values.input_hash,
                    "selected_images": cases[name][index + 2],
                    "status": values.status,
                    "answer_option_id": values.answer_option_id,
                    "expected_option_ids": values.expected_option_ids,
                    "correct": values.correct,
                    "exclusion_reasons": values.exclusion_reasons,
                }
            )
            for name, values in sides.items()
        )
        evaluations.append(
            evaluation.model_copy(
                update={
                    "context": evaluation.context.model_copy(
                        update={"selected_case_ids": tuple(sides)}
                    ),
                    "cases": report_cases,
                }
            )
        )
    return comparison, tuple(evaluations)


def test_experimental_pairs_disclose_treatments_and_keep_exclusions(fixture_graph):
    comparison, evaluations = _changed_evidence(fixture_graph)
    assert comparison.primary_counts["changed_input"] == 5
    result = experimental_comparison(comparison, evaluations)
    assert result.counts == {
        "left_only": 1,
        "right_only": 1,
        "changed_question_options": 0,
        "changed_expectations": 2,
        "unavailable_answer": 1,
        "excluded_expectation": 1,
        "both_correct": 2,
        "improved": 1,
        "regressed": 1,
        "both_wrong": 1,
    }
    assert (result.quality_denominator, result.left_correct_count, result.right_correct_count) == (
        5,
        3,
        3,
    )
    assert result.paired_case_count == 9
    assert result.input_identity_changed_count == 3
    assert (result.request_bytes_changed_count, result.request_bytes_unavailable_count) == (1, 1)
    assert result.image_presence_changed_count == result.selected_image_names_changed_count == 1
    assert result.image_source_changed_count == 1
    assert result.prepared_image_changed_count == 2
    assert result.preparation_changed_count == 1
    assert result.definition_changed
    case = {item.case_id: item for item in result.cases}
    assert case["input-and-label"].bucket == "changed_expectations"
    assert case["input-and-label"].input_identity_changed is True
    assert case["left-only"].input_identity_changed is None
    assert case["image-padded"].preparation_changed is True


def test_experimental_pairs_exclude_incompatible_questions(fixture_graph):
    comparison, evaluations = _changed_evidence(fixture_graph)
    left = {case.case_id: case.left for case in comparison.cases if case.left is not None}
    right = {case.case_id: case.right for case in comparison.cases if case.right is not None}
    different = pair_cases(
        comparison.left, comparison.right.model_copy(update={"question_id": "other"}), left, right
    )
    result = experimental_comparison(different, evaluations)
    assert result.counts["changed_question_options"] == 9
    assert result.quality_denominator == 0


def test_incompatible_answer_is_not_an_excluded_expectation(fixture_graph):
    comparison, evaluations = _changed_evidence(fixture_graph)
    left = {case.case_id: case.left for case in comparison.cases if case.left is not None}
    right = {case.case_id: case.right for case in comparison.cases if case.right is not None}
    left["same"] = left["same"].model_copy(
        update={"correct": None, "exclusion_reasons": ("incompatible_answer",)}
    )
    updated = pair_cases(comparison.left, comparison.right, left, right)
    left_evaluation = evaluations[0]
    changed_cases = tuple(
        case.model_copy(update={"answer_question_id": "another-question"})
        if case.case_id == "same"
        else case
        for case in left_evaluation.cases
    )
    evaluations = (left_evaluation.model_copy(update={"cases": changed_cases}), evaluations[1])
    safe = safe_comparison_outcomes(updated, Sanitizer(("incompatible_answer",)))
    result = experimental_comparison(safe, evaluations)
    cases = {case.case_id: case for case in result.cases}
    assert cases["same"].bucket == "unavailable_answer"


def test_csv_marks_one_row_per_pair_including_one_sided_cases(fixture_graph):
    source = MemorySnapshotSource.from_records(fixture_graph.records)
    saved = ReportService(source, SystemClock()).create(
        ReportRequest(target_id=fixture_graph.comparison_id, preset="classification"),
        operation_id="pair-row-base",
    )
    comparison, evaluations = _changed_evidence(fixture_graph)
    content = saved.content.model_copy(
        update={
            "comparison": comparison,
            "evaluations": evaluations,
            "classification": classification_report(
                evaluations,
                ClassificationPricing(),
                policy="classification-strict-v3",
                comparison=comparison,
            ),
        }
    )
    rows = list(csv.DictReader(io.StringIO(classification_csv(saved.record, content).decode())))
    assert len(rows) == 20
    marked = [row for row in rows if row["experimental_pair_row"] == "true"]
    assert len(marked) == 11
    assert len({row["case_id"] for row in marked}) == 11
    assert {row["experimental_pair_bucket"] for row in marked if row["case_id"] == "left-only"} == {
        "left_only"
    }
    assert {
        row["experimental_pair_bucket"] for row in marked if row["case_id"] == "right-only"
    } == {"right_only"}


def test_redacted_model_names_do_not_appear_equal(fixture_graph):
    comparison, evaluations = _changed_evidence(fixture_graph)
    comparison = comparison.model_copy(
        update={
            "left": comparison.left.model_copy(update={"requested_model": "Bearer alpha"}),
            "right": comparison.right.model_copy(update={"requested_model": "Bearer beta"}),
        }
    )
    safe = safe_comparison_outcomes(comparison, Sanitizer())
    assert safe.left.requested_model == safe.right.requested_model == "Bearer [REDACTED]"
    assert experimental_comparison(safe, evaluations).requested_model_changed is None


def test_v2_comparison_replays_without_new_columns(fixture_graph):
    source = MemorySnapshotSource.from_records(fixture_graph.records)
    service = ReportService(source, SystemClock())
    request = ReportRequest(target_id=fixture_graph.comparison_id, preset="classification")
    saved = service.create(request, operation_id="old-comparison")
    parsed = parse_json(saved.record.content_source)
    for evaluation in parsed["evaluations"]:
        evaluation["context"].pop("cohort_selection", None)
        for case in evaluation["cases"]:
            case.pop("legacy_label_provenances", None)
    parsed["classification"]["policy"] = "classification-strict-v2"
    del parsed["classification"]["experimental_comparison"]
    parsed["classification"]["treatment_limitations"] = list(
        ClassificationReport.model_fields["treatment_limitations"].default
    )
    record = saved.record.model_copy(update={"content_source": dump_json(parsed)})
    record = record.model_copy(update={"content_hash": report_hash(record, saved.content)})
    body = dump_record(record)
    key = ResourceKey("reports", record.id)
    legacy = StoredRecord(key, body, bytes_hash(body))
    source.records[key] = legacy
    intent, receipt = source.operations["old-comparison"]
    source.operations["old-comparison"] = (intent, replace(receipt, changes=(legacy,)))
    assert service.read(record.id).content.classification.policy == "classification-strict-v2"
    assert service.create(request, operation_id="old-comparison").replayed
    assert source.records[key].body == body
    assert (
        "Experimental paired comparison"
        not in service.render(record.id, format="markdown").body.decode()
    )
    columns = next(csv.reader(io.StringIO(service.render(record.id, format="csv").body.decode())))
    assert "experimental_pair_bucket" not in columns
    assert "explicit_refusal" in columns


def test_v3_comparison_replays_and_exports_without_selected_input_fields(fixture_graph):
    source = MemorySnapshotSource.from_records(fixture_graph.records)
    service = ReportService(source, SystemClock())
    request = ReportRequest(target_id=fixture_graph.comparison_id, preset="classification")
    saved = service.create(request, operation_id="v3-comparison")
    parsed = parse_json(saved.record.content_source)
    for evaluation in parsed["evaluations"]:
        evaluation["context"].pop("cohort_selection", None)
        for case in evaluation["cases"]:
            case.pop("legacy_label_provenances", None)
    classification = parsed["classification"]
    classification["policy"] = "classification-strict-v3"
    classification["treatment_limitations"] = [
        "cohort_selection_does_not_establish_representativeness",
        "case_input_hash_covers_original_input_and_source_images",
        "selected_model_input_identity_not_recorded",
        "request_bytes_do_not_identify_change_cause",
        "experimental_pairs_do_not_establish_model_only_causality",
    ]
    experimental = classification["experimental_comparison"]
    experimental["selected_input_comparison"] = "not_recorded"
    del experimental["selected_input_changed_count"]
    del experimental["selected_input_unavailable_count"]
    for case in experimental["cases"]:
        del case["selected_input"]
    record = saved.record.model_copy(update={"content_source": dump_json(parsed)})
    record = record.model_copy(update={"content_hash": report_hash(record, saved.content)})
    body = dump_record(record)
    key = ResourceKey("reports", record.id)
    legacy = StoredRecord(key, body, bytes_hash(body))
    source.records[key] = legacy
    intent, receipt = source.operations["v3-comparison"]
    source.operations["v3-comparison"] = (intent, replace(receipt, changes=(legacy,)))
    assert service.read(record.id).content.classification.policy == "classification-strict-v3"
    assert service.create(request, operation_id="v3-comparison").replayed
    assert source.records[key].body == body
    assert (
        "Selected model input comparison: unavailable (not recorded)."
        in service.render(record.id, format="markdown").body.decode()
    )
    columns = next(csv.reader(io.StringIO(service.render(record.id, format="csv").body.decode())))
    assert "selected_input_changed" not in columns


@pytest.mark.parametrize(
    "damage", ["count", "missing_policy", "missing_category_policy", "input_change"]
)
def test_tampered_experimental_content_is_rejected(fixture_graph, damage):
    source = MemorySnapshotSource.from_records(fixture_graph.records)
    service = ReportService(source, SystemClock())
    saved = service.create(
        ReportRequest(target_id=fixture_graph.comparison_id, preset="classification"),
        operation_id="tampered-comparison",
    )
    parsed = parse_json(saved.record.content_source)
    if damage == "count":
        parsed["classification"]["experimental_comparison"]["quality_denominator"] = 99
    elif damage == "missing_policy":
        del parsed["classification"]["experimental_comparison"]["policy"]
    elif damage == "missing_category_policy":
        del parsed["classification"]["category_only_scoring"]
    else:
        parsed["classification"]["experimental_comparison"]["cases"][0]["selected_input"][
            "changed"
        ] = True
    record = saved.record.model_copy(update={"content_source": dump_json(parsed)})
    record = record.model_copy(update={"content_hash": report_hash(record, saved.content)})
    body = dump_record(record)
    key = ResourceKey("reports", record.id)
    source.records[key] = StoredRecord(key, body, bytes_hash(body))
    with pytest.raises(ServiceFailure) as error:
        service.read(record.id)
    assert (
        error.value.error.reason
        == {
            "count": "report_classification_mismatch",
            "missing_policy": "invalid_report_content",
            "missing_category_policy": "invalid_report_content",
            "input_change": "report_classification_mismatch",
        }[damage]
    )


def test_cli_exports_the_same_experimental_report(fixture_graph, tmp_path):
    project = tmp_path / "project"
    shutil.copytree(fixture_graph.root, project)
    runner = CliRunner()
    args = ["--project", str(project), "--json", "report", "export"]
    result = runner.invoke(
        app,
        [
            *args,
            fixture_graph.comparison_id,
            "--preset",
            "classification",
            "--format",
            "json",
            "--output",
            str(tmp_path / "report.json"),
            "--operation-id",
            "experimental-cli",
        ],
    )
    assert result.exit_code == 0, result.output
    report_id = json.loads(result.stdout)["data"]["report"]["report_id"]
    exported = json.loads((tmp_path / "report.json").read_text())
    assert (
        exported["content"]["classification"]["experimental_comparison"]["quality_denominator"] == 8
    )
    for fmt in ("markdown", "csv"):
        result = runner.invoke(
            app, [*args, "--report-id", report_id, "--format", fmt, "--output", str(tmp_path / fmt)]
        )
        assert result.exit_code == 0, result.output
    assert "Experimental paired comparison" in (tmp_path / "markdown").read_text()
    rows = list(csv.DictReader(io.StringIO((tmp_path / "csv").read_text())))
    assert {row["report_id"] for row in rows} == {report_id}
    assert {row["experimental_quality_denominator"] for row in rows} == {"8"}
