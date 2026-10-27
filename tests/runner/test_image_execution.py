"""Managed images travel through the real runner as explicit frozen dependencies."""

import asyncio
import base64
import csv
import io
import json
import shutil

import pytest
from PIL import Image
from typer.testing import CliRunner

from deykit.application.comparisons import ComparisonService
from deykit.application.datasets import CaseInput, DatasetService
from deykit.application.diagnostics import ChoiceOrderRequest, DiagnosticService
from deykit.application.errors import ServiceFailure
from deykit.application.evaluations import EvaluationService
from deykit.application.imports import ImportService
from deykit.application.labels import LabelService
from deykit.application.projects import ProjectService
from deykit.application.regressions import RegressionAdd, RegressionService
from deykit.application.reports import ReportService
from deykit.cli.main import app
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.images import CaseImage, ImagePreparation
from deykit.contracts.json_value import bytes_hash, dump_json, parse_json
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import ChoiceDefinition, DecisionDraft
from deykit.domain.import_mapping import ImageField, ImportMapping
from deykit.images.local import LocalImages
from deykit.providers.choice import JevChoiceCompiler
from deykit.reports.models import ReportRequest
from deykit.runner.planner import RunRequest
from deykit.storage import FileProjectSource


class AuthoredImageCompiler(JevChoiceCompiler):
    def compile_images(self, definition, selected_state, profile, images):
        # This is authored transport-contract evidence, not a provider wire format.
        text_definition = definition.model_copy(update={"selected_images": ()})
        request = self.compile(text_definition, selected_state, profile)
        body = parse_json(request.body)
        body["authored_images"] = [
            {"name": name, "bytes": base64.b64encode(asset.prepared_bytes()).decode("ascii")}
            for name, asset in images
        ]
        wire = dump_json(body).encode()
        return request.model_copy(update={"body": wire, "body_hash": bytes_hash(wire)})


def seed_image(setup, tmp_path, *, select=True, preparation=None):
    source, execution, factory, clock = setup(0)
    root = tmp_path / "images"
    root.mkdir()
    Image.new("RGB", (2, 1), (255, 0, 0)).save(root / "product.png")
    imports = ImportService(source, clock, images=LocalImages(root))
    # JSON model input is an object; its image path and expectation stay outside it.
    preview = imports.preview(
        "data",
        '{"id":"product","input":{"text":"red"},"image":"product.png","expected":"yes"}',
        format="jsonl",
        decision_id="decision",
        mapping=ImportMapping(
            input_kind="json",
            input_column="input",
            id_column="id",
            expected_column="expected",
            images=(
                ImageField(
                    source="image", name="product", preparation=preparation or ImagePreparation()
                ),
            ),
        ),
    )
    imports.commit(preview, operation_id="import-image")
    key = ResourceKey("drafts", "decision")
    stored = source.read(key)
    draft = load_record(DecisionDraft, stored.body)
    definition = load_record(ChoiceDefinition, draft.editor_source)
    if select:
        definition = definition.model_copy(update={"selected_images": ("product",)})
        changed = draft.model_copy(update={"editor_source": dump_record(definition).decode()})
        source.commit("select-images", (SourceChange(key, dump_record(changed), stored.etag),))
    return source, execution, factory, clock, root, definition


def request():
    return RunRequest(
        decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
    )


def test_selected_images_fail_before_dispatch_with_text_compiler(setup, tmp_path):
    source, execution, factory, _, _, _ = seed_image(setup, tmp_path)

    class TextCompiler:
        review_identity = JevChoiceCompiler().review_identity
        compile = JevChoiceCompiler().compile
        validate_response = JevChoiceCompiler().validate_response

    factory.compiler = TextCompiler()
    with pytest.raises(ServiceFailure) as error:
        execution.preview(request())
    assert error.value.error.reason == "image_compilation_unsupported"
    assert not factory.calls and not source.list_ids("runs")


