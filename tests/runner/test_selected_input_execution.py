"""Compare frozen selected inputs across real fixture runs."""

import asyncio
import csv
import io
from decimal import Decimal

import pytest
from test_image_execution import seed_image

from deykit.application.comparisons import ComparisonService
from deykit.application.datasets import CaseInput, DatasetService
from deykit.application.evaluations import EvaluationService
from deykit.application.labels import LabelService
from deykit.application.reports import ReportService
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.images import ImagePreparation
from deykit.contracts.json_value import bytes_hash, dump_json, parse_json, semantic_hash
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import ChoiceDefinition, DecisionDraft, DispatchOutcome
from deykit.providers.choice import JevChoiceCompiler
from deykit.reports.models import ReportRequest
from deykit.runner.planner import RunRequest


@pytest.mark.parametrize("change", ["selection", "unselected_field", "key_order"])
def test_selected_input_differences_are_separate_from_case_identity(setup, change):
    source, execution, factory, clock = setup(1)
    labels = LabelService(source, clock)
    labels.set(
        labels.read("decision", "data", "case-00").review,
        ("yes",),
        provenance="model_generated",
        operation_id="label",
    )
    request = RunRequest(
        decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
    )
    evaluations = EvaluationService(source, clock)

    def run(operation):
        result = asyncio.run(execution.start(request, operation_id=operation))
        assert result.exit_code == 0
        return evaluations.evaluate_saved(
            result.run_id, result.latest_result_snapshot_id, operation_id=f"evaluate-{operation}"
        )

    def select(fields):
        key = ResourceKey("drafts", "decision")
        stored = source.read(key)
        draft = load_record(DecisionDraft, stored.body)
        definition = load_record(ChoiceDefinition, draft.editor_source)
        definition = definition.model_copy(update={"selected_fields": fields})
        changed = draft.model_copy(update={"editor_source": dump_record(definition).decode()})
        source.commit("select-extra-field", (SourceChange(key, dump_record(changed), stored.etag),))

    if change == "key_order":
        select(())
    left = run("left")
    if change == "selection":
        select(("text", "exact"))
    else:
        datasets = DatasetService(source, clock)
        case = datasets.case("data", "case-00")
        datasets.edit_case(
            "data",
            "case-00",
            CaseInput(
                input_kind="json",
                input_source=(
                    '{"exact":9007199254740993,"text":"Text 0"}'
                    if change == "key_order"
                    else '{"text":"Text 0","exact":9007199254740994}'
                ),
            ),
            expected_dataset_etag=datasets.read("data").etag,
            expected_case_etag=case.etag,
            operation_id="edit-unselected-field",
        )
    right = run("right")
    comparison = ComparisonService(source, clock).create(
        left.record.id, right.record.id, operation_id="compare"
    )
    reports = ReportService(source, clock)
    report = reports.create(
        ReportRequest(target_id=comparison.record.id, preset="classification"),
        operation_id="report",
    )
    experimental = report.content.classification.experimental_comparison
    pair = experimental.cases[0]
    assert pair.input_identity_changed is (change == "unselected_field")
    assert pair.selected_input.changed is (change in {"selection", "key_order"})
    assert experimental.selected_input_changed_count == (change in {"selection", "key_order"})
    assert experimental.selected_input_unavailable_count == 0
    expected_right = (
        {"exact": 9007199254740993, "text": "Text 0"}
        if change == "key_order"
        else {"text": "Text 0", "exact": 9007199254740993}
        if change == "selection"
        else {"text": "Text 0"}
    )
    assert parse_json(factory.calls[1][1].body)["state"] == expected_right
    exported = reports.render(report.record.id, format="json").body.decode()
    assert "Text 0" not in exported
    assert semantic_hash({"text": "Text 0"}) not in exported
    assert '"selected_input_hash"' not in exported
    rows = list(
        csv.DictReader(io.StringIO(reports.render(report.record.id, format="csv").body.decode()))
    )
    assert "selected_input_hash" not in rows[0]
    assert {row["selected_input_changed"] for row in rows} == {
        str(change in {"selection", "key_order"}).lower()
    }
    assert len(factory.calls) == 2


