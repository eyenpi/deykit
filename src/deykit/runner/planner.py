"""Local preflight: capture consistent source, compile exact requests, freeze no mutable views."""

from dataclasses import dataclass
from typing import Literal, Self, cast

from pydantic import model_validator

from deykit.application.dataset_support import (
    decoded,
    fail,
    fingerprint,
    safe_hash,
    validated_model,
)
from deykit.contracts.base import FrozenModel
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import ResourceId
from deykit.contracts.json_value import JsonDocument, JsonError, JsonValue, bytes_hash
from deykit.contracts.ports import ResourceKey, SnapshotSource, StoredRecord
from deykit.contracts.records import (
    CaseRecord,
    ChoiceDefinition,
    CompiledRequest,
    DatasetRecord,
    DecisionDraft,
    DecisionRecord,
    DecisionRevision,
    ExecutionSettings,
    LabelRecord,
    ProviderProfile,
)
from deykit.domain.definitions import definition_hash, select_input
from deykit.domain.label_identity import label_id
from deykit.runner.ports import BackendFactory

MAX_CASES = 10_000
MAX_PLAN_BYTES = 32 * 1024 * 1024


class RunRequest(FrozenModel):
    decision_id: ResourceId
    dataset_id: ResourceId
    mode: Literal["fixture", "live"]
    provider_id: ResourceId | None = None
    fixture_set_id: ResourceId | None = None
    revision_id: ResourceId | None = None
    split: Literal["all", "development", "calibration", "test"] = "all"
    case_ids: tuple[ResourceId, ...] = ()
    settings: ExecutionSettings = ExecutionSettings()

    @model_validator(mode="after")
    def explicit_mode(self) -> Self:
        if self.mode == "fixture" and self.fixture_set_id is None:
            raise ValueError("fixture_set_required")
        if self.mode == "live" and (self.provider_id is None or self.fixture_set_id is not None):
            raise ValueError("live_profile_required")
        if len(self.case_ids) != len(set(self.case_ids)):
            raise ValueError("duplicate_selected_case")
        if self.settings.timeout_seconds > 600 or self.settings.concurrency > 64:
            raise ValueError("execution_resource_limit")
        return self


def validate_request(value: RunRequest) -> RunRequest:
    return validated_model(RunRequest, value, "invalid_run_request")


def start_intent(request: RunRequest) -> str:
    return safe_hash(
        {"command": "run.start", "request": cast(JsonValue, request.model_dump(mode="json"))}
    )


@dataclass(frozen=True)
class PlannedCase:
    case_id: str
    input_hash: str
    request: CompiledRequest | None
    error: ServiceError | None


@dataclass(frozen=True)
class RunPlan:
    selection: RunRequest
    definition: ChoiceDefinition
    definition_hash: str
    cases: tuple[CaseRecord, ...]
    labels: tuple[LabelRecord, ...]
    development_cases: tuple[CaseRecord, ...]
    development_labels: tuple[LabelRecord, ...]
    provider: ProviderProfile
    prepared: tuple[PlannedCase, ...]
    context_hash: str

    @property
    def initial_requests(self) -> int:
        return sum(item.request is not None for item in self.prepared)


