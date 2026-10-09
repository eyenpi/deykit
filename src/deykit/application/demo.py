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
from deykit.application.projects import ProjectBackend, ProjectService, SourceFactory
from deykit.contracts.base import FrozenModel, Record
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import ResourceId, new_id
from deykit.contracts.json_value import (
    JsonDocument,
    JsonError,
    JsonSource,
    bytes_hash,
    dump_json,
    semantic_hash,
)
from deykit.contracts.ports import Clock, CommitReceipt, SourceChange, StoredRecord
from deykit.contracts.records import (
    CaseRecord,
    ChoiceDefinition,
    DecisionDraft,
    DecisionRecord,
    DecisionRevision,
    DatasetRecord,
    FixtureBinding,
    FixtureSet,
    LabelChange,
    LabelRecord,
    NormalizedAnswer,
    ProjectRecord,
    ProviderProfile,
)
from deykit.domain.definitions import definition_hash, select_input
from deykit.domain.import_mapping import ImportMapping
from deykit.providers.choice import compile_choice
from deykit.providers.fixtures import (
    FIXTURE_DESTINATION,
    validate_fixture_profile,
    validate_fixture_set,
)


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
    operation_id: str
    replayed: bool
    evidence_mode: Literal["authored_fixture"] = "authored_fixture"


def _invalid_corpus() -> ServiceFailure:
    return ServiceFailure(ServiceError(code="validation_error", reason="invalid_packaged_demo"))


