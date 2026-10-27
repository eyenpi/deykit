"""Local preflight: capture consistent source, compile exact requests, freeze no mutable views."""

from dataclasses import dataclass
from typing import Literal, Self, cast

from pydantic import ValidationError, model_validator

from deykit.application.dataset_support import (
    decoded,
    fail,
    fingerprint,
    safe_hash,
    validated_model,
)
from deykit.application.errors import ServiceFailure
from deykit.application.images import ImageAssets
from deykit.contracts.base import FrozenModel
from deykit.contracts.codec import dump_record, load_record
from deykit.contracts.errors import ServiceError
from deykit.contracts.evidence import evidence_hash as evidence_hash
from deykit.contracts.execution_groups import RegressionRemoval
from deykit.contracts.identities import ResourceId
from deykit.contracts.json_value import JsonDocument, JsonError, JsonValue, bytes_hash
from deykit.contracts.ports import (
    CompilerIdentity,
    ImageChoiceCompiler,
    ResourceKey,
    SnapshotSource,
    StoredRecord,
)
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
    RegressionRecord,
)
from deykit.domain.case_identity import case_input_hash
from deykit.domain.definitions import definition_hash, select_input
from deykit.domain.label_identity import label_id
from deykit.regressions.evidence import frozen_case
from deykit.runner.ports import Backend, BackendFactory

MAX_CASES = 10_000
MAX_PLAN_BYTES = 32 * 1024 * 1024
MAX_EXPERIMENT_PLAN_BYTES = 512 * 1024 * 1024


class RunRequest(FrozenModel):
    decision_id: ResourceId
    dataset_id: ResourceId
    mode: Literal["fixture", "live"]
    provider_id: ResourceId | None = None
    fixture_set_id: ResourceId | None = None
    revision_id: ResourceId | None = None
    split: Literal["all", "development", "calibration", "test"] = "all"
    case_ids: tuple[ResourceId, ...] = ()
    option_order: tuple[ResourceId, ...] | None = None
    regression_ids: tuple[ResourceId, ...] = ()
    settings: ExecutionSettings = ExecutionSettings()

    @model_validator(mode="after")
    def explicit_mode(self) -> Self:
        if self.mode == "fixture" and self.fixture_set_id is None:
            raise ValueError("fixture_set_required")
        if self.mode == "live" and (self.provider_id is None or self.fixture_set_id is not None):
            raise ValueError("live_profile_required")
        if len(self.case_ids) != len(set(self.case_ids)):
            raise ValueError("duplicate_selected_case")
        if len(set(self.regression_ids)) != len(self.regression_ids):
            raise ValueError("duplicate_regression_selection")
        if self.regression_ids and (self.case_ids or self.split != "all"):
            raise ValueError("regression_selection_override")
        if self.settings.timeout_seconds > 600 or self.settings.concurrency > 64:
            raise ValueError("execution_resource_limit")
        return self


def validate_request(value: RunRequest) -> RunRequest:
    return validated_model(RunRequest, value, "invalid_run_request")


def start_intent(request: RunRequest, expected_review_context_hash: str | None = None) -> str:
    if expected_review_context_hash is not None:
        from deykit.runner.review import validate_review_hash

        validate_review_hash(expected_review_context_hash)
        return safe_hash(
            {
                "command": "run.start.reviewed-v1",
                "request": cast(JsonValue, request.model_dump(mode="json")),
                "expected_review_context_hash": expected_review_context_hash,
            }
        )
    return safe_hash(
        {"command": "run.start", "request": cast(JsonValue, request.model_dump(mode="json"))}
    )


