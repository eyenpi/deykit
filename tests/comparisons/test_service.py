"""Real-store comparisons use genuine offline runner dispatch/settlement evidence."""

import asyncio
import json
import shutil
from dataclasses import replace

import pytest
from typer.testing import CliRunner

from deykit.application.comparisons import ComparisonService, _prepared, comparison_hash
from deykit.application.datasets import CaseInput, DatasetService
from deykit.application.demo import DemoService
from deykit.application.errors import ServiceFailure
from deykit.application.evaluations import EvaluationService
from deykit.application.execution import ExecutionService
from deykit.application.fixtures import FixtureService
from deykit.application.labels import LabelService
from deykit.cli.context import SystemClock
from deykit.cli.main import app
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.ports import ResourceKey
from deykit.contracts.records import NormalizedAnswer, PreparedCase
from deykit.runner.backends import ProviderBackends
from deykit.runner.planner import RunRequest
from deykit.storage import FileProjectSource


@pytest.fixture(scope="module")
def seed(tmp_path_factory):
    clock = SystemClock()
    root = tmp_path_factory.mktemp("comparison-seed") / "Comparison ü"
    info = DemoService(lambda path, create: FileProjectSource(path, create=create), clock).create(
        root, operation_id="demo"
    )
    with FileProjectSource(root) as source:
        fixtures = FixtureService(source, clock)
        original = fixtures.read(info.fixture_set_id).fixture_set
        corrected = tuple(
            binding.model_copy(
                update={
                    "answer": NormalizedAnswer(
                        question_id="category",
                        option_id="question",
                        reported_model=original.model_identity,
                    )
                }
            )
            if binding.case_id == "ex-003"
            else binding
            for binding in original.bindings
        )
        fixtures.create(
            "corrected",
            info.decision_id,
            info.dataset_id,
            "Authored correction",
            original.model_identity,
            tuple(dump_record(binding) for binding in corrected),
            operation_id="corrected-fixture",
        )
        runner = ExecutionService(source, source, ProviderBackends(source, clock), clock)
        evaluations = EvaluationService(source, clock)

        def run(fixture_id, op, **changes):
            progress = asyncio.run(
                runner.start(
                    RunRequest(
                        decision_id=info.decision_id,
                        dataset_id=info.dataset_id,
                        mode="fixture",
                        fixture_set_id=fixture_id,
                        **changes,
                    ),
                    operation_id=op,
                )
            )
            return evaluations.evaluate_saved(
                progress.run_id, progress.latest_result_snapshot_id, operation_id="evaluate-" + op
            )

        left, right = run(info.fixture_set_id, "left"), run("corrected", "right")
    return root, info, left, right


@pytest.fixture
def sandbox(seed, tmp_path):
    seed_root, info, left, right = seed
    root = tmp_path / "Comparison ü"
    # Copy only a quiescent, closed project. Each test owns its source and journal.
    shutil.copytree(seed_root, root)
    clock = SystemClock()
    with FileProjectSource(root) as source:
        runner = ExecutionService(source, source, ProviderBackends(source, clock), clock)
        evaluations = EvaluationService(source, clock)

        def run(fixture_id, op, **changes):
            progress = asyncio.run(
                runner.start(
                    RunRequest(
                        decision_id=info.decision_id,
                        dataset_id=info.dataset_id,
                        mode="fixture",
                        fixture_set_id=fixture_id,
                        **changes,
                    ),
                    operation_id=op,
                )
            )
            return evaluations.evaluate_saved(
                progress.run_id, progress.latest_result_snapshot_id, operation_id="evaluate-" + op
            )

        yield source, info, clock, left, right, run