class Planner:
    def __init__(self, source: SnapshotSource, backends: BackendFactory) -> None:
        self.source, self.backends = source, backends

    def _capture(self, request: RunRequest) -> tuple[StoredRecord, ...]:
        captured = self.source.capture_snapshot()
        index = {record.key: record for record in captured}
        keys = [
            ResourceKey("decisions", request.decision_id),
            ResourceKey("datasets", request.dataset_id),
            ResourceKey("revisions", request.revision_id, (request.decision_id,))
            if request.revision_id
            else ResourceKey("drafts", request.decision_id),
        ]
        if request.provider_id:
            keys.append(ResourceKey("providers", request.provider_id))
        if any(key not in index for key in keys):
            fail("run_source_missing", "preflight_failed")
        records = [index[key] for key in keys[:3]]
        records.extend(
            record
            for record in captured
            if (record.key.collection == "cases" and record.key.scope == (request.dataset_id,))
            or (
                record.key.collection == "labels"
                and record.key.scope == (request.decision_id, request.dataset_id)
            )
        )
        records.extend(index[key] for key in keys[3:])
        return tuple(records)

    def check_context(self, plan: RunPlan) -> None:
        if fingerprint(self._capture(plan.selection)) != plan.context_hash:
            fail("run_source_changed", "conflict")

    def prepare(self, request: RunRequest) -> RunPlan:
        request = validate_request(request)
        with self.source.consistent_read():
            records = self._capture(request)
            profile = self.backends.profile(request.provider_id, request.fixture_set_id)
        decision = decoded(DecisionRecord, records[0])
        dataset = decoded(DatasetRecord, records[1])
        if decision.archived or dataset.archived:
            fail("archived_run_source", "preflight_failed")
        try:
            if request.revision_id:
                revision = decoded(DecisionRevision, records[2])
                definition = revision.definition
                if definition_hash(definition) != revision.content_hash:
                    fail("revision_hash_mismatch", "preflight_failed")
            else:
                draft = decoded(DecisionDraft, records[2])
                definition = load_record(ChoiceDefinition, draft.editor_source)
        except JsonError as error:
            fail(error.code, "preflight_failed")
        all_cases = tuple(
            decoded(CaseRecord, item) for item in records if item.key.collection == "cases"
        )
        if len(all_cases) > MAX_CASES:
            fail("run_resource_limit", "preflight_failed")
        if any(case_id not in {case.id for case in all_cases} for case_id in request.case_ids):
            fail("selected_case_missing", "preflight_failed")
        cases = tuple(
            case
            for case in all_cases
            if (not request.case_ids or case.id in request.case_ids)
            and (request.split == "all" or case.split == request.split)
        )
        if not cases:
            fail("empty_run_scope", "preflight_failed")
        all_labels = tuple(
            decoded(LabelRecord, item) for item in records if item.key.collection == "labels"
        )
        if any(label.id != label_id(label.case_id, label.question_id) for label in all_labels):
            fail("label_identity_mismatch", "preflight_failed")
        selected_ids = {case.id for case in cases}
        development = tuple(case for case in all_cases if case.split == "development")
        development_ids = {case.id for case in development}
        if profile.adapter != ("fixture" if request.mode == "fixture" else "jev"):
            fail("provider_mode_mismatch", "preflight_failed")
        backend = self.backends.resolve(profile, request.fixture_set_id)
        preflight_error = backend.preflight(request.decision_id, request.dataset_id)
        if preflight_error is not None:
            fail(preflight_error.reason or "provider_preflight_failed", "preflight_failed")
        prepared: list[PlannedCase] = []
        for case in cases:
            document = JsonDocument(case.input_source)
            try:
                selected = select_input(definition, document)
            except JsonError as error:
                prepared.append(
                    PlannedCase(
                        case.id,
                        document.content_hash,
                        None,
                        ServiceError(
                            code="validation_error", resource_id=case.id, reason=error.code
                        ),
                    )
                )
                continue
            try:
                compiled = backend.compiler.compile(definition, selected.value, profile)
            except ValueError:
                fail("unsupported_request_configuration", "preflight_failed")
            prepared.append(PlannedCase(case.id, document.content_hash, compiled, None))
        if sum(item.request is not None for item in prepared) > request.settings.max_attempts:
            fail("initial_requests_exceed_cap", "preflight_failed")
        # Bound all copied evidence, including the separate fitting-source capture.
        total = sum(len(item.body) for item in records)
        total += sum(len(dump_record(item.request)) for item in prepared if item.request)
        if total > MAX_PLAN_BYTES:
            fail("run_resource_limit", "preflight_failed")
        return RunPlan(
            request,
            definition,
            definition_hash(definition),
            cases,
            tuple(label for label in all_labels if label.case_id in selected_ids),
            development,
            tuple(label for label in all_labels if label.case_id in development_ids),
            profile,
            tuple(prepared),
            fingerprint(records),
        )


def evidence_hash(bodies: tuple[bytes, ...]) -> str:
    """Length-independent exact envelope identity; user values stay source strings."""
    return bytes_hash("\n".join(bytes_hash(body) for body in bodies).encode("ascii"))