def _exact_records(
    records: tuple[StoredRecord, ...],
) -> tuple[tuple[str, tuple[str, ...], str, str, str], ...]:
    return tuple(
        (
            item.key.collection,
            item.key.scope,
            item.key.resource_id,
            item.etag,
            bytes_hash(item.body),
        )
        for item in sorted(
            records,
            key=lambda item: (item.key.collection, item.key.scope, item.key.resource_id),
        )
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
    review_records: tuple[StoredRecord, ...]
    review_compiler: CompilerIdentity
    plan_bytes: int = 0

    @property
    def initial_requests(self) -> int:
        return sum(item.request is not None for item in self.prepared)


def trusted_request(value: CompiledRequest, profile: ProviderProfile) -> CompiledRequest:
    if type(value) is not CompiledRequest:
        fail("invalid_compiled_request", "preflight_failed")
    raw = vars(value)
    if any(type(item) not in (str, int, bytes) for item in raw.values()):
        fail("invalid_compiled_request", "preflight_failed")
    try:
        for item in raw.values():
            if type(item) is str:
                item.encode("utf-8", "strict")
        request = CompiledRequest.model_validate(raw)
    except (UnicodeError, ValidationError):
        fail("invalid_compiled_request", "preflight_failed")
    if (request.adapter, request.destination, request.requested_model) != (
        profile.adapter,
        profile.destination,
        profile.requested_model,
    ):
        fail("compiled_profile_mismatch", "preflight_failed")
    return request


class Planner:
    def __init__(self, source: SnapshotSource, backends: BackendFactory) -> None:
        self.source, self.backends = source, backends

    def _capture(
        self, request: RunRequest, captured: tuple[StoredRecord, ...] | None = None
    ) -> tuple[StoredRecord, ...]:
        if captured is None:
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
        if request.fixture_set_id:
            keys.append(ResourceKey("fixtures", request.fixture_set_id))
        if any(key not in index for key in keys):
            fail("run_source_missing", "preflight_failed")
        records = [index[key] for key in keys[:3]]
        records.extend(
            record
            for record in captured
            if not request.regression_ids
            and (
                (record.key.collection == "cases" and record.key.scope == (request.dataset_id,))
                or (
                    record.key.collection == "labels"
                    and record.key.scope == (request.decision_id, request.dataset_id)
                )
            )
        )
        records.extend(index[key] for key in keys[3:])
        for regression_id in request.regression_ids:
            key = ResourceKey("regressions", regression_id)
            if key not in index:
                fail("selected_regression_missing", "preflight_failed")
            records.append(index[key])
        if request.regression_ids:
            from deykit.application.regressions import visible_regressions
            from deykit.regressions.evidence import admit_regression_origin

            visible = {r.id: r for r in visible_regressions(captured, request.decision_id)}
            for regression_id in request.regression_ids:
                if regression_id not in visible:
                    fail("regression_not_visible", "preflight_failed")
                admit_regression_origin(captured, visible[regression_id])
            records.extend(
                r
                for r in captured
                if r.key.collection == "regression_removals"
                and decoded(RegressionRemoval, r).regression_id in request.regression_ids
            )
        # Assets remain separate from case JSON and are pinned by immutable IDs.
        asset_cases = [
            decoded(CaseRecord, record) for record in records if record.key.collection == "cases"
        ]
        asset_cases.extend(
            frozen_case(decoded(RegressionRecord, record))
            for record in records
            if record.key.collection == "regressions"
        )
        asset_ids = {image.asset_id for case in asset_cases for image in case.images}
        for asset_id in sorted(asset_ids):
            key = ResourceKey("image_assets", asset_id)
            if key not in index:
                fail("image_asset_missing", "preflight_failed")
            records.append(index[key])
        return tuple(records)

    def check_context(self, plan: RunPlan) -> None:
        from deykit.application.errors import ServiceFailure

        try:
            current = self._capture(plan.selection)
        except ServiceFailure:
            fail("run_source_changed", "conflict")
        if fingerprint(current) != plan.context_hash or _exact_records(current) != _exact_records(
            plan.review_records
        ):
            fail("run_source_changed", "conflict")

    def prepare(self, request: RunRequest) -> RunPlan:
        request = validate_request(request)
        with self.source.consistent_read():
            captured = self.source.capture_snapshot()
            records = self._capture(request, captured)
            profile = self.backends.profile_captured(
                request.provider_id, request.fixture_set_id, captured
            )
        backend = self.backends.resolve_captured(profile, request.fixture_set_id, captured)
        return self._prepare(request, records, profile, backend)

    def prepare_many(
        self,
        requests: tuple[RunRequest, ...],
        *,
        captured: tuple[StoredRecord, ...] | None = None,
        allow_partial: bool = False,
        max_plan_bytes: int | None = None,
        max_total_plan_bytes: int | None = None,
        allow_missing_credentials: bool = False,
    ) -> tuple[RunPlan, ...]:
        """All member plans read a single source epoch before any compilation or writes."""
        requests = tuple(validate_request(request) for request in requests)
        with self.source.consistent_read():
            if captured is None:
                captured = self.source.capture_snapshot()
        plans: list[RunPlan] = []
        total = 0
        for request in requests:
            records = self._capture(request, captured)
            profile = self.backends.profile_captured(
                request.provider_id, request.fixture_set_id, captured
            )
            backend = self.backends.resolve_captured(profile, request.fixture_set_id, captured)
            limit = max_plan_bytes
            if max_total_plan_bytes is not None:
                remaining = max_total_plan_bytes - total
                if remaining <= 0:
                    fail("execution_group_resource_limit", "preflight_failed")
                limit = remaining if limit is None else min(limit, remaining)
            try:
                plan = self._prepare(
                    request,
                    records,
                    profile,
                    backend,
                    allow_partial=allow_partial,
                    max_plan_bytes=limit,
                    allow_missing_credentials=allow_missing_credentials,
                )
            except ServiceFailure as error:
                if max_total_plan_bytes is not None and error.error.reason == "run_resource_limit":
                    fail("execution_group_resource_limit", "preflight_failed")
                raise
            plans.append(plan)
            total += plan.plan_bytes
        return tuple(plans)

    def prepare_orders(self, request: RunRequest, *, orders: int, seed: int) -> tuple[RunPlan, ...]:
        from deykit.diagnostics.orders import DiagnosticInvalid, choice_orders

        request = validate_request(request)
        if request.option_order is not None or request.regression_ids:
            fail("diagnostic_selection_override", "preflight_failed")
        with self.source.consistent_read():
            captured = self.source.capture_snapshot()
            records = self._capture(request, captured)
            profile = self.backends.profile_captured(
                request.provider_id, request.fixture_set_id, captured
            )
        backend = self.backends.resolve_captured(profile, request.fixture_set_id, captured)
        original = self._prepare(request, records, profile, backend)
        try:
            expanded = choice_orders(
                tuple(option.id for option in original.definition.questions[0].options),
                orders=orders,
                seed=seed,
            )
        except DiagnosticInvalid:
            fail("invalid_diagnostic_orders", "preflight_failed")
        return tuple(
            self._prepare(
                validate_request(request.model_copy(update={"option_order": order})),
                records,
                profile,
                backend,
            )
            for order in expanded
        )

    def check_contexts(self, plans: tuple[RunPlan, ...]) -> None:
        from deykit.application.errors import ServiceFailure

        captured = self.source.capture_snapshot()
        for plan in plans:
            try:
                context = self._capture(plan.selection, captured)
            except ServiceFailure:
                fail("run_source_changed", "conflict")
            if fingerprint(context) != plan.context_hash or _exact_records(
                context
            ) != _exact_records(plan.review_records):
                fail("run_source_changed", "conflict")

    def _prepare(
        self,
        request: RunRequest,
        records: tuple[StoredRecord, ...],
        profile: ProviderProfile,
        backend: Backend,
        *,
        allow_partial: bool = False,
        max_plan_bytes: int | None = None,
        allow_missing_credentials: bool = False,
    ) -> RunPlan:
        plan_limit = MAX_PLAN_BYTES if max_plan_bytes is None else max_plan_bytes
        profile = validated_model(ProviderProfile, profile, "invalid_provider_profile")
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
        compile_definition = definition
        if request.option_order is not None:
            question = definition.questions[0]
            options = {option.id: option for option in question.options}
            if len(request.option_order) != len(options) or set(request.option_order) != set(
                options
            ):
                fail("invalid_option_order", "preflight_failed")
            compile_definition = definition.model_copy(
                update={
                    "questions": (
                        question.model_copy(
                            update={"options": tuple(options[key] for key in request.option_order)}
                        ),
                    )
                }
            )
            compile_definition = validated_model(
                ChoiceDefinition, compile_definition, "invalid_option_order"
            )
        all_cases = tuple(
            decoded(CaseRecord, item) for item in records if item.key.collection == "cases"
        )
        if request.regression_ids:
            regressions = tuple(
                decoded(RegressionRecord, item)
                for item in records
                if item.key.collection == "regressions"
            )
            frozen_cases: dict[str, CaseRecord] = {}
            question = definition.questions[0]
            for regression in regressions:
                case = frozen_case(regression)
                if (
                    regression.decision_id != request.decision_id
                    or regression.dataset_id != request.dataset_id
                    or regression.question_id != question.id
                    or not set(regression.acceptable_option_ids).issubset(
                        option.id for option in question.options
                    )
                ):
                    fail("incompatible_regression", "preflight_failed")
                try:
                    select_input(definition, JsonDocument(case.input_source))
                except JsonError:
                    fail("incompatible_regression_input", "preflight_failed")
                if case.id in frozen_cases and frozen_cases[case.id] != case:
                    fail("conflicting_regression_versions", "preflight_failed")
                frozen_cases[case.id] = case
            all_cases = tuple(frozen_cases.values())
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
        if request.regression_ids:
            all_labels = ()  # Regression expectations remain separate immutable check evidence.
        selected_ids = {case.id for case in cases}
        development = (
            ()
            if request.regression_ids
            else tuple(case for case in all_cases if case.split == "development")
        )
        development_ids = {case.id for case in development}
        if (profile.adapter == "fixture") != (request.mode == "fixture"):
            fail("provider_mode_mismatch", "preflight_failed")
        compiler = backend.compiler
        compiler_identity = compiler.review_identity
        if (
            type(compiler_identity) is not CompilerIdentity
            or type(compiler_identity.compiler) is not str
            or not compiler_identity.compiler
            or type(compiler_identity.compiler_version) is not str
            or not compiler_identity.compiler_version
        ):
            fail("invalid_compiler_identity", "preflight_failed")
        preflight_error = backend.preflight(request.decision_id, request.dataset_id, definition)
        if preflight_error is not None and not (
            allow_missing_credentials and preflight_error.reason == "credential_unavailable"
        ):
            fail(preflight_error.reason or "provider_preflight_failed", "preflight_failed")
        # Bound copied evidence and each compiled request as the plan grows. Managed
        # assets are independent dependencies, not part of the JSON plan envelope.
        total = sum(len(item.body) for item in records if item.key.collection != "image_assets")
        if total > plan_limit:
            fail("run_resource_limit", "preflight_failed")
        initial_requests = 0
        prepared: list[PlannedCase] = []
        image_assets = ImageAssets({record.key: record for record in records})
        for case in cases:
            assets = image_assets.for_case(case)
            if any(name not in assets for name in definition.selected_images):
                fail("selected_image_missing", "preflight_failed")
            if definition.selected_images and not isinstance(compiler, ImageChoiceCompiler):
                fail("image_compilation_unsupported", "preflight_failed")
            document = JsonDocument(case.input_source)
            try:
                selected = select_input(definition, document)
            except JsonError as error:
                prepared.append(
                    PlannedCase(
                        case.id,
                        case_input_hash(case),
                        None,
                        ServiceError(
                            code="validation_error", resource_id=case.id, reason=error.code
                        ),
                    )
                )
                continue
            initial_requests += 1
            if initial_requests > request.settings.max_attempts and not allow_partial:
                fail("initial_requests_exceed_cap", "preflight_failed")
            try:
                if definition.selected_images:
                    assert isinstance(compiler, ImageChoiceCompiler)
                    compiled = compiler.compile_images(
                        compile_definition,
                        selected.value,
                        profile,
                        tuple((name, assets[name]) for name in definition.selected_images),
                    )
                else:
                    compiled = compiler.compile(compile_definition, selected.value, profile)
            except ValueError:
                fail("unsupported_request_configuration", "preflight_failed")
            compiled = trusted_request(compiled, profile)
            if (compiled.compiler, compiled.compiler_version) != (
                compiler_identity.compiler,
                compiler_identity.compiler_version,
            ):
                fail("compiled_compiler_mismatch", "preflight_failed")
            total += len(dump_record(compiled))
            if total > plan_limit:
                fail("run_resource_limit", "preflight_failed")
            prepared.append(PlannedCase(case.id, case_input_hash(case), compiled, None))
        return RunPlan(
            selection=request,
            definition=definition,
            definition_hash=definition_hash(definition),
            cases=cases,
            labels=tuple(label for label in all_labels if label.case_id in selected_ids),
            development_cases=development,
            development_labels=tuple(
                label for label in all_labels if label.case_id in development_ids
            ),
            provider=profile,
            prepared=tuple(prepared),
            context_hash=fingerprint(records),
            review_records=records,
            review_compiler=compiler_identity,
            plan_bytes=total,
        )