@pytest.mark.parametrize(
    ("state", "response", "expected_source"),
    [
        ("known", True, "salvaged"),
        ("known", False, "unavailable"),
        ("not_sent", True, "unavailable"),
        ("unknown", True, "unavailable"),
    ],
)
def test_category_only_requires_known_saved_response(
    setup, state, response, expected_source, monkeypatch
):
    source, execution, factory, clock = setup(1)
    labels = LabelService(source, clock)
    labels.set(
        labels.read("decision", "data", "case-00").review,
        ("yes",),
        provenance="model_generated",
        operation_id="label-category",
    )
    raw = (
        '{"model":"jev-1.14.0","answers":{"q":'
        '{"type":"choice","choice":"yes","probabilities":{"yes":0.8,"no":0.8},'
        '"confidence":1}},"usage":{"input_tokens":100,"output_tokens":10}}'
    )
    factory.responses["case-00"] = [
        DispatchOutcome(
            state=state,
            error=ServiceError(code="response_invalid", reason="invalid_probability_sum"),
            raw_response_source=raw if response else None,
        )
    ]
    request = RunRequest(
        decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
    )
    run = asyncio.run(execution.start(request, operation_id="run-category"))
    reports = ReportService(source, clock)
    report = reports.create(
        ReportRequest(
            target_id=run.run_id, target_kind="run", preset="classification", category_only=True
        ),
        operation_id="report-category",
    )
    summary = report.content.classification.evaluations[0]
    assert summary.cases[0].category_only.source == expected_source
    assert summary.full_cohort_strict_accuracy.numerator == 0
    assert summary.category_only.salvaged_count == (expected_source == "salvaged")
    if expected_source == "salvaged":
        monkeypatch.setattr("deykit.providers.choice.COMPILER_VERSION", "2")
        monkeypatch.setattr("deykit.providers.response.TOLERANCE", Decimal("1"))

        def future_validator(*args):
            raise AssertionError("A future validator must not change a frozen report")

        monkeypatch.setattr("deykit.providers.choice.validate_response", future_validator)
        monkeypatch.setattr("deykit.providers.choice._verify_compiled_request_v1", future_validator)
        assert reports.read(report.record.id).content == report.content
        assert b"Category-only" in reports.render(report.record.id, format="markdown").body
    assert len(factory.calls) == 1


def test_category_only_does_not_trust_a_backend_error_for_an_invalid_request(setup):
    source, execution, factory, clock = setup(1)
    labels = LabelService(source, clock)
    labels.set(
        labels.read("decision", "data", "case-00").review,
        ("yes",),
        provenance="model_generated",
        operation_id="label-bad-request",
    )

    class InvalidRequestCompiler(JevChoiceCompiler):
        def compile(self, definition, selected_state, profile):
            request = super().compile(definition, selected_state, profile)
            body = parse_json(request.body)
            body["model"] = "different-model"
            encoded = dump_json(body).encode()
            return request.model_copy(update={"body": encoded, "body_hash": bytes_hash(encoded)})

    factory.compiler = InvalidRequestCompiler()
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="known",
            error=ServiceError(code="response_invalid", reason="invalid_probability_sum"),
            raw_response_source=(
                '{"model":"jev-1.14.0","answers":{"q":'
                '{"type":"choice","choice":"yes","probabilities":{"yes":0.8,"no":0.8},'
                '"confidence":1}},"usage":{"input_tokens":100,"output_tokens":10}}'
            ),
        )
    ]
    run = asyncio.run(
        execution.start(
            RunRequest(
                decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
            ),
            operation_id="run-bad-request",
        )
    )
    report = ReportService(source, clock).create(
        ReportRequest(
            target_id=run.run_id, target_kind="run", preset="classification", category_only=True
        ),
        operation_id="report-bad-request",
    )
    summary = report.content.classification.evaluations[0]
    assert summary.cases[0].category_only.source == "unavailable"
    assert summary.category_only.salvaged_count == 0


def test_category_only_uses_the_frozen_run_option_order(setup):
    source, execution, factory, clock = setup(1)
    labels = LabelService(source, clock)
    labels.set(
        labels.read("decision", "data", "case-00").review,
        ("yes",),
        provenance="model_generated",
        operation_id="label-reordered-options",
    )
    factory.responses["case-00"] = [
        DispatchOutcome(
            state="known",
            error=ServiceError(code="response_invalid", reason="invalid_probability_sum"),
            raw_response_source=(
                '{"model":"jev-1.14.0","answers":{"q":'
                '{"type":"choice","choice":"yes","probabilities":{"yes":0.8,"no":0.8},'
                '"confidence":1}},"usage":{"input_tokens":100,"output_tokens":10}}'
            ),
        )
    ]
    run = asyncio.run(
        execution.start(
            RunRequest(
                decision_id="decision",
                dataset_id="data",
                mode="fixture",
                fixture_set_id="set",
                option_order=("no", "yes"),
            ),
            operation_id="run-reordered-options",
        )
    )
    criteria = parse_json(factory.calls[0][1].body)["questions"]["q"]["criteria"]
    assert tuple(criteria) == ("no", "yes")
    report = ReportService(source, clock).create(
        ReportRequest(
            target_id=run.run_id, target_kind="run", preset="classification", category_only=True
        ),
        operation_id="report-reordered-options",
    )
    summary = report.content.classification.evaluations[0]
    assert summary.cases[0].category_only.source == "salvaged"
    assert summary.cases[0].category_only.correct is True
    assert summary.category_only.salvaged_count == 1
    assert len(factory.calls) == 1


