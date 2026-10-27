"""Coordinate frozen experiment members through the shared execution group."""

from dataclasses import dataclass, replace
from typing import Literal, cast

from deykit.application.dataset_support import decoded, fail, identifier, validated_model
from deykit.application.errors import ServiceFailure
from deykit.application.evaluation_evidence import snapshot_history
from deykit.application.execution import ExecutionService
from deykit.application.execution_groups import GroupAcknowledgementCallback, GroupExecutionService
from deykit.application.experiment_reuse import (
    admit_reuse,
    match_reuse,
    reuse_intent,
    reuse_members,
    reuse_request,
)
from deykit.contracts.errors import ServiceError
from deykit.contracts.execution_groups import ExperimentReuse
from deykit.contracts.experiments import (
    ExperimentCohort,
    ExperimentDecision,
    ExperimentOrder,
    ExperimentRepeat,
    ExperimentRequest,
    ExperimentVariant,
    amount_text,
    amount_units,
)
from deykit.contracts.json_value import GROUP_SELECTION_LIMITS, JsonError, JsonValue, dump_json
from deykit.contracts.ports import ResourceKey, StoredRecord
from deykit.contracts.records import DecisionRevision
from deykit.domain.definitions import definition_hash
from deykit.runner.experiment_plan import ExperimentMember, diagnostic_base_index, expand_experiment
from deykit.runner.group_evidence import (
    admit_group_snapshots,
    content_hash,
    experiment_members,
    group_budget,
)
from deykit.runner.group_models import GroupPlan, GroupPreview, GroupProgress
from deykit.runner.history import history_from_records
from deykit.runner.planner import MAX_EXPERIMENT_PLAN_BYTES, RunPlan, RunRequest
from deykit.runner.repository import change
from deykit.runner.result_limits import experiment_case_result_limit, minimum_dense_result_size
from deykit.runner.review import group_review_hash, require_review_hash
from deykit.runner.views import RunPreview, RunProgress, preview_view, progress_view

__all__ = [
    "ExperimentCohort",
    "ExperimentDecision",
    "ExperimentRequest",
    "ExperimentService",
    "ExperimentVariant",
]

MAX_EXPANDED_CASE_IDS = 1_000_000
MAX_EXPERIMENT_MEMBERS = 100


@dataclass(frozen=True)
class ExperimentCompatibilityFailure:
    member_index: int | None
    error: ServiceError


@dataclass(frozen=True)
class ExperimentPreview:
    group: GroupPreview | None
    initial_reservation_usd: str | None
    known_reservation_usd: str
    unknown_price_requests: int
    budget_usd: str | None
    price_assumptions: tuple[tuple[str, str | None], ...]
    member_details: tuple[ExperimentMember, ...]
    fresh_requests: int
    reused_requests: int
    member_previews: tuple[RunPreview | None, ...]
    compatibility_failures: tuple[ExperimentCompatibilityFailure, ...]
    unplanned_members: int | None

    @property
    def initial_requests(self) -> int:
        if self.group is not None:
            return self.group.initial_requests
        return sum(preview.initial_requests for preview in self.member_previews if preview)

    @property
    def members(self) -> tuple[RunPreview, ...]:
        if self.group is not None:
            return self.group.members
        return tuple(preview for preview in self.member_previews if preview)


@dataclass(frozen=True)
class ExperimentProgress:
    group: GroupProgress
    reserved_usd: str
    remaining_usd: str | None
    unknown_price_attempts: int
    unknown_usage_attempts: int
    member_details: tuple[ExperimentMember, ...]
    fresh_attempts: int
    reuse_id: str | None = None
    reused_group_id: str | None = None
    billed_cost_usd: None = None

    @property
    def group_id(self) -> str:
        return self.group.group_id

    @property
    def members(self) -> tuple[RunProgress, ...]:
        return self.group.members

    @property
    def attempts_used(self) -> int:
        return self.group.attempts_used

    @property
    def replayed(self) -> bool:
        return self.group.replayed


