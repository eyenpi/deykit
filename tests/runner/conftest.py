import asyncio
import itertools
from datetime import UTC, datetime, timedelta

import pytest

from deykit.application.execution import ExecutionService
from deykit.contracts.codec import dump_record
from deykit.contracts.json_value import JsonDocument, dump_json
from deykit.contracts.ports import ResourceKey, SourceChange, StoredRecord
from deykit.contracts.records import (
    CaseRecord,
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    DatasetRecord,
    DecisionDraft,
    DecisionRecord,
    DispatchOutcome,
    FixtureBinding,
    FixtureSet,
    NormalizedAnswer,
    ProjectRecord,
    ProviderProfile,
)
from deykit.providers.choice import JevChoiceCompiler
from deykit.providers.fixtures import fixture_set_hash
from deykit.storage import FileProjectSource


class Clock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        return self.value

    def utc_now(self):
        return (
            (datetime(2026, 10, 5, tzinfo=UTC) + timedelta(seconds=self.value))
            .isoformat()
            .replace("+00:00", "Z")
        )

    async def wait(self, seconds):
        self.value += seconds
        await asyncio.sleep(0)


def answer():
    return DispatchOutcome(
        state="known",
        answer=NormalizedAnswer(question_id="q", option_id="yes", reported_model="authored-v1"),
    )


class Factory:
    compiler = JevChoiceCompiler()

    def __init__(self):
        self.calls = []
        self.error = None
        self.responses = {}
        self.callback = None
        self.profile_value = ProviderProfile(
            id="authored",
            adapter="fixture",
            requested_model="authored-v1",
            destination="fixture:jev-choice",
        )

    def profile(self, provider_id, fixture_set_id):
        return self.profile_value

    def profile_captured(self, provider_id, fixture_set_id, records: tuple[StoredRecord, ...]):
        return self.profile(provider_id, fixture_set_id)

    def resolve(self, profile, fixture_set_id):
        self.resolved_profile = profile
        return self

    def resolve_captured(self, profile, fixture_set_id, records: tuple[StoredRecord, ...]):
        return self.resolve(profile, fixture_set_id)

    def preflight(self, decision_id, dataset_id, definition=None):
        return self.error

    def for_case(self, case_id):
        factory = self

        class Transport:
            async def dispatch(self, request, *, timeout_seconds):
                factory.calls.append((case_id, request, timeout_seconds))
                if factory.callback:
                    return await factory.callback(case_id, request)
                scripted = factory.responses.get(case_id, [])
                return scripted.pop(0) if scripted else answer()

        return Transport()


def seed(source, count=3, invalid=()):
    stamp = "2026-10-05T00:00:00Z"
    definition = ChoiceDefinition(
        input_kind="json",
        selected_fields=("text",),
        input_schema_source='{"type":"object","required":["text"],"properties":{"text":{"type":"string"}}}',
        questions=(
            ChoiceQuestion(
                id="q",
                instructions="Choose.",
                options=(ChoiceOption(id="yes", name="Yes"), ChoiceOption(id="no", name="No")),
            ),
        ),
    )
    records = [
        (ResourceKey("project", "p"), ProjectRecord(id="p", name="Project", created_at=stamp)),
        (ResourceKey("decisions", "decision"), DecisionRecord(id="decision", name="Decision")),
        (
            ResourceKey("drafts", "decision"),
            DecisionDraft(
                decision_id="decision",
                editor_source=dump_record(definition).decode(),
                updated_at=stamp,
            ),
        ),
        (ResourceKey("datasets", "data"), DatasetRecord(id="data", name="Data", created_at=stamp)),
    ]
    for index in range(count):
        records.append(
            (
                ResourceKey("cases", f"case-{index:02}", ("data",)),
                CaseRecord(
                    id=f"case-{index:02}",
                    dataset_id="data",
                    input_kind="json",
                    input_source="{}"
                    if index in invalid
                    else dump_json({"text": f"Text {index}", "exact": 9007199254740993}),
                ),
            )
        )
    fixture_profile = ProviderProfile(
        id="authored",
        adapter="fixture",
        requested_model="authored-v1",
        destination="fixture:jev-choice",
    )
    compiler = JevChoiceCompiler()
    bindings = []
    for key, record in records:
        if key.collection != "cases" or record.input_source == "{}":
            continue
        selected = JsonDocument(record.input_source).value
        request = compiler.compile(definition, selected, fixture_profile)
        bindings.append(
            FixtureBinding(
                id=f"binding-{record.id}",
                case_id=record.id,
                request=request,
                answer=NormalizedAnswer(
                    question_id="q", option_id="yes", reported_model="authored-v1"
                ),
            )
        )
    if not bindings:
        request = compiler.compile(definition, {"text": "placeholder"}, fixture_profile)
        bindings.append(
            FixtureBinding(
                id="binding-placeholder",
                case_id="case-placeholder",
                request=request,
                answer=NormalizedAnswer(
                    question_id="q", option_id="yes", reported_model="authored-v1"
                ),
            )
        )
    incomplete_fixture = FixtureSet(
        id="set",
        decision_id="decision",
        dataset_id="data",
        name="Authored test fixtures",
        model_identity="authored-v1",
        bindings=tuple(bindings),
        content_hash="0" * 64,
        created_at=stamp,
    )
    fixture = incomplete_fixture.model_copy(
        update={"content_hash": fixture_set_hash(incomplete_fixture)}
    )
    records.append((ResourceKey("fixtures", "set"), fixture))
    source.commit(
        "seed", tuple(SourceChange(key, dump_record(record), None) for key, record in records)
    )


@pytest.fixture
def setup(tmp_path):
    opened = []

    def build(count=3, invalid=(), hook=None):
        path = tmp_path / f"project-{len(opened)}"
        source = FileProjectSource(path, create=True)
        opened.append(source)
        seed(source, count, invalid)
        clock, factory = Clock(), Factory()
        counter = itertools.count()
        service = ExecutionService(
            source,
            source,
            factory,
            clock,
            lambda: f"id-{next(counter):05}",
            waiter=clock,
            hook=hook,
        )
        return source, service, factory, clock

    yield build
    for source in opened:
        source.close()