def test_replacing_original_image_makes_expectation_stale(setup, tmp_path):
    source, _, _, clock, root, _ = seed_image(setup, tmp_path)
    Image.new("RGB", (2, 1), (0, 0, 255)).save(root / "blue.png")
    asset = LocalImages(root).prepare("blue.png", ImagePreparation())
    source.commit(
        "blue-image",
        (SourceChange(ResourceKey("image_assets", asset.id), dump_record(asset), None),),
    )
    datasets = DatasetService(source, clock)
    case = datasets.case("data", "product")
    value = CaseInput(
        input_kind="json",
        input_source=case.record.input_source,
        images=(
            CaseImage(name="product", asset_id=asset.id, source_hash=asset.source.content_hash),
        ),
    )
    datasets.edit_case(
        "data",
        "product",
        value,
        expected_dataset_etag=datasets.read("data").etag,
        expected_case_etag=case.etag,
        operation_id="replace-image",
    )
    assert LabelService(source, clock).read("decision", "data", "product").reasons == ("stale",)


def test_frozen_images_reports_and_changed_preparation_exclusions(setup, tmp_path):
    source, execution, factory, clock, root, _ = seed_image(setup, tmp_path)
    factory.compiler = AuthoredImageCompiler()
    before = source.capture_snapshot()
    assert execution.preview(request()).initial_requests == 1
    assert source.capture_snapshot() == before and not factory.calls
    first = asyncio.run(execution.start(request(), operation_id="run-original"))
    assert first.exit_code == 0 and len(factory.calls) == 1
    assert b"expected" not in factory.calls[0][1].body
    evaluations = EvaluationService(source, clock)
    left = evaluations.evaluate_saved(
        first.run_id, first.latest_result_snapshot_id, operation_id="evaluate-left"
    )
    datasets = DatasetService(source, clock)
    case = datasets.case("data", "product")
    asset = LocalImages(root).prepare(
        "product.png", ImagePreparation(mode="pad", min_width=4, min_height=4)
    )
    source.commit(
        "prepare-padding",
        (SourceChange(ResourceKey("image_assets", asset.id), dump_record(asset), None),),
    )
    value = CaseInput(
        input_kind=case.record.input_kind,
        input_source=case.record.input_source,
        images=(
            CaseImage(name="product", asset_id=asset.id, source_hash=asset.source.content_hash),
        ),
    )
    datasets.edit_case(
        "data",
        "product",
        value,
        expected_dataset_etag=datasets.read("data").etag,
        expected_case_etag=case.etag,
        operation_id="use-padding",
    )
    second = asyncio.run(execution.start(request(), operation_id="run-padding"))
    right = evaluations.evaluate_saved(
        second.run_id, second.latest_result_snapshot_id, operation_id="evaluate-right"
    )
    comparison = ComparisonService(source, clock).create(
        left.record.id, right.record.id, operation_id="compare-images"
    )
    assert comparison.outcomes.primary_counts["changed_input"] == 1
    assert comparison.outcomes.quality_denominator == 0
    assert first.cases[0].status == second.cases[0].status == "valid"
    reports = ReportService(source, clock)
    report = reports.create(
        ReportRequest(
            target_id=comparison.record.id, target_kind="comparison", preset="classification"
        ),
        operation_id="image-report",
    )
    left_case, right_case = [evaluation.cases[0] for evaluation in report.content.evaluations]
    assert left_case.expected_option_ids == right_case.expected_option_ids == ("yes",)
    assert left_case.label_provenance == right_case.label_provenance == "imported_unknown"
    assert left_case.input_hash == right_case.input_hash
    assert (
        left_case.selected_images[0].asset.prepared.content_hash
        != right_case.selected_images[0].asset.prepared.content_hash
    )
    assert (
        left_case.selected_images[0].asset.source.content_hash
        == right_case.selected_images[0].asset.source.content_hash
    )
    assert all(
        evaluation.metrics.summary.set_accuracy.denominator == 1
        for evaluation in report.content.evaluations
    )
    experimental = report.content.classification.experimental_comparison
    assert experimental.quality_denominator == 1
    assert experimental.counts["both_correct"] == 1
    assert experimental.input_identity_changed_count == 0
    assert experimental.prepared_image_changed_count == 1
    assert experimental.preparation_changed_count == 1
    assert experimental.image_source_changed_count == 0
    calls = len(factory.calls)
    markdown = reports.render(report.record.id, format="markdown").body.decode()
    assert "Prepared image treatments" in markdown and asset.prepared.content_hash in markdown
    rows = list(
        csv.DictReader(io.StringIO(reports.render(report.record.id, format="csv").body.decode()))
    )
    assert json.loads(rows[1]["selected_images"])[0]["asset"]["id"] == asset.id
    assert {row["experimental_pair_bucket"] for row in rows} == {"both_correct"}
    assert {row["preparation_changed"] for row in rows} == {"true"}
    assert asset.id in reports.render(report.record.id, format="json").body.decode()
    output = tmp_path / "image-report.json"
    cli = CliRunner().invoke(
        app,
        [
            "--project",
            str(source.root),
            "--json",
            "report",
            "export",
            "--report-id",
            report.record.id,
            "--format",
            "json",
            "--output",
            str(output),
        ],
    )
    assert cli.exit_code == 0, cli.output
    exported = json.loads(output.read_text())
    assert (
        exported["content"]["classification"]["experimental_comparison"][
            "preparation_changed_count"
        ]
        == 1
    )
    assert len(factory.calls) == calls == 2
    ProjectService.validate_opened(source)
    copy = tmp_path / "copied"
    shutil.copytree(source.root, copy)
    shutil.rmtree(root)
    with FileProjectSource(copy) as copied:
        ProjectService.validate_opened(copied)
        assert (
            ReportService(copied, clock).render(report.record.id, format="json").body
            == reports.render(report.record.id, format="json").body
        )


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_missing_asset_blocks_run_and_completed_answer_reuse(setup, tmp_path, damage):
    source, execution, factory, clock, _, _ = seed_image(setup, tmp_path)
    factory.compiler = AuthoredImageCompiler()
    result = asyncio.run(execution.start(request(), operation_id="image-run"))
    assert len(factory.calls) == 1
    image_file = next((source.root / "source" / "image_assets").glob("*.json"))
    if damage == "missing":
        image_file.unlink()
    else:
        value = json.loads(image_file.read_text())
        value["source_base64"] = base64.b64encode(b"corrupt").decode()
        image_file.write_text(json.dumps(value))
    with pytest.raises(ServiceFailure):
        execution.preview(request())
    with pytest.raises(ServiceFailure):
        asyncio.run(execution.resume(result.run_id, operation_id="resume"))
    with pytest.raises(ServiceFailure):
        EvaluationService(source, clock).evaluate_saved(
            result.run_id, result.latest_result_snapshot_id, operation_id="evaluate"
        )
    assert len(factory.calls) == 1


