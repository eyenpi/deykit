"""Resource selection uses exact IDs and retains transient safe alternatives."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest
from typer.testing import CliRunner

from deykit.application.errors import ServiceFailure
from deykit.application.selectors import (
    choices_for_kinds,
    require_one_of,
    require_resource,
    resource_choices,
)
from deykit.cli.context import CliState
from deykit.cli.main import app
from deykit.cli.output import emit_error
from deykit.cli.selection import (
    SelectorHint,
    SelectorOwner,
    resolve_hint,
    selection_context,
    selector_hint,
)
from deykit.contracts.codec import dump_record
from deykit.contracts.errors import Failure, ServiceError
from deykit.contracts.ports import Collection, ResourceKey, SourceChange, StoredRecord
from deykit.contracts.records import (
    CaseRecord,
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    DatasetRecord,
    DecisionRecord,
    EvaluationRecord,
    ExecutionSettings,
    FixtureBinding,
    NormalizedAnswer,
    RunManifest,
)
from deykit.contracts.selection import ResourceChoice, SelectionDetails
from deykit.providers.choice import compile_choice
from deykit.storage import FileProjectSource


def stored(
    collection: Collection, resource_id: str, scope: tuple[str, ...] = ()
) -> StoredRecord:
    return StoredRecord(ResourceKey(collection, resource_id, scope), b"{}", "0" * 64)


def test_case_selector_is_exact_and_dataset_scoped() -> None:
    first = stored("cases", "same", ("dataset-b",))
    second = stored("cases", "same", ("dataset-a",))
    records = (first, second)

    assert require_resource(records, "case", "same", ("dataset-a",)) == second
    with pytest.raises(ServiceFailure) as ambiguous:
        require_resource(records, "case", "same")

    assert ambiguous.value.error.reason == "selection_ambiguous"
    assert ambiguous.value.selection is not None
    assert [choice.scope for choice in ambiguous.value.selection.choices] == [
        ("dataset-a",),
        ("dataset-b",),
    ]


def test_missing_selector_returns_only_sorted_safe_ids_in_scope() -> None:
    records = (
        stored("fixtures", "fixture-b", ("decision", "dataset")),
        stored("fixtures", "fixture-a", ("decision", "dataset")),
        stored("fixtures", "unrelated"),
    )
    with pytest.raises(ServiceFailure) as missing:
        require_resource(records, "fixture", "absent", ("decision", "dataset"))

    assert missing.value.error.code == "not_found"
    assert missing.value.error.resource_id is None
    assert missing.value.selection is not None
    assert [choice.resource_id for choice in missing.value.selection.choices] == [
        "fixture-a",
        "fixture-b",
    ]
    assert resource_choices(records, "fixture", ("decision", "dataset")) == (
        ResourceChoice(kind="fixture", resource_id="fixture-a", scope=("decision", "dataset")),
        ResourceChoice(kind="fixture", resource_id="fixture-b", scope=("decision", "dataset")),
    )


def test_cross_kind_selection_keeps_equal_ids_distinct() -> None:
    records = (stored("runs", "shared"), stored("evaluations", "shared"))
    assert [(item.kind, item.resource_id) for item in choices_for_kinds(
        records, ("run", "evaluation")
    )] == [("evaluation", "shared"), ("run", "shared")]

    with pytest.raises(ServiceFailure) as ambiguous:
        require_one_of(records, ("run", "evaluation"), "shared")
    assert ambiguous.value.selection == SelectionDetails(
        choices=(
            ResourceChoice(kind="evaluation", resource_id="shared"),
            ResourceChoice(kind="run", resource_id="shared"),
        )
    )


def test_selection_details_are_transient_top_level_cli_metadata(capsys) -> None:
    selection = SelectionDetails(
        choices=(ResourceChoice(kind="decision", resource_id="known"),)
    )
    failure = ServiceFailure(ServiceError(code="not_found"), selection=selection)
    emit_error(CliState(None, True), failure.error, selection=failure.selection)

    envelope = json.loads(capsys.readouterr().out)
    assert envelope["selection"] == {
        "choices": [{"kind": "decision", "resource_id": "known", "scope": []}]
    }
    assert "selection" not in envelope["error"]
    assert "selection" not in ServiceError(code="not_found").model_dump()
    assert Failure(error=ServiceError(code="not_found"), selection=selection).selection == selection


class CapturedSource:
    def __init__(self, records: tuple[StoredRecord, ...]) -> None:
        self.records = records
        self.captures = 0

    @contextmanager
    def consistent_read(self) -> Iterator[CapturedSource]:
        yield self

    def capture_snapshot(self):
        self.captures += 1
        return self.records


def test_selection_context_captures_only_after_service_failure_and_preserves_error() -> None:
    source = CapturedSource((stored("decisions", "known"),))
    original = ServiceError(
        code="not_found", resource_id="missing", reason="owned_service_reason", row=7
    )

    with pytest.raises(ServiceFailure) as caught:
        with selection_context(source, (selector_hint("decision", "missing", ()),)):
            assert source.captures == 0
            raise ServiceFailure(original)

    assert source.captures == 1
    assert caught.value.error == original
    assert caught.value.selection is not None
    assert [choice.resource_id for choice in caught.value.selection.choices] == ["known"]


def test_selection_context_does_not_capture_for_success_or_enrich_resolved_selector() -> None:
    source = CapturedSource((stored("decisions", "known"),))
    with selection_context(source, (selector_hint("decision", "known", ()),)):
        pass
    assert source.captures == 0

    original = ServiceError(code="not_found", reason="business_rule_failure")
    with pytest.raises(ServiceFailure) as caught:
        with selection_context(source, (selector_hint("decision", "known", ()),)):
            raise ServiceFailure(original)
    assert source.captures == 1
    assert caught.value.error == original
    assert caught.value.selection is None


def test_unadmittable_owner_never_falls_back_to_global_choices() -> None:
    records = (stored("runs", "broken-run"), stored("cases", "unrelated", ("dataset",)))
    hint = SelectorHint(
        kinds=("case",),
        resource_id="missing-case",
        scopes={"case": ()},
        owner=SelectorOwner("run", "broken-run"),
    )
    assert resolve_hint(records, hint) is None

    source = CapturedSource(records)
    original = ServiceError(code="not_found", reason="original_failure")
    with pytest.raises(ServiceFailure) as caught:
        with selection_context(source, (hint,)):
            raise ServiceFailure(original)
    assert caught.value.error == original
    assert caught.value.selection is None


def test_cli_missing_and_duplicate_case_selectors_are_project_and_dataset_scoped(
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    project = tmp_path / "Project ü with spaces"

    def invoke(*arguments: str, expected: int = 0) -> dict[str, object]:
        result = runner.invoke(app, [*arguments])
        assert result.exit_code == expected, result.output
        return json.loads(result.stdout)

    invoke("--json", "init", str(project), "--name", "Selector test")
    empty_decision = invoke(
        "--project", str(project), "--json", "decision", "show", "missing", expected=2
    )
    assert empty_decision["selection"] == {"choices": []}
    empty_provider = invoke(
        "--project", str(project), "--json", "provider", "show", "missing", expected=2
    )
    assert empty_provider["selection"] == {"choices": []}

    definition_file = tmp_path / "definition.json"
    definition_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "input_kind": "json",
                "input_schema_source": '{"type":"object","required":["shown"]}',
                "selected_fields": ["shown"],
                "questions": [
                    {
                        "id": "q",
                        "kind": "choice",
                        "instructions": "Choose",
                        "options": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    invoke(
        "--project",
        str(project),
        "--json",
        "decision",
        "create",
        "choice",
        "--name",
        "Choice",
        "--file",
        str(definition_file),
    )
    for dataset in ("dataset-a", "dataset-b"):
        invoke("--project", str(project), "--json", "dataset", "create", dataset, "--name", dataset)
        case_file = tmp_path / f"{dataset}.json"
        case_file.write_text(
            json.dumps({"input_kind": "json", "input_source": '{"shown":"hi"}'}),
            encoding="utf-8",
        )
        invoke(
            "--project",
            str(project),
            "--json",
            "case",
            "add",
            "--dataset",
            dataset,
            "--id",
            "shared-case",
            "--file",
            str(case_file),
        )

    missing_case = invoke(
        "--project",
        str(project),
        "--json",
        "case",
        "show",
        "absent-case",
        "--dataset",
        "dataset-a",
        expected=2,
    )
    assert missing_case["error"]["code"] == "not_found"
    assert missing_case["selection"]["choices"] == [
        {"kind": "case", "resource_id": "shared-case", "scope": ["dataset-a"]}
    ]
    resolved = invoke(
        "--project",
        str(project),
        "--json",
        "case",
        "show",
        "shared-case",
        "--dataset",
        "dataset-b",
    )
    assert resolved["data"]["record"]["id"] == "shared-case"


def test_cli_report_target_ambiguity_keeps_cross_kind_choices(tmp_path: Path) -> None:
    runner = CliRunner()
    project = tmp_path / "Ambiguous report project"
    initialized = runner.invoke(app, ["--json", "init", str(project), "--name", "Ambiguous"])
    assert initialized.exit_code == 0, initialized.output
    shared_id = "shared-report-target"
    with FileProjectSource(project) as source:
        source.commit(
            "seed-ambiguous-report-target",
            (
                SourceChange(
                    ResourceKey("runs", shared_id),
                    dump_record(
                        RunManifest(
                            id=shared_id,
                            decision_revision_id="revision",
                            dataset_snapshot_id="dataset-snapshot",
                            label_snapshot_id="label-snapshot",
                            provider_profile_id="provider",
                            provider_config_hash="0" * 64,
                            adapter="fixture",
                            compiler_version="1",
                            requested_model="authored-model",
                            mode="fixture",
                            case_ids=(),
                            settings=ExecutionSettings(),
                            created_at="2026-01-01T00:00:00Z",
                            operation_id="run-operation",
                        )
                    ),
                    None,
                ),
                SourceChange(
                    ResourceKey("evaluations", shared_id),
                    dump_record(
                        EvaluationRecord(
                            id=shared_id,
                            run_id=shared_id,
                            result_snapshot_id="result-snapshot",
                            label_snapshot_id="label-snapshot",
                            mode="original",
                            metrics_source='{"profile":"placeholder"}',
                            content_hash="0" * 64,
                            created_at="2026-01-01T00:00:00Z",
                        )
                    ),
                    None,
                ),
            ),
        )

    output = tmp_path / "ambiguous.json"
    result = runner.invoke(
        app,
        [
            "--project",
            str(project),
            "--json",
            "report",
            "export",
            shared_id,
            "--format",
            "json",
            "--output",
            str(output),
            "--operation-id",
            "ambiguous-report-export",
        ],
    )
    assert result.exit_code == 2, result.output
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "incompatible_data"
    assert envelope["error"]["reason"] == "ambiguous_report_target"
    assert envelope["selection"]["choices"] == [
        {"kind": "evaluation", "resource_id": shared_id, "scope": []},
        {"kind": "run", "resource_id": shared_id, "scope": []},
    ]
    assert not output.exists()


def test_cli_fixture_create_and_missing_case_choices_are_dataset_scoped(tmp_path: Path) -> None:
    runner = CliRunner()
    project = tmp_path / "Fixture selector project"
    initialized = runner.invoke(
        app, ["--json", "init", str(project), "--name", "Fixture selectors"]
    )
    assert initialized.exit_code == 0, initialized.output
    stamp = "2026-10-09T12:00:00Z"
    with FileProjectSource(project) as source:
        source.commit(
            "seed-fixture-selector-context",
            (
                SourceChange(
                    ResourceKey("decisions", "decision"),
                    dump_record(DecisionRecord(id="decision", name="Decision")),
                    None,
                ),
                SourceChange(
                    ResourceKey("datasets", "dataset"),
                    dump_record(DatasetRecord(id="dataset", name="Dataset", created_at=stamp)),
                    None,
                ),
                SourceChange(
                    ResourceKey("cases", "case", ("dataset",)),
                    dump_record(
                        CaseRecord(
                            id="case",
                            dataset_id="dataset",
                            input_kind="json",
                            input_source='{"text":"hello"}',
                        )
                    ),
                    None,
                ),
            ),
        )

    definition = ChoiceDefinition(
        input_kind="json",
        selected_fields=("text",),
        questions=(
            ChoiceQuestion(
                id="q",
                instructions="Choose",
                options=(ChoiceOption(id="yes", name="Yes"), ChoiceOption(id="no", name="No")),
            ),
        ),
    )
    compiled = compile_choice(definition, {"text": "hello"}, "authored-model", adapter="fixture")
    binding = FixtureBinding(
        id="binding",
        case_id="case",
        request=compiled,
        answer=NormalizedAnswer(question_id="q", option_id="yes", reported_model="authored-model"),
    )
    bindings_file = tmp_path / "bindings.jsonl"
    bindings_file.write_text(dump_record(binding) + "\n", encoding="utf-8")
    prefix = ["--project", str(project), "--json"]
    authored = runner.invoke(
        app,
        [
            *prefix,
            "fixture",
            "create",
            "fixture-set",
            "--decision",
            "decision",
            "--dataset",
            "dataset",
            "--name",
            "Authored",
            "--model",
            "authored-model",
            "--file",
            str(bindings_file),
            "--operation-id",
            "fixture-create",
        ],
    )
    assert authored.exit_code == 0, authored.output
    assert json.loads(authored.stdout)["data"]["dispatch_count"] == 0
    page = runner.invoke(app, [*prefix, "fixture", "list", "--limit", "1"])
    assert page.exit_code == 0, page.output
    assert json.loads(page.stdout)["data"]["items"][0]["id"] == "fixture-set"
    shown = runner.invoke(app, [*prefix, "fixture", "show", "fixture-set", "--request"])
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.stdout)["data"]["requests"] == [compiled.body.decode("utf-8")]

    missing_binding = binding.model_copy(update={"case_id": "missing-case"})
    bindings_file.write_text(dump_record(missing_binding) + "\n", encoding="utf-8")
    missing = runner.invoke(
        app,
        [
            *prefix,
            "fixture",
            "create",
            "missing-set",
            "--decision",
            "decision",
            "--dataset",
            "dataset",
            "--name",
            "Missing case",
            "--model",
            "authored-model",
            "--file",
            str(bindings_file),
            "--operation-id",
            "fixture-missing-case",
        ],
    )
    assert missing.exit_code == 2, missing.output
    envelope = json.loads(missing.stdout)
    assert envelope["error"]["reason"] == "fixture_case_missing"
    assert envelope["selection"]["choices"] == [
        {"kind": "case", "resource_id": "case", "scope": ["dataset"]}
    ]