@dataclass(frozen=True)
class ExperimentMemberResumePreview:
    run_id: str
    eligible_case_ids: tuple[str, ...]
    maximum_dispatchable_attempts: int
    blocked_reason: str | None = None


@dataclass(frozen=True)
class ExperimentResumePreview:
    group: GroupProgress
    segment_ids: tuple[str, ...]
    members: tuple[ExperimentMemberResumePreview, ...]
    retry_unknown: bool
    proposed_attempt_limit: int
    remaining_usd: str | None
    dry_run: bool = True


class ExperimentService:
    def __init__(self, execution: ExecutionService) -> None:
        self.execution = execution
        self.groups = GroupExecutionService(execution)

    @staticmethod
    def _selection_source(request: ExperimentRequest) -> str:
        return dump_json(
            {"kind": "experiment", "request": cast(JsonValue, request.model_dump(mode="json"))},
            limits=GROUP_SELECTION_LIMITS,
        )

    def _members(
        self, request: ExperimentRequest, *, captured: tuple[StoredRecord, ...] | None = None
    ) -> tuple[tuple[ExperimentMember, ...], tuple[StoredRecord, ...]]:
        if captured is None:
            with self.execution.source.consistent_read():
                captured = self.execution.source.capture_snapshot()
        by_key = {record.key: record for record in captured}
        definitions = []
        for decision in request.decisions:
            record = by_key.get(
                ResourceKey("revisions", decision.revision_id, (decision.decision_id,))
            )
            if record is None:
                fail("experiment_revision_missing", "preflight_failed")
            revision = decoded(DecisionRevision, record)
            if revision.content_hash != definition_hash(revision.definition):
                fail("revision_hash_mismatch", "incompatible_data")
            definitions.append(revision.definition)
        try:
            members = expand_experiment(request, tuple(definitions))
        except ValueError:
            fail("invalid_experiment_request", "preflight_failed")
        return members, captured

    def _inputs(
        self, request: ExperimentRequest, *, captured: tuple[StoredRecord, ...] | None = None
    ) -> tuple[tuple[ExperimentMember, ...], tuple[RunRequest, ...], tuple[StoredRecord, ...]]:
        combinations = request.combination_indices()
        if len(combinations) > MAX_EXPERIMENT_MEMBERS:
            fail("experiment_member_limit", "preflight_failed")
        if (
            sum(len(request.cohorts[cohort].case_ids) for _, cohort, _ in combinations)
            > MAX_EXPANDED_CASE_IDS
        ):
            fail("experiment_expanded_selection_limit", "preflight_failed")
        members, captured = self._members(request, captured=captured)
        if len(members) > MAX_EXPERIMENT_MEMBERS:
            fail("experiment_member_limit", "preflight_failed")
        if sum(len(member.cohort.case_ids) for member in members) > MAX_EXPANDED_CASE_IDS:
            fail("experiment_expanded_selection_limit", "preflight_failed")
        selections = tuple(
            RunRequest(
                decision_id=member.decision.decision_id,
                revision_id=member.decision.revision_id,
                dataset_id=member.cohort.dataset_id,
                split=member.cohort.split,
                case_ids=member.cohort.case_ids,
                mode=request.mode,
                provider_id=member.variant.provider_id,
                fixture_set_id=member.variant.fixture_set_id,
                option_order=member.option_order,
                settings=request.settings,
            )
            for member in members
        )
        return members, selections, captured

    @staticmethod
    def _check_member(plan: RunPlan, member: ExperimentMember) -> None:
        if bool(plan.definition.selected_images) != (member.decision.modality == "image"):
            fail("experiment_modality_mismatch", "preflight_failed")
        if plan.provider.adapter not in {"fixture", "jev", "openai"}:
            fail("experiment_provider_unsupported", "preflight_failed")
        if plan.selection.mode == "live" and plan.initial_requests:
            question = plan.definition.questions[0]
            if minimum_dense_result_size(
                max((case.id for case in plan.cases), key=len),
                question.id,
                tuple(option.id for option in question.options),
            ) > experiment_case_result_limit(
                len(plan.cases), min(plan.selection.settings.max_attempts, plan.initial_requests)
            ):
                fail("experiment_result_snapshot_capacity", "preflight_failed")

    def _plan(self, request: ExperimentRequest) -> GroupPlan:
        members, selections, captured = self._inputs(request)
        plans = self.execution.planner.prepare_many(
            selections,
            captured=captured,
            allow_partial=True,
            max_plan_bytes=MAX_EXPERIMENT_PLAN_BYTES,
            max_total_plan_bytes=MAX_EXPERIMENT_PLAN_BYTES,
            allow_missing_credentials=request.reuse_group_id is not None,
        )
        for plan, member in zip(plans, members, strict=True):
            self._check_member(plan, member)
            if member.purpose != "main":
                assert member.diagnostic is not None
                base_index = diagnostic_base_index(request, member.diagnostic)
                selected_ids = set(member.cohort.case_ids)
                if not selected_ids <= {
                    case.id for case in plans[base_index].cases
                } or selected_ids != {case.id for case in plan.cases}:
                    fail("experiment_diagnostic_scope_mismatch", "preflight_failed")
        return GroupPlan(
            "experiment",
            plans,
            request.settings.max_attempts,
            request.settings.deadline_seconds,
            review_membership_records=(),
        )

    def preview(self, request: ExperimentRequest) -> ExperimentPreview:
        request = validated_model(
            ExperimentRequest,
            request,
            "invalid_experiment_request",
            max_nodes=GROUP_SELECTION_LIMITS.max_nodes,
        )
        try:
            plan = self._plan(request)
        except ServiceFailure as failure:
            if failure.error.code != "preflight_failed":
                raise
            combinations = request.combination_indices()
            main_count = len(combinations)
            main_references = sum(
                len(request.cohorts[cohort].case_ids) for _, cohort, _ in combinations
            )
            upper_members = main_count + sum(
                diagnostic.count if isinstance(diagnostic, ExperimentRepeat) else diagnostic.orders
                for diagnostic in request.diagnostics
            )
            upper_references = main_references + sum(
                len(diagnostic.case_ids)
                * (
                    diagnostic.count
                    if isinstance(diagnostic, ExperimentRepeat)
                    else diagnostic.orders
                )
                for diagnostic in request.diagnostics
            )
            limit_failure = failure.error.reason in {
                "experiment_expanded_selection_limit",
                "experiment_member_limit",
            }
            uncertain_expansion = False
            if not limit_failure and (
                upper_members > MAX_EXPERIMENT_MEMBERS or upper_references > MAX_EXPANDED_CASE_IDS
            ):
                try:
                    self._inputs(request)
                except ServiceFailure:
                    uncertain_expansion = True
            if limit_failure or uncertain_expansion:
                member_count: int | None
                if main_count > MAX_EXPERIMENT_MEMBERS or main_references > MAX_EXPANDED_CASE_IDS:
                    member_count = main_count if not request.diagnostics else None
                elif limit_failure:
                    members, _ = self._members(request)
                    member_count = len(members)
                else:
                    member_count = None
                return ExperimentPreview(
                    group=None,
                    initial_reservation_usd=None,
                    known_reservation_usd="0",
                    unknown_price_requests=0,
                    budget_usd=request.budget_usd,
                    price_assumptions=tuple((v.name, v.reservation_usd) for v in request.variants),
                    member_details=(),
                    fresh_requests=0,
                    reused_requests=0,
                    member_previews=(),
                    compatibility_failures=(ExperimentCompatibilityFailure(None, failure.error),),
                    unplanned_members=member_count,
                )
            if failure.error.reason == "execution_group_resource_limit":
                members, _, _ = self._inputs(request)
                return ExperimentPreview(
                    group=None,
                    initial_reservation_usd=None,
                    known_reservation_usd="0",
                    unknown_price_requests=0,
                    budget_usd=request.budget_usd,
                    price_assumptions=tuple((v.name, v.reservation_usd) for v in request.variants),
                    member_details=members,
                    fresh_requests=0,
                    reused_requests=0,
                    member_previews=(None,) * len(members),
                    compatibility_failures=(ExperimentCompatibilityFailure(None, failure.error),),
                    unplanned_members=len(members),
                )
            return self._incompatible_preview(request, failure.error)
        staged_request = request.model_copy(update={"reuse_group_id": None})
        group: GroupPreview | None = None
        group_error: ServiceError | None = None
        try:
            selection_source = self._selection_source(request)
            group = self.groups.preview(
                lambda: plan, selection_source=self._selection_source(staged_request)
            )
            group = replace(group, review_context_hash=group_review_hash(plan, selection_source))
        except JsonError as error:
            group_error = ServiceError(code="preflight_failed", reason=error.code)
        except ServiceFailure as failure:
            if failure.error.code != "preflight_failed":
                raise
            group_error = failure.error
        known = 0
        unknown = 0
        combinations = request.combination_indices()
        definitions = tuple(
            plan.plans[
                next(
                    index
                    for index, (decision_index, _, _) in enumerate(combinations)
                    if decision_index == position
                )
            ].definition
            for position in range(len(request.decisions))
        )
        members = expand_experiment(request, definitions)
        for member, spec in zip(plan.plans, members, strict=True):
            if spec.variant.reservation_usd is None:
                unknown += member.initial_requests
            else:
                known += member.initial_requests * amount_units(spec.variant.reservation_usd)
        reused_requests = 0
        reuse_failure: ServiceError | None = None
        if request.reuse_group_id is not None and group is not None:
            with self.execution.source.consistent_read():
                records = self.execution.source.capture_snapshot()
            try:
                match_reuse(records, request.reuse_group_id, plan)
            except ServiceFailure as failure:
                if failure.error.code != "preflight_failed":
                    raise
                reuse_failure = failure.error
            else:
                reused_requests = group.initial_requests
        if request.reuse_group_id is not None:
            known = unknown = 0
        pricing_failures = (
            tuple(
                ExperimentCompatibilityFailure(
                    index,
                    ServiceError(
                        code="preflight_failed", reason="experiment_price_unknown_with_budget"
                    ),
                )
                for index, spec in enumerate(members)
                if spec.variant.reservation_usd is None
            )
            if request.budget_usd is not None and request.reuse_group_id is None
            else ()
        )
        return ExperimentPreview(
            group=group,
            initial_reservation_usd=amount_text(known)
            if not unknown and not reuse_failure
            else None,
            known_reservation_usd=amount_text(known),
            unknown_price_requests=unknown,
            budget_usd=request.budget_usd,
            price_assumptions=tuple((v.name, v.reservation_usd) for v in request.variants),
            member_details=members,
            fresh_requests=(
                0
                if request.reuse_group_id is not None
                else sum(member.initial_requests for member in plan.plans)
            ),
            reused_requests=reused_requests,
            member_previews=tuple(preview_view(member) for member in plan.plans)
            if group is None
            else (),
            compatibility_failures=pricing_failures
            + ((ExperimentCompatibilityFailure(None, reuse_failure),) if reuse_failure else ())
            + ((ExperimentCompatibilityFailure(None, group_error),) if group_error else ()),
            unplanned_members=0,
        )

    def _incompatible_preview(
        self, request: ExperimentRequest, original_error: ServiceError
    ) -> ExperimentPreview:
        with self.execution.source.consistent_read():
            captured = self.execution.source.capture_snapshot()
        entries: list[tuple[ExperimentMember, RunRequest | None, ServiceError | None]] = []
        decision_errors: dict[int, ServiceError] = {}
        for index, decision in enumerate(request.decisions):
            include = (
                tuple(
                    item.model_copy(update={"decision_index": 0})
                    for item in request.include
                    if item.decision_index == index
                )
                if request.include is not None
                else None
            )
            subrequest = request.model_copy(
                update={"decisions": (decision,), "diagnostics": (), "include": include}
            )
            try:
                members, selections, _ = self._inputs(subrequest, captured=captured)
            except ServiceFailure as failure:
                if failure.error.code != "preflight_failed":
                    raise
                decision_errors[index] = failure.error
                entries.extend(
                    (ExperimentMember(decision, cohort, variant, "main"), None, failure.error)
                    for _, cohort, variant in subrequest.combinations()
                )
            else:
                entries.extend(
                    (member, run, None) for member, run in zip(members, selections, strict=True)
                )
        for diagnostic in request.diagnostics:
            decision = request.decisions[diagnostic.decision_index]
            input_failure = decision_errors.get(diagnostic.decision_index)
            if input_failure is None:
                include = (
                    tuple(
                        item.model_copy(update={"decision_index": 0})
                        for item in request.include
                        if item.decision_index == diagnostic.decision_index
                    )
                    if request.include is not None
                    else None
                )
                subrequest = request.model_copy(
                    update={
                        "decisions": (decision,),
                        "diagnostics": (diagnostic.model_copy(update={"decision_index": 0}),),
                        "include": include,
                    }
                )
                main_count = len(subrequest.combinations())
                try:
                    members, selections, _ = self._inputs(subrequest, captured=captured)
                except ServiceFailure as failure:
                    if failure.error.code != "preflight_failed":
                        raise
                    input_failure = failure.error
                else:
                    entries.extend(
                        (member, run, None)
                        for member, run in zip(
                            members[main_count:], selections[main_count:], strict=True
                        )
                    )
                    continue
            variant = next(item for item in request.variants if item.name == diagnostic.variant)
            cohort = request.cohorts[diagnostic.cohort_index].model_copy(
                update={"case_ids": diagnostic.case_ids}
            )
            kind: Literal["choice_order", "repeat"] = (
                "choice_order" if isinstance(diagnostic, ExperimentOrder) else "repeat"
            )
            count = (
                diagnostic.orders if isinstance(diagnostic, ExperimentOrder) else diagnostic.count
            )
            entries.extend(
                (
                    ExperimentMember(decision, cohort, variant, kind, diagnostic.name),
                    None,
                    input_failure,
                )
                for _ in range(count)
            )
        members = tuple(member for member, _, _ in entries)
        previews: list[RunPreview | None] = []
        failures: list[ExperimentCompatibilityFailure] = []
        known = unknown = 0
        planned_bytes = 0
        limit_error: ServiceError | None = None
        for index, (member, selection, input_error) in enumerate(entries):
            try:
                if input_error is not None:
                    raise ServiceFailure(input_error)
                if limit_error is not None:
                    raise ServiceFailure(limit_error)
                assert selection is not None
                plan = self.execution.planner.prepare_many(
                    (selection,),
                    captured=captured,
                    allow_partial=True,
                    max_plan_bytes=MAX_EXPERIMENT_PLAN_BYTES,
                    max_total_plan_bytes=MAX_EXPERIMENT_PLAN_BYTES - planned_bytes,
                    allow_missing_credentials=request.reuse_group_id is not None,
                )[0]
                planned_bytes += plan.plan_bytes
                self._check_member(plan, member)
                preview = preview_view(plan)
            except ServiceFailure as error:
                if error.error.reason == "execution_group_resource_limit":
                    limit_error = error.error
                failures.append(ExperimentCompatibilityFailure(index, error.error))
                previews.append(None)
                continue
            previews.append(preview)
            if member.variant.reservation_usd is None:
                unknown += preview.initial_requests
            else:
                known += preview.initial_requests * amount_units(member.variant.reservation_usd)
        if not any(failure.error.reason == original_error.reason for failure in failures):
            failures.append(ExperimentCompatibilityFailure(None, original_error))
        if request.reuse_group_id is not None:
            known = unknown = 0
        return ExperimentPreview(
            group=None,
            initial_reservation_usd=None,
            known_reservation_usd=amount_text(known),
            unknown_price_requests=unknown,
            budget_usd=request.budget_usd,
            price_assumptions=tuple((v.name, v.reservation_usd) for v in request.variants),
            member_details=members,
            fresh_requests=0
            if request.reuse_group_id is not None
            else sum(preview.initial_requests for preview in previews if preview),
            reused_requests=0,
            member_previews=tuple(previews),
            compatibility_failures=tuple(failures),
            unplanned_members=sum(preview is None for preview in previews),
        )

    async def start(
        self,
        request: ExperimentRequest,
        *,
        operation_id: str,
        expected_review_context_hash: str | None = None,
        on_created: GroupAcknowledgementCallback | None = None,
    ) -> ExperimentProgress:
        request = validated_model(
            ExperimentRequest,
            request,
            "invalid_experiment_request",
            max_nodes=GROUP_SELECTION_LIMITS.max_nodes,
        )
        if request.reuse_group_id is not None:
            return self._reuse(
                request,
                operation_id=operation_id,
                expected_review_context_hash=expected_review_context_hash,
            )
        if request.budget_usd is not None and any(
            variant.reservation_usd is None for _, _, variant in request.combinations()
        ):
            fail("experiment_price_unknown_with_budget", "preflight_failed")
        result = await self.groups.start(
            selection_source=self._selection_source(request),
            prepare=lambda: self._plan(request),
            operation_id=operation_id,
            expected_review_context_hash=expected_review_context_hash,
            on_created=on_created,
        )
        return await self._view_async(result)

    def read(self, group_id: str) -> ExperimentProgress:
        identifier(group_id)
        with self.execution.source.consistent_read():
            record = self.execution.source.read(ResourceKey("experiment_reuses", group_id))
        if record is not None:
            return self._reuse_view(decoded(ExperimentReuse, record), replayed=False)
        progress = self.groups.show(group_id)
        if progress.kind != "experiment":
            fail("experiment_group_required")
        return self._view(progress)

    def read_captured(
        self, records: tuple[StoredRecord, ...], experiment_id: str, *, active: bool
    ) -> ExperimentProgress:
        identifier(experiment_id)
        stored = next(
            (
                item
                for item in records
                if item.key == ResourceKey("experiment_reuses", experiment_id)
            ),
            None,
        )
        if stored is not None:
            return self._project_reuse(records, decoded(ExperimentReuse, stored), replayed=False)
        progress = self.groups.captured_progress(
            records, experiment_id, active=active, decoder=self.execution.repository.decoder
        )
        return self._view_from_records(progress, records)

    def preview_resume(
        self, group_id: str, *, retry_unknown: bool = False
    ) -> ExperimentResumePreview:
        identifier(group_id)
        if type(retry_unknown) is not bool:
            fail("invalid_unknown_retry_choice")
        with self.execution.source.consistent_read():
            records = self.execution.source.capture_snapshot()
            budget = group_budget(records, group_id, decoder=self.execution.repository.decoder)
            self.groups._require_kind(budget.group, "experiment")
            admit_group_snapshots(records, group_id, decoder=self.execution.repository.decoder)
            histories = tuple(
                history_from_records(
                    records,
                    member.run_id,
                    verify_group=False,
                    decoder=self.execution.repository.decoder,
                )
                for member in budget.group.members
            )
            blocked_profiles = self.groups._failed_provider_profiles(histories)
            members = []
            for history in histories:
                blocked = history.manifest.provider_config_hash in blocked_profiles
                work = history.work(retry_unknown=retry_unknown) if not blocked else ()
                eligible = tuple(item.prepared.case_id for item in work)
                possible_attempts = sum(
                    1
                    + max(
                        0,
                        history.manifest.settings.max_retries_per_case
                        - sum(
                            attempt.kind == "rate_retry"
                            for attempt in history.case_attempts(item.prepared.case_id)
                        )
                        - (item.kind == "rate_retry"),
                    )
                    for item in work
                )
                if eligible and budget.remaining_for(history.manifest.id) > 0:
                    self.groups._backend_captured(history, records)
                members.append(
                    ExperimentMemberResumePreview(
                        history.manifest.id,
                        eligible,
                        min(possible_attempts, budget.remaining_for(history.manifest.id)),
                        "provider_wide_failure" if blocked else None,
                    )
                )
        active = self.execution.execution.execution_active()
        progress = self.groups.captured_progress(
            records, group_id, active=active, decoder=self.execution.repository.decoder
        )
        return ExperimentResumePreview(
            group=progress,
            segment_ids=tuple(segment.id for segment in budget.segments),
            members=tuple(members),
            retry_unknown=retry_unknown,
            proposed_attempt_limit=budget.group.max_attempts,
            remaining_usd=(
                amount_text(max(0, budget.limit_units - budget.reserved_units))
                if budget.limit_units is not None
                else None
            ),
        )

    async def resume(
        self,
        group_id: str,
        *,
        operation_id: str,
        retry_unknown: bool = False,
        on_resumed: GroupAcknowledgementCallback | None = None,
    ) -> ExperimentProgress:
        return await self._view_async(
            await self.groups.resume(
                group_id,
                operation_id=operation_id,
                retry_unknown=retry_unknown,
                expected_kind="experiment",
                on_resumed=on_resumed,
            )
        )

    def _view(self, progress: GroupProgress) -> ExperimentProgress:
        if progress.kind != "experiment":
            fail("experiment_group_required")
        with self.execution.source.consistent_read():
            records = self.execution.source.capture_snapshot()
        return self._project_progress(progress, records)

    async def _view_async(self, progress: GroupProgress) -> ExperimentProgress:
        records = await self.execution.scheduler._source_call(
            progress.group_id, "history", self.execution.source.capture_snapshot, offload=True
        )
        return self._project_progress(progress, records)

    def _project_progress(
        self, progress: GroupProgress, records: tuple[StoredRecord, ...]
    ) -> ExperimentProgress:
        if progress.kind != "experiment":
            fail("experiment_group_required")
        progress = self.groups.captured_progress(
            records,
            progress.group_id,
            active=any(member.execution_active for member in progress.members),
            replayed=progress.replayed,
            decoder=self.execution.repository.decoder,
        )
        return self._view_from_records(progress, records)

    def _view_from_records(
        self, progress: GroupProgress, records: tuple[StoredRecord, ...]
    ) -> ExperimentProgress:
        if progress.kind != "experiment":
            fail("experiment_group_required")
        budget = group_budget(records, progress.group_id, decoder=self.execution.repository.decoder)
        unknown_usage = 0
        for member in budget.group.members:
            history = history_from_records(
                records,
                member.run_id,
                verify_group=False,
                decoder=self.execution.repository.decoder,
            )
            dispatched = {
                event.attempt_id for event in history.attempt_events if event.state == "dispatched"
            }
            for attempt in history.attempts:
                if attempt.id not in dispatched:
                    continue
                event = history.final_event(attempt.id)
                if event is not None and event.state == "not_sent":
                    continue
                if event is None or event.outcome is None or event.outcome.usage_source is None:
                    unknown_usage += 1
        return ExperimentProgress(
            progress,
            amount_text(budget.reserved_units),
            amount_text(budget.limit_units - budget.reserved_units)
            if budget.limit_units is not None
            else None,
            budget.unknown_price_attempts,
            unknown_usage,
            experiment_members(budget.group, records),
            progress.attempts_used,
        )

    def _reuse(
        self,
        request: ExperimentRequest,
        *,
        operation_id: str,
        expected_review_context_hash: str | None,
    ) -> ExperimentProgress:
        identifier(operation_id)
        assert request.reuse_group_id is not None
        selection = self._selection_source(request)
        intent = reuse_intent(selection, expected_review_context_hash)
        with self.execution.source.consistent_read():
            receipt = self.execution.source.operation_receipt(operation_id, intent_hash=intent)
        if receipt is not None:
            stored = next(
                (item for item in receipt.changes if item.key.collection == "experiment_reuses"),
                None,
            )
            if stored is None:
                fail("invalid_experiment_reuse_receipt", "incompatible_data")
            return self._reuse_view(decoded(ExperimentReuse, stored), replayed=True)
        with self.execution.execution.execution_owner():
            plan = self._plan(request)
            with self.execution.source.consistent_read():
                receipt = self.execution.source.operation_receipt(operation_id, intent_hash=intent)
                if receipt is not None:
                    stored = next(
                        (
                            item
                            for item in receipt.changes
                            if item.key.collection == "experiment_reuses"
                        ),
                        None,
                    )
                    if stored is None:
                        fail("invalid_experiment_reuse_receipt", "incompatible_data")
                    reuse = decoded(ExperimentReuse, stored)
                    replayed = True
                else:
                    self.execution.planner.check_contexts(plan.plans)
                    review_hash = group_review_hash(plan, selection)
                    require_review_hash(expected_review_context_hash, review_hash)
                    records = self.execution.source.capture_snapshot()
                    snapshot = match_reuse(records, request.reuse_group_id, plan)
                    reuse = ExperimentReuse(
                        id=self.execution.repository.identity(),
                        source_group_id=request.reuse_group_id,
                        source_snapshot_id=snapshot.id,
                        operation_id=operation_id,
                        intent_hash=intent,
                        selection_source=selection,
                        review_context_hash=review_hash,
                        expected_review_context_hash=expected_review_context_hash,
                        results=snapshot.results,
                        content_hash="0" * 64,
                        created_at=self.execution.repository.clock.utc_now(),
                    )
                    reuse = reuse.model_copy(update={"content_hash": content_hash(reuse)})
                    admit_reuse(records, reuse)
                    self.execution.source.commit(
                        operation_id, (change("experiment_reuses", reuse),), intent_hash=intent
                    )
                    replayed = False
        return self._reuse_view(reuse, replayed=replayed)

    def _reuse_view(self, reuse: ExperimentReuse, *, replayed: bool) -> ExperimentProgress:
        with self.execution.source.consistent_read():
            records = self.execution.source.capture_snapshot()
        return self._project_reuse(records, reuse, replayed=replayed)

    def _project_reuse(
        self, records: tuple[StoredRecord, ...], reuse: ExperimentReuse, *, replayed: bool
    ) -> ExperimentProgress:
        selected = admit_reuse(records, reuse)
        group = self.groups.captured_progress(
            records,
            reuse.source_group_id,
            replayed=replayed,
            decoder=self.execution.repository.decoder,
        )
        result = self._view_from_records(group, records)
        request = reuse_request(reuse)
        members = []
        unknown_usage = 0
        for reference in selected.results:
            history = history_from_records(
                records,
                reference.run_id,
                verify_group=False,
                decoder=self.execution.repository.decoder,
            )
            snapshot = next(
                item for item in history.snapshots if item.id == reference.result_snapshot_id
            )
            historical, dispatched = snapshot_history(
                records, snapshot, decoder=self.execution.repository.decoder, history=history
            )
            members.append(progress_view(historical))
            unknown_usage += sum(
                event.state != "not_sent"
                and (event.outcome is None or event.outcome.usage_source is None)
                for _, event in dispatched
            )
        return replace(
            result,
            group=replace(
                group,
                members=tuple(members),
                attempts_used=0,
                attempt_limit=request.settings.max_attempts,
                attempts_remaining=request.settings.max_attempts,
                snapshot_id=selected.id,
            ),
            reserved_usd="0",
            remaining_usd=request.budget_usd,
            unknown_price_attempts=0,
            unknown_usage_attempts=unknown_usage,
            member_details=reuse_members(reuse),
            fresh_attempts=0,
            reuse_id=reuse.id,
            reused_group_id=reuse.source_group_id,
        )
