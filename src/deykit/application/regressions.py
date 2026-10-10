"""Zero-call regression authoring and append-only current visibility."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Annotated, Literal, cast

from pydantic import Field

from deykit.application.dataset_support import decoded, fail, identifier, safe_hash, validated_model
from deykit.application.evaluations import frozen_evaluation_from_records
from deykit.contracts.base import FrozenModel
from deykit.contracts.execution_groups import RegressionRemoval
from deykit.contracts.identities import ResourceId, new_id
from deykit.contracts.json_value import JsonValue
from deykit.contracts.ports import Clock, ResourceKey, SnapshotSource, StoredRecord
from deykit.contracts.records import Nonempty, RegressionRecord
from deykit.contracts.redaction import Sanitizer
from deykit.regressions.evidence import admit_regression_origin, regression_hash
from deykit.runner.history import history_from_records
from deykit.runner.repository import change


class RegressionAdd(FrozenModel):
    run_id: ResourceId
    case_id: ResourceId
    acceptable_option_ids: Annotated[tuple[ResourceId, ...], Field(min_length=1)]
    reason: Nonempty
    result_snapshot_id: ResourceId | None = None
    provenance: Literal["human", "authored_fixture", "imported_unknown", "model_generated"] = (
        "human"
    )


@dataclass(frozen=True)
class RegressionView:
    id: str
    decision_id: str
    dataset_id: str
    case_id: str
    question_id: str
    acceptable_option_ids: tuple[str, ...]
    reason: str
    original_split: str
    provenance: str
    source_run_id: str
    source_result_snapshot_id: str
    input_hash: str
    removed: bool = False
    executable: bool = True
    unavailable_reason: str | None = None


def visible_regressions(
    records: tuple[StoredRecord, ...], decision_id: str
) -> tuple[RegressionRecord, ...]:
    values = tuple(
        decoded(RegressionRecord, r) for r in records if r.key.collection == "regressions"
    )
    by_id = {r.id: r for r in values}
    removed: set[str] = set()
    for stored in records:
        if stored.key.collection != "regression_removals":
            continue
        removal = decoded(RegressionRemoval, stored)
        origin = by_id.get(removal.regression_id)
        if (
            origin is None
            or regression_decision(records, origin) != removal.decision_id
            or stored.key != ResourceKey("regression_removals", removal.id, (removal.decision_id,))
        ):
            fail("regression_removal_mismatch", "incompatible_data")
        removed.add(origin.id)
    selected = tuple(
        sorted(
            (
                r
                for r in values
                if regression_decision(records, r) == decision_id and r.id not in removed
            ),
            key=lambda r: r.id,
        )
    )
    for record in selected:
        if executable_regression(record):
            admit_regression_origin(records, record)
    return selected


def regression_decision(records: tuple[StoredRecord, ...], record: RegressionRecord) -> str:
    if record.decision_id is not None:
        return record.decision_id
    candidates = tuple(
        r.key.scope[0]
        for r in records
        if r.key.collection == "revisions"
        and r.key.resource_id == record.decision_revision_id
        and len(r.key.scope) == 1
    )
    if len(candidates) != 1:
        fail("legacy_regression_scope_ambiguous", "incompatible_data")
    return candidates[0]


def executable_regression(record: RegressionRecord) -> bool:
    return all(
        value is not None
        for value in (
            record.source_case,
            record.decision_id,
            record.provenance,
            record.source_run_id,
            record.source_result_snapshot_id,
            record.content_hash,
        )
    )


def regression_view(record: RegressionRecord, *, removed: bool = False) -> RegressionView:
    case = record.source_case
    return RegressionView(
        record.id,
        record.decision_id or "",
        record.dataset_id,
        record.case_id,
        record.question_id,
        record.acceptable_option_ids,
        Sanitizer().text(record.reason),
        case.split if case else "",
        record.provenance or "",
        record.source_run_id or "",
        record.source_result_snapshot_id or "",
        record.input_hash,
        removed,
        executable_regression(record),
        None if executable_regression(record) else "legacy_regression_not_executable",
    )


class RegressionService:
    def __init__(
        self, source: SnapshotSource, clock: Clock, id_factory: Callable[[], str] = new_id
    ) -> None:
        self.source, self.clock, self.id_factory = source, clock, id_factory

    def add(
        self,
        request: RegressionAdd,
        *,
        operation_id: str,
        expected_decision_id: str | None = None,
    ) -> RegressionView:
        request = validated_model(RegressionAdd, request, "invalid_regression_request")
        identifier(operation_id)
        if expected_decision_id is not None:
            expected_decision_id = identifier(expected_decision_id)
        if len(set(request.acceptable_option_ids)) != len(request.acceptable_option_ids):
            fail("duplicate_expected_option")
        intent: dict[str, JsonValue] = {
            "command": "regression.add",
            "request": cast(JsonValue, request.model_dump(mode="json")),
        }
        if expected_decision_id is not None:
            intent["expected_decision_id"] = expected_decision_id
        digest = safe_hash(intent)
        with self.source.consistent_read():
            receipt = self.source.operation_receipt(operation_id, intent_hash=digest)
            if receipt is not None:
                saved = next(
                    (r for r in receipt.changes if r.key.collection == "regressions"), None
                )
                if saved is None:
                    fail("incomplete_regression_receipt", "incompatible_data")
                replayed = decoded(RegressionRecord, saved)
                if (
                    expected_decision_id is not None
                    and replayed.decision_id != expected_decision_id
                ):
                    fail("regression_decision_mismatch")
                return regression_view(replayed)
            records = self.source.capture_snapshot()
            history = history_from_records(records, request.run_id)
            snapshot_id = request.result_snapshot_id or history.snapshots[-1].id
            frozen = frozen_evaluation_from_records(
                records, request.run_id, snapshot_id, None, "original"
            )
            if (
                expected_decision_id is not None
                and frozen.manifest.decision_id != expected_decision_id
            ):
                fail("regression_decision_mismatch")
            question = frozen.revision.definition.questions[0]
            if not set(request.acceptable_option_ids).issubset(
                option.id for option in question.options
            ):
                fail("unknown_expected_option")
            case = next((c for c in frozen.dataset.cases if c.id == request.case_id), None)
            result = next((r for r in frozen.results.results if r.case_id == request.case_id), None)
            if case is None or result is None:
                fail("regression_case_missing", "not_found")
            record = RegressionRecord(
                id=identifier(self.id_factory()),
                decision_id=frozen.manifest.decision_id,
                decision_revision_id=frozen.revision.id,
                dataset_id=frozen.dataset.dataset_id,
                case_id=case.id,
                question_id=question.id,
                input_source=case.input_source,
                input_hash=result.input_hash,
                source_case=case,
                source_run_id=request.run_id,
                source_result_snapshot_id=snapshot_id,
                source_attempt_id=result.attempt_id,
                acceptable_option_ids=request.acceptable_option_ids,
                reason=request.reason,
                provenance=request.provenance,
                created_at=self.clock.utc_now(),
                content_hash="0" * 64,
            )
            record = record.model_copy(update={"content_hash": regression_hash(record)})
            admit_regression_origin(records, record)
            self.source.commit(operation_id, (change("regressions", record),), intent_hash=digest)
            return regression_view(record)

    def list(self, decision_id: str) -> tuple[RegressionView, ...]:
        identifier(decision_id)
        with self.source.consistent_read():
            return tuple(
                replace(regression_view(record), decision_id=decision_id)
                for record in visible_regressions(self.source.capture_snapshot(), decision_id)
            )

    def remove(self, regression_id: str, *, decision_id: str, operation_id: str) -> RegressionView:
        identifier(regression_id)
        identifier(decision_id)
        identifier(operation_id)
        digest = safe_hash(
            {
                "command": "regression.remove",
                "decision_id": decision_id,
                "regression_id": regression_id,
            }
        )
        with self.source.consistent_read():
            receipt = self.source.operation_receipt(operation_id, intent_hash=digest)
            source = self.source.read(ResourceKey("regressions", regression_id))
            if source is None:
                fail("regression_missing", "not_found")
            record = decoded(RegressionRecord, source)
            records = self.source.capture_snapshot()
            if regression_decision(records, record) != decision_id:
                fail("regression_decision_mismatch")
            if executable_regression(record):
                admit_regression_origin(records, record)
            view = regression_view(record, removed=True)
            if receipt is not None:
                return view
            removal = RegressionRemoval(
                id=identifier(self.id_factory()),
                regression_id=regression_id,
                decision_id=decision_id,
                operation_id=operation_id,
                created_at=self.clock.utc_now(),
            )
            self.source.commit(
                operation_id,
                (change("regression_removals", removal, (decision_id,)),),
                intent_hash=digest,
            )
            return view
