import itertools

import pytest

from deykit.application.datasets import DatasetService
from deykit.application.imports import ImportService
from deykit.contracts.codec import dump_record
from deykit.contracts.ports import ResourceKey, SourceChange
from deykit.contracts.records import (
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    DecisionDraft,
    DecisionRecord,
    ProjectRecord,
)
from deykit.storage import FileProjectSource

STAMP = "2026-10-05T12:00:00Z"


class Clock:
    def utc_now(self):
        return STAMP

    def monotonic(self):
        return 0.0


def definition():
    return ChoiceDefinition(
        input_kind="json",
        selected_fields=("text",),
        input_schema_source=(
            '{"type":"object","properties":{"text":{"type":"string","minLength":1}},'
            '"required":["text"]}'
        ),
        questions=(
            ChoiceQuestion(
                id="category",
                instructions="Choose.",
                options=(ChoiceOption(id="A", name="Alpha"), ChoiceOption(id="B", name="Beta")),
            ),
        ),
    )


@pytest.fixture
def project(tmp_path):
    source = FileProjectSource(tmp_path / "project", create=True)
    source.commit(
        "project-create",
        (
            SourceChange(
                ResourceKey("project", "p"),
                dump_record(ProjectRecord(id="p", name="Test", created_at=STAMP)),
                None,
            ),
        ),
    )
    counter = itertools.count()

    def ids():
        return f"generated-{next(counter)}"

    datasets = DatasetService(source, Clock(), ids)
    dataset = datasets.create("Dataset", dataset_id="data", operation_id="dataset-create")
    source.commit(
        "decision-create",
        (
            SourceChange(
                ResourceKey("decisions", "decision"),
                dump_record(DecisionRecord(id="decision", name="Decision")),
                None,
            ),
            SourceChange(
                ResourceKey("drafts", "decision"),
                dump_record(
                    DecisionDraft(
                        decision_id="decision",
                        editor_source=dump_record(definition()).decode(),
                        updated_at=STAMP,
                    )
                ),
                None,
            ),
        ),
    )
    yield source, datasets, ImportService(source, Clock(), ids), dataset
    source.close()