def test_a36_exact_sandbox_counts_and_idempotent_immutable_comparison(sandbox, monkeypatch):
    source, info, clock, left, right, run = sandbox
    ids = []

    def new_id():
        ids.append("comparison")
        return "comparison"

    service = ComparisonService(source, clock, new_id)
    saved = service.create(left.record.id, right.record.id, operation_id="compare")
    outcomes = saved.outcomes
    assert outcomes.quality_denominator == 8
    assert {key: value for key, value in outcomes.primary_counts.items() if value} == {
        "both_correct": 6,
        "improved": 1,
        "both_wrong": 1,
        "unlabelled_agreement": 2,
        "unavailable_answer": 2,
    }
    assert outcomes.left_correct_count == 6 and outcomes.right_correct_count == 7
    assert len(outcomes.cases) == 12 and sum(outcomes.primary_counts.values()) == 12
    assert outcomes.left_status_counts == {
        "pending": 0,
        "input_invalid": 1,
        "response_error": 1,
        "unknown": 0,
        "valid": 10,
    }
    assert outcomes.left.label_snapshot_id != outcomes.right.label_snapshot_id
    assert outcomes.left.dataset_snapshot_id != outcomes.right.dataset_snapshot_id
    assert outcomes.left.label_hash != "0" * 64
    assert outcomes.left.compiler_ids == outcomes.right.compiler_ids == ("jev-choice",)
    assert all(
        case.left.request_hash is not None for case in outcomes.cases if case.left.status == "valid"
    )
    assert all(
        case.left.request_hash is None
        for case in outcomes.cases
        if case.left.status == "input_invalid"
    )
    labels = LabelService(source, clock)
    labels.set(
        labels.read(info.decision_id, info.dataset_id, "ex-001").review,
        ("report",),
        provenance="human",
        operation_id="change-after-comparison",
    )
    run(info.fixture_set_id, "newer", case_ids=("ex-002",))
    replay = service.create(left.record.id, right.record.id, operation_id="compare")
    assert replay.replayed and replay.record == saved.record and ids == ["comparison"]
    assert service.read(saved.record.id).outcomes == outcomes
    from deykit.application import comparisons

    monkeypatch.setattr(
        comparisons,
        "assess_results",
        lambda *args: (_ for _ in ()).throw(AssertionError("saved reads must not recompute")),
    )
    assert service.read(saved.record.id).outcomes == outcomes
    with pytest.raises(ServiceFailure) as changed:
        service.create(right.record.id, left.record.id, operation_id="compare")
    assert changed.value.error.code == "conflict"


def test_saved_request_and_compiler_links_reject_rehashed_wrong_context(sandbox, monkeypatch):
    source, _, clock, left, right, _ = sandbox
    service = ComparisonService(source, clock)
    saved = service.create(left.record.id, right.record.id, operation_id="binding-test")
    original_read = source.read
    stored = original_read(ResourceKey("comparisons", saved.record.id))
    # Only the comparison payload is altered. All answers and attempt evidence
    # remain genuine runner records. A valid new content hash cannot repair links.
    wrong_context = saved.outcomes.model_copy(
        update={"left": saved.outcomes.left.model_copy(update={"compiler_ids": ("other",)})}
    )
    first = saved.outcomes.cases[0]
    wrong_request = saved.outcomes.model_copy(
        update={
            "cases": (
                first.model_copy(
                    update={"left": first.left.model_copy(update={"request_hash": "0" * 64})}
                ),
                *saved.outcomes.cases[1:],
            )
        }
    )
    for outcomes, reason in (
        (wrong_context, "comparison_context_mismatch"),
        (wrong_request, "comparison_request_link_mismatch"),
    ):
        record = saved.record.model_copy(
            update={"outcomes_source": dump_record(outcomes).decode("utf-8")}
        )
        record = record.model_copy(update={"content_hash": comparison_hash(record)})
        altered = replace(stored, body=dump_record(record))
        with monkeypatch.context() as patch:
            patch.setattr(
                source,
                "read",
                lambda key, altered=altered: altered if key == stored.key else original_read(key),
            )
            with pytest.raises(ServiceFailure) as rejected:
                service.read(saved.record.id)
            assert rejected.value.error.reason == reason
    evaluations = EvaluationService(source, clock)
    frozen = evaluations.frozen_context(left.record.run_id, left.record.result_snapshot_id)
    records = source.capture_snapshot()
    prepared = next(
        item
        for item in records
        if item.key.collection == "prepared_cases" and item.key.scope == (left.record.run_id,)
    )
    record = load_record(PreparedCase, prepared.body)
    for change in ({"run_id": "other"}, {"input_hash": "0" * 64}):
        altered = replace(prepared, body=dump_record(record.model_copy(update=change)))
        with pytest.raises(ServiceFailure) as rejected:
            _prepared(tuple(altered if item == prepared else item for item in records), frozen)
        assert rejected.value.error.reason == "comparison_prepared_context_mismatch"


def test_changed_expectations_and_partial_results_never_silently_pair(sandbox):
    source, info, clock, left, right, run = sandbox
    labels = LabelService(source, clock)
    labels.set(
        labels.read(info.decision_id, info.dataset_id, "ex-001").review,
        ("report",),
        provenance="human",
        operation_id="change-label",
    )
    evaluations = EvaluationService(source, clock)
    updated = evaluations.reevaluate_current_labels(
        right.record.run_id, right.record.result_snapshot_id, operation_id="new-label-context"
    )
    saved = ComparisonService(source, clock).create(
        left.record.id, updated.record.id, operation_id="changed-expectation"
    )
    assert saved.outcomes.primary_counts["changed_expectations"] == 1
    assert saved.outcomes.quality_denominator == 7
    scoped = run(info.fixture_set_id, "scoped", case_ids=("ex-001",))
    unequal = ComparisonService(source, clock).create(
        left.record.id, scoped.record.id, operation_id="unequal"
    )
    assert unequal.outcomes.primary_counts["left_only"] == 11
    assert unequal.outcomes.primary_counts["changed_expectations"] == 1
    assert unequal.outcomes.quality_denominator == 0
    runner = ExecutionService(source, source, ProviderBackends(source, clock), clock)
    partial = asyncio.run(
        runner.start(
            RunRequest(
                decision_id=info.decision_id,
                dataset_id=info.dataset_id,
                mode="fixture",
                fixture_set_id=info.fixture_set_id,
                case_ids=("ex-002",),
            ),
            operation_id="partial",
            on_created=lambda created: runner.cancel(created.run_id, operation_id="cancel-partial"),
        )
    )
    old = evaluations.evaluate_saved(
        partial.run_id, partial.latest_result_snapshot_id, operation_id="partial-eval"
    )
    before = ComparisonService(source, clock).create(
        old.record.id, updated.record.id, operation_id="partial-comparison"
    )
    assert before.outcomes.quality_denominator == 0
    assert before.outcomes.left_status_counts["pending"] == 1
    asyncio.run(runner.resume(partial.run_id, operation_id="resume"))
    assert ComparisonService(source, clock).read(before.record.id).outcomes == before.outcomes
    datasets = DatasetService(source, clock)
    current_case = source.read(ResourceKey("cases", "ex-001", (info.dataset_id,)))
    datasets.edit_case(
        info.dataset_id,
        "ex-001",
        CaseInput(
            input_kind="json",
            input_source='{"text":"Changed after evaluation","context":{"source":"example"}}',
        ),
        expected_dataset_etag=datasets.read(info.dataset_id).etag,
        expected_case_etag=current_case.etag,
        operation_id="change-input",
    )
    changed_input = run(info.fixture_set_id, "changed-input-run", case_ids=("ex-001",))
    different = ComparisonService(source, clock).create(
        left.record.id, changed_input.record.id, operation_id="input-comparison"
    )
    assert different.outcomes.primary_counts["changed_input"] == 1
    assert different.outcomes.primary_counts["left_only"] == 11
    assert different.outcomes.quality_denominator == 0
    assert different.outcomes.right_exclusion_counts["stale"] == 1


def test_cli_explicit_and_default_evaluation_selection_is_zero_call(sandbox, monkeypatch):
    source, _, _, left, right, _ = sandbox
    from deykit.providers.choice import JevChoiceCompiler
    from deykit.providers.credentials import Credentials
    from deykit.providers.fixtures import FixtureCaseTransport
    from deykit.providers.jev import JevProvider

    def forbidden(*args, **kwargs):
        raise AssertionError("comparison may not compile, resolve credentials or dispatch")

    monkeypatch.setattr(JevProvider, "dispatch", forbidden)
    monkeypatch.setattr(Credentials, "resolve", forbidden)
    monkeypatch.setattr(FixtureCaseTransport, "dispatch", forbidden)
    monkeypatch.setattr(JevChoiceCompiler, "compile", forbidden)
    args = [
        "--project",
        str(source.root),
        "--json",
        "compare",
        left.record.run_id,
        right.record.run_id,
    ]
    default = CliRunner().invoke(app, [*args, "--operation-id", "default-compare"])
    assert default.exit_code == 0, default.output
    data = json.loads(default.stdout)["data"]
    assert (
        data["left_evaluation_id"] == left.record.id
        and data["right_evaluation_id"] == right.record.id
    )
    assert data["dispatch_count"] == 0 and data["outcomes"]["quality_denominator"] == 8
    pinned_args = [
        *args,
        "--evaluation-a",
        left.record.id,
        "--evaluation-b",
        right.record.id,
        "--operation-id",
        "pinned",
    ]
    pinned = CliRunner().invoke(app, pinned_args)
    assert pinned.exit_code == 0
    replay = CliRunner().invoke(app, pinned_args)
    assert replay.exit_code == 0 and json.loads(replay.stdout)["data"]["replayed"]
    wrong = CliRunner().invoke(app, [*args, "--evaluation-a", right.record.id])
    assert (
        wrong.exit_code == 2
        and json.loads(wrong.stdout)["error"]["reason"] == "evaluation_run_mismatch"
    )