DEMO_OPERATION_INTENT = semantic_hash({"command": "demo.create", "demo_id": "sandbox"})


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
        self,
        source_factory: SourceFactory,
        clock: Clock,
        id_factory: Callable[[], str] = new_id,
        *,
        staging_factory: Callable[[], ProjectBackend],
    ) -> None:
        self._factory = source_factory
        self._clock, self._id = clock, id_factory
        self._staging_factory = staging_factory

    @staticmethod
    def _intent() -> str:
        return DEMO_OPERATION_INTENT

    def _stage(self, corpus: SandboxCorpus, operation_id: str) -> tuple[StoredRecord, ...]:
        try:
            import_source = _import_source(corpus)
            bindings = _binding_sources(corpus)
        except (JsonError, ValidationError, ValueError):
            raise _invalid_corpus() from None
        stage = self._staging_factory()

        def phase(name: str) -> str:
            return "demo-" + semantic_hash({"operation": operation_id, "phase": name})[:32]

        try:
            project = ProjectService(self._factory, self._clock, self._id).create_in(
                stage, corpus.project_name, phase("project")
            )
            decisions = DecisionService(stage, self._clock, self._id)
            created = decisions.create(
                corpus.decision_id,
                corpus.decision_name,
                dump_record(corpus.definition).decode("utf-8"),
                operation_id=phase("decision"),
            )
            decisions.save(
                corpus.decision_id,
                expected_draft_etag=created.draft.etag,
                expected_decision_etag=created.decision.etag,
                operation_id=phase("revision"),
                note="Authored Sandbox definition",
            )
            datasets = DatasetService(stage, self._clock, self._id)
            datasets.create(
                corpus.dataset_name,
                dataset_id=corpus.dataset_id,
                operation_id=phase("dataset"),
            )
            imports = ImportService(stage, self._clock, self._id)
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

            from deykit.application.labels import LabelEdit, LabelService

            labels = LabelService(stage, self._clock, self._id)
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
            fixtures = FixtureService(stage, self._clock)
            fixtures.create_profile(
                corpus.profile_id, corpus.model_identity, operation_id=phase("profile")
            )
            fixtures.create(
                corpus.fixture_set_id,
                corpus.decision_id,
                corpus.dataset_id,
                "Authored Sandbox answers",
                corpus.model_identity,
                bindings,
                operation_id=phase("fixtures"),
                note="Authored examples; no live provider observations",
            )
            if project.project.name != corpus.project_name:
                raise _invalid_corpus()
            return stage.capture_snapshot()
        except ServiceFailure:
            raise
        except (JsonError, ValidationError, ValueError):
            raise _invalid_corpus() from None
        finally:
            stage.close()

    @staticmethod
    def _incompatible_receipt() -> ServiceFailure:
        return ServiceFailure(
            ServiceError(code="incompatible_data", reason="invalid_demo_receipt")
        )

    def _admit_receipt(
        self,
        receipt: CommitReceipt,
        display_path: Path,
        *,
        operation_id: str,
        expected: tuple[StoredRecord, ...] | None = None,
    ) -> DemoInfo:
        try:
            if (
                receipt.operation_id != operation_id
                or any(
                    type(row.body) is not bytes
                    or type(row.etag) is not str
                    or row.etag != bytes_hash(row.body)
                    for row in receipt.changes
                )
                or receipt.deleted_keys
                or len({row.key for row in receipt.changes}) != len(receipt.changes)
            ):
                raise ValueError("invalid_demo_receipt")
            if expected is not None:
                expected_by_key = {row.key: (row.body, row.etag) for row in expected}
                actual_by_key = {row.key: (row.body, row.etag) for row in receipt.changes}
                if actual_by_key != expected_by_key:
                    raise ValueError("invalid_demo_receipt")
            def records(collection: str, scope: tuple[str, ...] = ()) -> tuple[StoredRecord, ...]:
                return tuple(
                    row
                    for row in receipt.changes
                    if row.key.collection == collection and row.key.scope == scope
                )

            project_rows = records("project")
            decision_rows = records("decisions")
            draft_rows = records("drafts")
            dataset_rows = records("datasets")
            if not all(
                len(rows) == 1
                for rows in (project_rows, decision_rows, draft_rows, dataset_rows)
            ):
                raise ValueError("invalid_demo_receipt")
            decision_id = decision_rows[0].key.resource_id
            revision_rows = records("revisions", (decision_id,))
            if len(revision_rows) != 1:
                raise ValueError("invalid_demo_receipt")
            allowed = {
                "project",
                "decisions",
                "drafts",
                "revisions",
                "datasets",
                "cases",
                "labels",
                "label_history",
                "providers",
                "fixtures",
            }
            if any(row.key.collection not in allowed for row in receipt.changes):
                raise ValueError("invalid_demo_receipt")
            expected_scope = {
                "project": (),
                "decisions": (),
                "drafts": (),
                "revisions": (decision_id,),
                "datasets": (),
                "providers": (),
                "fixtures": (),
            }
            if any(
                row.key.scope != expected_scope[row.key.collection]
                for row in receipt.changes
                if row.key.collection in expected_scope
            ):
                raise ValueError("invalid_demo_receipt")
            if any(
                row.key.scope != (dataset_rows[0].key.resource_id,)
                for row in receipt.changes
                if row.key.collection == "cases"
            ):
                raise ValueError("invalid_demo_receipt")
            if any(
                row.key.scope
                != (decision_id, dataset_rows[0].key.resource_id)
                for row in receipt.changes
                if row.key.collection in {"labels", "label_history"}
            ):
                raise ValueError("invalid_demo_receipt")
            project = load_record(ProjectRecord, project_rows[0].body)
            decision = load_record(DecisionRecord, decision_rows[0].body)
            draft = load_record(DecisionDraft, draft_rows[0].body)
            revision = load_record(DecisionRevision, revision_rows[0].body)
            dataset = load_record(DatasetRecord, dataset_rows[0].body)
            if any(
                row.key.resource_id != record.id
                for row, record in (
                    (project_rows[0], project),
                    (decision_rows[0], decision),
                    (revision_rows[0], revision),
                    (dataset_rows[0], dataset),
                )
            ):
                raise ValueError("invalid_demo_receipt")
            if draft_rows[0].key.resource_id != decision.id:
                raise ValueError("invalid_demo_receipt")
            if draft.decision_id != decision.id or revision.decision_id != decision.id:
                raise ValueError("invalid_demo_receipt")
            if (
                decision.latest_revision_id != revision.id
                or not isinstance(revision.definition, ChoiceDefinition)
                or definition_hash(revision.definition) != revision.content_hash
            ):
                raise ValueError("invalid_demo_receipt")
            case_rows = records("cases", (dataset.id,))
            label_rows = records("labels", (decision.id, dataset.id))
            label_history_rows = records("label_history", (decision.id, dataset.id))
            provider_rows = records("providers")
            fixture_rows = records("fixtures")
            if len(case_rows) != 12 or len(label_rows) != 9 or len(label_history_rows) != 9:
                raise ValueError("invalid_demo_receipt")
            if len(provider_rows) != 1 or len(fixture_rows) != 1:
                raise ValueError("invalid_demo_receipt")
            if len(records("cases")) or len(records("labels")) or len(records("label_history")):
                raise ValueError("invalid_demo_receipt")
            cases = {row.key.resource_id: load_record(CaseRecord, row.body) for row in case_rows}
            if len(cases) != 12:
                raise ValueError("invalid_demo_receipt")
            if any(
                case.id != row.key.resource_id or case.dataset_id != dataset.id
                for row in case_rows
                for case in (cases[row.key.resource_id],)
            ):
                raise ValueError("invalid_demo_receipt")
            profile = load_record(ProviderProfile, provider_rows[0].body)
            fixture_set = load_record(FixtureSet, fixture_rows[0].body)
            if (
                provider_rows[0].key.resource_id != profile.id
                or fixture_rows[0].key.resource_id != fixture_set.id
            ):
                raise ValueError("invalid_demo_receipt")
            validate_fixture_profile(profile)
            validate_fixture_set(fixture_set)
            if (
                profile.adapter != "fixture"
                or profile.destination != FIXTURE_DESTINATION
                or profile.credential_ref is not None
            ):
                raise ValueError("invalid_demo_receipt")
            if fixture_set.decision_id != decision.id or fixture_set.dataset_id != dataset.id:
                raise ValueError("invalid_demo_receipt")
            if profile.requested_model != fixture_set.model_identity:
                raise ValueError("invalid_demo_receipt")
            bound_ids = {binding.case_id for binding in fixture_set.bindings}
            if len(fixture_set.bindings) != 11 or len(bound_ids) != 11:
                raise ValueError("invalid_demo_receipt")
            if not bound_ids.issubset(cases):
                raise ValueError("invalid_demo_receipt")
            for case_id, case in cases.items():
                try:
                    selected = select_input(revision.definition, JsonDocument(case.input_source))
                except JsonError as error:
                    if error.code != "input_schema_mismatch" or case_id in bound_ids:
                        raise ValueError("invalid_demo_receipt") from None
                else:
                    if case_id not in bound_ids:
                        raise ValueError("invalid_demo_receipt")
                    binding = next(item for item in fixture_set.bindings if item.case_id == case_id)
                    request = compile_choice(
                        revision.definition,
                        selected.value,
                        fixture_set.model_identity,
                        adapter="fixture",
                    )
                    if dump_record(request) != dump_record(binding.request):
                        raise ValueError("invalid_demo_receipt")

            labels = tuple(load_record(LabelRecord, row.body) for row in label_rows)
            if any(
                row.key.resource_id != label.id
                for row, label in zip(label_rows, labels, strict=True)
            ):
                raise ValueError("invalid_demo_receipt")
            option_ids = {option.id for option in revision.definition.questions[0].options}
            if len({label.case_id for label in labels}) != 9 or any(
                label.provenance != "authored_fixture"
                or label.decision_id != decision.id
                or label.dataset_id != dataset.id
                or label.case_id not in cases
                or label.question_id != revision.definition.questions[0].id
                or label.input_hash
                != JsonDocument(cases[label.case_id].input_source).content_hash
                or len(label.acceptable_option_ids) != 1
                or not set(label.acceptable_option_ids).issubset(option_ids)
                for label in labels
            ):
                raise ValueError("invalid_demo_receipt")
            changes = tuple(load_record(LabelChange, row.body) for row in label_history_rows)
            if any(
                row.key.resource_id != change.id
                for row, change in zip(label_history_rows, changes, strict=True)
            ):
                raise ValueError("invalid_demo_receipt")
            label_by_case = {label.case_id: label for label in labels}
            if any(
                change.action != "set"
                or change.label is None
                or change.decision_id != decision.id
                or change.dataset_id != dataset.id
                or change.case_id not in cases
                or change.label.provenance != "authored_fixture"
                or label_by_case.get(change.case_id) != change.label
                or change.question_id != revision.definition.questions[0].id
                for change in changes
            ) or {change.case_id for change in changes} != set(label_by_case):
                raise ValueError("invalid_demo_receipt")
            return DemoInfo(
                display_path,
                project.id,
                decision.id,
                revision.id,
                dataset.id,
                profile.id,
                fixture_set.id,
                len(cases),
                len(fixture_set.bindings),
                len(labels),
                receipt.operation_id,
                receipt.replayed,
            )
        except (JsonError, ValidationError, ValueError, StopIteration, TypeError):
            raise self._incompatible_receipt() from None

    def _commit_staged(
        self,
        source: ProjectBackend,
        display_path: Path,
        operation_id: str,
        records: tuple[StoredRecord, ...],
    ) -> DemoInfo:
        intent = self._intent()
        with source.consistent_read():
            replay = source.operation_receipt(operation_id, intent_hash=intent)
            if replay is not None:
                return self._admit_receipt(replay, display_path, operation_id=operation_id)
            if source.capture_snapshot():
                raise ServiceFailure(ServiceError(code="conflict", reason="demo_path_exists"))
            changes = tuple(SourceChange(row.key, row.body, None) for row in records)
            receipt = source.commit(operation_id, changes, intent_hash=intent)
            return self._admit_receipt(
                receipt, display_path, operation_id=operation_id, expected=records
            )

    def create_in(
        self, source: ProjectBackend, display_path: Path, *, operation_id: str
    ) -> DemoInfo:
        identifier(operation_id)
        if not isinstance(display_path, Path):
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_demo_path")
            ) from None
        replay = source.operation_receipt(operation_id, intent_hash=self._intent())
        if replay is not None:
            return self._admit_receipt(replay, display_path, operation_id=operation_id)
        corpus = read_sandbox_corpus()
        records = self._stage(corpus, operation_id)
        return self._commit_staged(source, display_path, operation_id, records)

    def create(self, path: Path, *, operation_id: str) -> DemoInfo:
        """Create a fresh demo folder or replay its matching original receipt."""
        source, info = self._create_opened(path, operation_id=operation_id)
        source.close()
        return info

    def _create_opened(
        self, path: Path, *, operation_id: str
    ) -> tuple[ProjectBackend, DemoInfo]:
        """Create or replay a demo and return its source to a retaining caller."""
        identifier(operation_id)
        if not isinstance(path, Path):
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="invalid_demo_path")
            ) from None
        if path.exists():
            try:
                source = self._factory(path, False)
            except (OSError, ServiceFailure):
                raise ServiceFailure(
                    ServiceError(code="conflict", reason="demo_path_exists")
                ) from None
            try:
                receipt = source.operation_receipt(operation_id, intent_hash=self._intent())
                if receipt is None:
                    raise ServiceFailure(ServiceError(code="conflict", reason="demo_path_exists"))
                return source, self._admit_receipt(receipt, path, operation_id=operation_id)
            except BaseException:
                source.close()
                raise
        corpus = read_sandbox_corpus()
        records = self._stage(corpus, operation_id)
        try:
            path.mkdir()
        except FileExistsError:
            raise ServiceFailure(ServiceError(code="conflict", reason="demo_path_exists")) from None
        except OSError:
            raise ServiceFailure(
                ServiceError(code="internal_error", reason="demo_path_unavailable")
            ) from None
        source = self._factory(path, True)
        try:
            return source, self._commit_staged(source, path, operation_id, records)
        except BaseException:
            source.close()
            raise
