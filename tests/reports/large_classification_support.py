"""Authored 2,500-case runner evidence persisted for report CLI regressions."""

import asyncio
import json
from contextlib import ExitStack, contextmanager
from decimal import Decimal
from pathlib import Path

from test_reports import MemorySnapshotSource

from deykit.application.evaluations import EvaluationService
from deykit.application.execution import ExecutionService
from deykit.cli.context import SystemClock
from deykit.contracts.codec import dump_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import JsonDocument, dump_json
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import (
    CaseRecord,
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    DatasetRecord,
    DecisionDraft,
    DecisionRecord,
    DispatchOutcome,
    ExecutionSettings,
    FixtureBinding,
    FixtureSet,
    LabelRecord,
    NormalizedAnswer,
    ProjectRecord,
    ProviderProfile,
)
from deykit.domain.definitions import select_input
from deykit.domain.label_identity import label_id
from deykit.providers.choice import JevChoiceCompiler
from deykit.providers.fixtures import fixture_set_hash
from deykit.runner.planner import RunRequest
from deykit.storage import FileProjectSource

COUNT = 2500
OPTIONS = tuple(f"category-{i:03}" for i in range(104))


class AuthoredExecutionSource(MemorySnapshotSource):
    """Prepare report evidence without repeating filesystem execution benchmarks."""

    active = False

    def read(self, key):
        return self.records.get(key)

    def read_records(self):
        return self.capture_snapshot()

    @contextmanager
    def execution_owner(self):
        assert not self.active
        self.active = True
        try:
            yield
        finally:
            self.active = False

    def execution_active(self):
        return self.active

    def cancellation_requested(self, run_id):
        return False

    def acknowledge_cancel(self, run_id, segment_id):
        raise AssertionError("Fixture setup does not request cancellation.")


def probabilities(chosen, *, dense=False):
    return dump_json(
        {
            option: (
                Decimal("0.9872839507317331") if option == chosen else Decimal("0.0001234567890123")
            )
            if dense
            else int(option == chosen)
            for option in OPTIONS
        }
    )


class AuthoredBackends:
    compiler = JevChoiceCompiler()

    def __init__(self, mistakes=frozenset(), *, dense=False):
        self.calls = 0
        self.mistakes = mistakes
        self.dense = dense
        self.profile_value = ProviderProfile(
            id="authored",
            adapter="fixture",
            requested_model="authored-report-scale-v1",
            destination="fixture:jev-choice",
        )

    def profile_captured(self, provider_id, fixture_set_id, records):
        return self.profile_value

    def profile(self, provider_id, fixture_set_id):
        return self.profile_value

    def resolve(self, profile, fixture_set_id):
        return self

    def resolve_captured(self, profile, fixture_set_id, records):
        return self

    def preflight(self, decision_id, dataset_id, definition=None):
        return None

    def for_case(self, case_id):
        parent = self
        index = int(case_id.removeprefix("product-"))

        class Transport:
            async def dispatch(self, request, *, timeout_seconds):
                parent.calls += 1
                if index < 2:
                    return DispatchOutcome(
                        state="unknown" if index == 0 else "known",
                        error=ServiceError(
                            code="provider_rejected" if index == 0 else "response_invalid",
                            reason="authored_unknown" if index == 0 else "authored_invalid",
                        ),
                    )
                chosen = OPTIONS[(index + (index in parent.mistakes)) % len(OPTIONS)]
                return DispatchOutcome(
                    state="known",
                    answer=NormalizedAnswer(
                        question_id="category",
                        option_id=chosen,
                        reported_model=parent.profile_value.requested_model,
                        probabilities_source=probabilities(chosen, dense=parent.dense),
                    ),
                )

        return Transport()