def test_category_only_still_counts_valid_selected_image_answers(setup, tmp_path):
    source, execution, factory, clock, _, _ = seed_image(
        setup,
        tmp_path,
        preparation=ImagePreparation(mode="pad", min_width=280, min_height=280),
    )
    run = asyncio.run(
        execution.start(
            RunRequest(
                decision_id="decision", dataset_id="data", mode="fixture", fixture_set_id="set"
            ),
            operation_id="run-valid-image-category",
        )
    )
    report = ReportService(source, clock).create(
        ReportRequest(
            target_id=run.run_id, target_kind="run", preset="classification", category_only=True
        ),
        operation_id="report-valid-image-category",
    )
    summary = report.content.classification.evaluations[0]
    assert summary.cases[0].category_only.source == "valid"
    assert summary.cases[0].category_only.correct is True
    assert summary.category_only.usable_count == 1
    assert len(factory.calls) == 1


@pytest.mark.parametrize("current_label", [False, True])
def test_report_preserves_legacy_label_provenance_and_cohort_selection(setup, current_label):
    source, execution, factory, clock = setup(2)
    labels = LabelService(source, clock)
    labels.set(
        labels.read("decision", "data", "case-00").review,
        ("yes",),
        provenance="imported_unknown",
        operation_id="legacy-label",
    )
    key = ResourceKey("drafts", "decision")
    stored = source.read(key)
    draft = load_record(DecisionDraft, stored.body)
    definition = load_record(ChoiceDefinition, draft.editor_source)
    older_question = definition.questions[0].model_copy(update={"id": "older"})
    older_definition = definition.model_copy(update={"questions": (older_question,)})
    older_draft = draft.model_copy(update={"editor_source": dump_record(older_definition).decode()})
    source.commit("older-question", (SourceChange(key, dump_record(older_draft), stored.etag),))
    labels.set(
        labels.read("decision", "data", "case-00").review,
        ("no",),
        provenance="authored_fixture",
        operation_id="older-label",
    )
    stored = source.read(key)
    draft = load_record(DecisionDraft, stored.body)
    definition = load_record(ChoiceDefinition, draft.editor_source)
    question = definition.questions[0].model_copy(update={"id": "new-question"})
    definition = definition.model_copy(update={"questions": (question,)})
    changed = draft.model_copy(update={"editor_source": dump_record(definition).decode()})
    source.commit("replace-question", (SourceChange(key, dump_record(changed), stored.etag),))
    if current_label:
        labels.set(
            labels.read("decision", "data", "case-00").review,
            ("no",),
            provenance="model_generated",
            operation_id="current-label",
        )
    run = asyncio.run(
        execution.start(
            RunRequest(
                decision_id="decision",
                dataset_id="data",
                mode="fixture",
                fixture_set_id="set",
                split="development",
                case_ids=("case-00",),
            ),
            operation_id="selected-run",
        )
    )
    reports = ReportService(source, clock)
    report = reports.create(
        ReportRequest(target_id=run.run_id, target_kind="run", preset="classification"),
        operation_id="selected-report",
    )
    evaluation = report.content.evaluations[0]
    selection = evaluation.context.cohort_selection
    assert selection.split == "development"
    assert selection.explicit_case_ids is True
    assert selection.requested_case_count == 1
    assert selection.regression_selected is False
    case = evaluation.cases[0]
    assert case.legacy_question_ids == ("older", "q")
    assert case.legacy_expected_option_ids == (("no",), ("yes",))
    assert case.legacy_label_provenances == ("authored_fixture", "imported_unknown")
    assert case.label_provenance == ("model_generated" if current_label else None)
    assert report.content.classification.evaluations[0].cases[0].applicable is current_label
    markdown = reports.render(report.record.id, format="markdown").body.decode()
    assert "imported\\_unknown" in markdown
    assert "development" in markdown and "explicit case IDs" in markdown
    if not current_label:
        assert "incompatible question" in markdown
    rows = list(
        csv.DictReader(io.StringIO(reports.render(report.record.id, format="csv").body.decode()))
    )
    assert parse_json(rows[0]["legacy_question_ids"]) == ["older", "q"]
    assert parse_json(rows[0]["legacy_expected_option_ids"]) == [["no"], ["yes"]]
    assert parse_json(rows[0]["legacy_label_provenances"]) == [
        "authored_fixture",
        "imported_unknown",
    ]
    assert rows[0]["cohort_split"] == "development"
    assert rows[0]["cohort_explicit_case_ids"] == "true"
    assert reports.read(report.record.id).content == report.content
    assert len(factory.calls) == 1