def test_image_regression_uses_frozen_case_after_current_case_removed(setup, tmp_path):
    source, execution, factory, clock, _, _ = seed_image(setup, tmp_path)
    factory.compiler = AuthoredImageCompiler()
    first = asyncio.run(execution.start(request(), operation_id="first"))
    regression = RegressionService(source, clock).add(
        RegressionAdd(
            run_id=first.run_id,
            case_id="product",
            acceptable_option_ids=("yes",),
            reason="Preserve image input",
            provenance="authored_fixture",
        ),
        operation_id="regression",
    )
    datasets = DatasetService(source, clock)
    datasets.remove_case(
        "data",
        "product",
        expected_dataset_etag=datasets.read("data").etag,
        expected_case_etag=datasets.case("data", "product").etag,
        operation_id="remove-current",
    )
    selected = request().model_copy(update={"regression_ids": (regression.id,)})
    assert execution.preview(selected).initial_requests == 1
    second = asyncio.run(execution.start(selected, operation_id="regression-run"))
    assert second.exit_code == 0 and len(factory.calls) == 2
    assert factory.calls[0][1].body == factory.calls[1][1].body
    ProjectService.validate_opened(source)


def test_diagnostic_report_retains_member_image_treatments(setup, tmp_path):
    source, execution, factory, clock, _, _ = seed_image(setup, tmp_path)
    factory.compiler = AuthoredImageCompiler()
    result = asyncio.run(
        DiagnosticService(execution).start(
            ChoiceOrderRequest(run=request(), orders=2), operation_id="image-orders"
        )
    )
    reports = ReportService(source, clock)
    report = reports.create(
        ReportRequest(target_id=result.group.group_id, target_kind="diagnostic"),
        operation_id="image-order-report",
    )
    assert len(report.content.diagnostic.members) == 2
    for member in report.content.diagnostic.members:
        treatment = member.image_treatments[0]
        assert treatment.case_id == "product"
        assert treatment.selected_images[0].name == "product"
        assert treatment.selected_images[0].asset.prepared.width == 2
    assert "Image for" in reports.render(report.record.id, format="markdown").body.decode()
    assert len(factory.calls) == 2