def build_large_evidence(root: Path, *, paired=False):
    receipt_path = root.parent / f"{root.name}-evidence.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        assert receipt["count"] == COUNT and receipt["option_count"] == len(OPTIONS)
        assert receipt.get("paired", False) == paired
        return receipt
    assert not root.exists(), "Interrupted fixture setup: choose a new project directory."
    stamp = "2026-10-21T00:00:00Z"
    clock = SystemClock()
    backend = AuthoredBackends(frozenset({2, 4}) if paired else frozenset(), dense=paired)
    definition = ChoiceDefinition(
        input_kind="json",
        selected_fields=("text",),
        input_schema_source='{"type":"object","required":["text"],"properties":{"text":{"type":"string"}}}',
        questions=(
            ChoiceQuestion(
                id="category",
                instructions="Choose the product category.",
                options=tuple(ChoiceOption(id=option, name=option) for option in OPTIONS),
            ),
        ),
    )
    records = [
        (
            ResourceKey("project", "p"),
            ProjectRecord(id="p", name="Authored report scale", created_at=stamp),
        ),
        (
            ResourceKey("decisions", "decision"),
            DecisionRecord(id="decision", name="Product category"),
        ),
        (
            ResourceKey("drafts", "decision"),
            DecisionDraft(
                decision_id="decision",
                editor_source=dump_record(definition).decode(),
                updated_at=stamp,
            ),
        ),
        (
            ResourceKey("datasets", "data"),
            DatasetRecord(id="data", name="Products", created_at=stamp),
        ),
    ]
    for index in range(COUNT):
        case_id = f"product-{index:04}"
        case = CaseRecord(
            id=case_id,
            dataset_id="data",
            input_kind="json",
            input_source=dump_json(
                {"text": f"Authored product {index}", "exact": 9007199254740993}
            ),
        )
        records.append((ResourceKey("cases", case_id, ("data",)), case))
        if index != COUNT - 1:
            identity = label_id(case_id, "category")
            records.append(
                (
                    ResourceKey("labels", identity, ("decision", "data")),
                    LabelRecord(
                        id=identity,
                        decision_id="decision",
                        dataset_id="data",
                        case_id=case_id,
                        question_id="category",
                        input_hash=JsonDocument(case.input_source).content_hash,
                        acceptable_option_ids=(OPTIONS[index % len(OPTIONS)],),
                        provenance="authored_fixture",
                        updated_at=stamp,
                        status="disputed" if index == COUNT - 2 else "active",
                    ),
                )
            )
    # The injected transport authors all responses. Keep a small valid fixture
    # profile rather than storing thousands of duplicate compiled bindings.
    request = backend.compiler.compile(
        definition,
        select_input(definition, JsonDocument('{"text":"placeholder"}')).value,
        backend.profile_value,
    )
    fixture = FixtureSet(
        id="fixture",
        decision_id="decision",
        dataset_id="data",
        name="Controlled authored transport",
        model_identity=backend.profile_value.requested_model,
        bindings=(
            FixtureBinding(
                id="placeholder",
                case_id="placeholder",
                request=request,
                answer=NormalizedAnswer(
                    question_id="category",
                    option_id=OPTIONS[0],
                    reported_model=backend.profile_value.requested_model,
                ),
            ),
        ),
        content_hash="0" * 64,
        created_at=stamp,
    )
    fixture = fixture.model_copy(update={"content_hash": fixture_set_hash(fixture)})
    records.append((ResourceKey("fixtures", "fixture"), fixture))
    with ExitStack() as stack:
        source = (
            AuthoredExecutionSource({})
            if paired
            else stack.enter_context(FileProjectSource(root, create=True))
        )
        source.commit(
            "large-seed",
            tuple(SourceChange(key, dump_record(record), None) for key, record in records),
        )
        runner = ExecutionService(source, source, backend, clock)
        request = RunRequest(
            decision_id="decision",
            dataset_id="data",
            mode="fixture",
            fixture_set_id="fixture",
            settings=ExecutionSettings(max_attempts=COUNT, concurrency=32, deadline_seconds=86400),
        )
        preview = runner.preview(request)
        assert len(preview.selected_case_ids) == preview.initial_requests == COUNT
        result = asyncio.run(runner.start(request, operation_id="large-run"))
        assert result.attempts_used == backend.calls == COUNT
        assert result.latest_result_snapshot_id is not None
        evaluation = EvaluationService(source, clock).evaluate_saved(
            result.run_id, result.latest_result_snapshot_id, operation_id="large-evaluate"
        )
        receipt = {
            "count": COUNT,
            "option_count": len(OPTIONS),
            "calls": backend.calls,
            "run_id": result.run_id,
            "evaluation_id": evaluation.record.id,
            "evidence_mode": "controlled_authored_transport",
            "paired": paired,
        }
        if paired:
            backend.mistakes = frozenset({3, 4})
            right = asyncio.run(runner.start(request, operation_id="large-run-right"))
            assert right.attempts_used == COUNT and backend.calls == 2 * COUNT
            right_evaluation = EvaluationService(source, clock).evaluate_saved(
                right.run_id,
                right.latest_result_snapshot_id,
                operation_id="large-evaluate-right",
            )
            receipt.update(
                right_run_id=right.run_id,
                right_evaluation_id=right_evaluation.record.id,
                calls=backend.calls,
            )
            with FileProjectSource(root, create=True) as target:
                target.commit(
                    "authored-paired-evidence",
                    tuple(
                        SourceChange(record.key, record.body, None)
                        for record in source.capture_snapshot()
                    ),
                )
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt
