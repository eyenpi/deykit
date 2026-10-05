"""Create the installed, authored Sandbox project through portable application services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator

from deykit.application.dataset_support import identifier
from deykit.application.datasets import DatasetService
from deykit.application.definitions import DecisionService
from deykit.application.errors import ServiceFailure
from deykit.application.fixtures import FixtureService
from deykit.application.imports import ImportService
from deykit.application.projects import ProjectService, SourceFactory
from deykit.contracts.base import FrozenModel, Record
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import ResourceId, new_id
from deykit.contracts.json_value import (
    JsonDocument,
    JsonError,
    JsonSource,
    dump_json,
    semantic_hash,
)
from deykit.contracts.ports import Clock
from deykit.contracts.records import ChoiceDefinition, FixtureBinding, NormalizedAnswer
from deykit.domain.definitions import select_input
from deykit.domain.import_mapping import ImportMapping
from deykit.providers.choice import compile_choice


class SandboxCase(FrozenModel):
    id: ResourceId
    input_source: JsonSource
    label_option_id: ResourceId | None
    outcome: Literal["answer", "input_invalid", "response_error"]
    answer_option_id: ResourceId | None = None
    probabilities_source: JsonSource | None = None

    @model_validator(mode="after")
    def explicit_outcome(self) -> Self:
        if (self.outcome == "answer") != (self.answer_option_id is not None):
            raise ValueError("sandbox_answer_shape")
        if self.outcome != "answer" and self.probabilities_source is not None:
            raise ValueError("sandbox_probability_shape")
        if self.outcome == "input_invalid" and self.label_option_id is not None:
            raise ValueError("sandbox_invalid_label")
        return self


class SandboxCorpus(Record):
    evidence_mode: Literal["authored_fixture"]
    project_name: str = Field(min_length=1)
    decision_id: ResourceId
    decision_name: str = Field(min_length=1)
    dataset_id: ResourceId
    dataset_name: str = Field(min_length=1)
    profile_id: ResourceId
    fixture_set_id: ResourceId
    model_identity: str = Field(pattern=r"^authored-[A-Za-z0-9_-]+$")
    definition: ChoiceDefinition
    cases: tuple[SandboxCase, ...] = Field(min_length=12, max_length=12)

    @model_validator(mode="after")
    def unique_cases(self) -> Self:
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("duplicate_sandbox_case")
        return self


@dataclass(frozen=True)
class DemoInfo:
    path: Path
    project_id: str
    decision_id: str
    revision_id: str
    dataset_id: str
    profile_id: str
    fixture_set_id: str
    case_count: int
    binding_count: int
    label_count: int
    evidence_mode: Literal["authored_fixture"] = "authored_fixture"


def _invalid_corpus() -> ServiceFailure:
    return ServiceFailure(ServiceError(code="validation_error", reason="invalid_packaged_demo"))


def read_sandbox_corpus() -> SandboxCorpus:
    """The package resource is authored content; enforce its whole declared contract."""
    try:
        source = resources.files("deykit").joinpath("data/sandbox.json").read_bytes()
        corpus = load_record(SandboxCorpus, source)
        question = corpus.definition.questions[0]
        options = {option.id for option in question.options}
        for case in corpus.cases:
            if case.label_option_id is not None and case.label_option_id not in options:
                raise ValueError("unknown_sandbox_label")
            if case.answer_option_id is not None and case.answer_option_id not in options:
                raise ValueError("unknown_sandbox_answer")
            try:
                select_input(corpus.definition, JsonDocument(case.input_source))
            except JsonError as error:
                if case.outcome != "input_invalid" or error.code != "input_schema_mismatch":
                    raise ValueError("unexpected_sandbox_input") from None
            else:
                if case.outcome == "input_invalid":
                    raise ValueError("unexpected_valid_sandbox_input")
        return corpus
    except (OSError, JsonError, ValidationError, ValueError):
        raise _invalid_corpus() from None


def _import_source(corpus: SandboxCorpus) -> str:
    return "".join(
        dump_json({"id": case.id, "input": JsonDocument(case.input_source).value}) + "\n"
        for case in corpus.cases
    )


def _binding_sources(corpus: SandboxCorpus) -> tuple[bytes, ...]:
    result: list[bytes] = []
    question_id = corpus.definition.questions[0].id
    for case in corpus.cases:
        if case.outcome == "input_invalid":
            continue
        selected = select_input(corpus.definition, JsonDocument(case.input_source))
        request = compile_choice(
            corpus.definition, selected.value, corpus.model_identity, adapter="fixture"
        )
        answer = (
            NormalizedAnswer(
                question_id=question_id,
                option_id=case.answer_option_id,
                probabilities_source=case.probabilities_source,
                reported_model=corpus.model_identity,
            )
            if case.answer_option_id is not None
            else None
        )
        error = (
            ServiceError(code="response_invalid", reason="authored_response_error")
            if case.outcome == "response_error"
            else None
        )
        result.append(
            dump_record(
                FixtureBinding(
                    id=f"binding-{case.id}",
                    case_id=case.id,
                    request=request,
                    answer=answer,
                    error=error,
                )
            )
        )
    return tuple(result)


class DemoService:
    def __init__(
        self, source_factory: SourceFactory, clock: Clock, id_factory: Callable[[], str] = new_id
    ) -> None:
        self._factory, self._clock, self._id = source_factory, clock, id_factory

    def create(self, path: Path, *, operation_id: str) -> DemoInfo:
        """Create a new project directory; an existing path is never reused or overwritten."""
        identifier(operation_id)
        if not isinstance(path, Path):
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_demo_path")
            ) from None
        corpus = read_sandbox_corpus()
        try:
            import_source = _import_source(corpus)
            bindings = _binding_sources(corpus)
        except (JsonError, ValidationError, ValueError):
            raise _invalid_corpus() from None

        def phase(name: str) -> str:
            return "demo-" + semantic_hash({"operation": operation_id, "phase": name})[:32]

        try:
            path.mkdir()
        except FileExistsError:
            raise ServiceFailure(ServiceError(code="conflict", reason="demo_path_exists")) from None
        except OSError:
            raise ServiceFailure(
                ServiceError(code="internal_error", reason="demo_path_unavailable")
            ) from None

        project = ProjectService(self._factory, self._clock, self._id).create(
            path, corpus.project_name, phase("project")
        )
        source = self._factory(path, False)
        try:
            decisions = DecisionService(source, self._clock, self._id)
            created = decisions.create(
                corpus.decision_id,
                corpus.decision_name,
                dump_record(corpus.definition).decode("utf-8"),
                operation_id=phase("decision"),
            )
            saved = decisions.save(
                corpus.decision_id,
                expected_draft_etag=created.draft.etag,
                expected_decision_etag=created.decision.etag,
                operation_id=phase("revision"),
                note="Authored Sandbox definition",
            )
            datasets = DatasetService(source, self._clock, self._id)
            datasets.create(
                corpus.dataset_name,
                dataset_id=corpus.dataset_id,
                operation_id=phase("dataset"),
            )
            imports = ImportService(source, self._clock, self._id)
            preview = imports.preview(
                corpus.dataset_id,
                import_source,
                format="jsonl",
                mapping=ImportMapping(input_kind="json", input_column="input", id_column="id"),
            )
            if preview.exclusions or len(preview.valid_rows) != len(corpus.cases):
                raise _invalid_corpus()
            imported = imports.commit(preview, operation_id=phase("cases"))
            if set(imported.imported_case_ids) != {case.id for case in corpus.cases}:
                raise _invalid_corpus()

            # Expectations are separate from input and from authored model answers.
            from deykit.application.labels import LabelEdit, LabelService

            labels = LabelService(source, self._clock, self._id)
            edits = tuple(
                LabelEdit(
                    labels.read(corpus.decision_id, corpus.dataset_id, case.id).review,
                    "set",
                    (case.label_option_id,),
                    "authored_fixture",
                )
                for case in corpus.cases
                if case.label_option_id is not None
            )
            labels.batch(edits, operation_id=phase("labels"))

            fixtures = FixtureService(source, self._clock)
            fixtures.create_profile(
                corpus.profile_id, corpus.model_identity, operation_id=phase("profile")
            )
            fixture_set = fixtures.create(
                corpus.fixture_set_id,
                corpus.decision_id,
                corpus.dataset_id,
                "Authored Sandbox answers",
                corpus.model_identity,
                bindings,
                operation_id=phase("fixtures"),
                note="Authored examples; no live provider observations",
            )
            return DemoInfo(
                path=path,
                project_id=project.project.id,
                decision_id=corpus.decision_id,
                revision_id=saved.record.id,
                dataset_id=corpus.dataset_id,
                profile_id=corpus.profile_id,
                fixture_set_id=fixture_set.fixture_set.id,
                case_count=len(corpus.cases),
                binding_count=len(fixture_set.fixture_set.bindings),
                label_count=len(edits),
            )
        finally:
            source.close()
