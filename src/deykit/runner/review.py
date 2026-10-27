"""Pure reviewed-context fingerprints for exact run and group plans."""

import re
from typing import cast

from deykit.application.dataset_support import decoded, fail
from deykit.contracts.codec import dump_record
from deykit.contracts.execution_groups import RegressionRemoval
from deykit.contracts.json_value import JsonError, JsonLimits, JsonValue, bytes_hash, semantic_hash
from deykit.contracts.ports import StoredRecord
from deykit.contracts.records import RegressionRecord
from deykit.runner.group_models import GroupPlan
from deykit.runner.planner import MAX_PLAN_BYTES, RunPlan

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_REVIEW_LIMITS = JsonLimits(max_bytes=MAX_PLAN_BYTES, max_depth=128, max_nodes=2_000_000)


def _review_digest(payload: JsonValue, reason: str) -> str:
    try:
        return semantic_hash(payload, limits=_REVIEW_LIMITS)
    except JsonError as error:
        if error.code == "json_resource_limit":
            fail(reason, "preflight_failed")
        raise


def _record_identities(records: tuple[StoredRecord, ...]) -> list[JsonValue]:
    return [
        [
            item.key.collection,
            list(item.key.scope),
            item.key.resource_id,
            item.etag,
            bytes_hash(item.body),
        ]
        for item in sorted(
            records,
            key=lambda record: (
                record.key.collection,
                record.key.scope,
                record.key.resource_id,
            ),
        )
    ]


def regression_membership_records(
    records: tuple[StoredRecord, ...], decision_id: str, explicit_ids: tuple[str, ...] | None
) -> tuple[StoredRecord, ...]:
    """Capture regression and removal evidence that determines this selection's membership."""
    from deykit.application.regressions import regression_decision

    if explicit_ids is not None:
        selected = set(explicit_ids)
        regressions = tuple(
            record
            for record in records
            if record.key.collection == "regressions" and record.key.resource_id in selected
        )
        removals = tuple(
            record
            for record in records
            if record.key.collection == "regression_removals"
            and decoded(RegressionRemoval, record).regression_id in selected
        )
        return tuple(
            sorted(
                (*regressions, *removals),
                key=lambda item: (
                    item.key.collection,
                    item.key.scope,
                    item.key.resource_id,
                ),
            )
        )

    candidates: list[StoredRecord] = []
    candidate_ids: set[str] = set()
    for record in records:
        if record.key.collection != "regressions":
            continue
        value = decoded(RegressionRecord, record)
        if regression_decision(records, value) == decision_id:
            candidates.append(record)
            candidate_ids.add(value.id)
    candidates.extend(
        record
        for record in records
        if record.key.collection == "regression_removals"
        and decoded(RegressionRemoval, record).regression_id in candidate_ids
    )
    return tuple(
        sorted(
            candidates,
            key=lambda item: (item.key.collection, item.key.scope, item.key.resource_id),
        )
    )


def run_review_payload(plan: RunPlan) -> JsonValue:
    prepared: list[JsonValue] = []
    for item in plan.prepared:
        request: JsonValue = None
        error: JsonValue = None
        if item.request is not None:
            compiled = item.request
            request = [
                compiled.adapter,
                compiled.compiler,
                compiled.compiler_version,
                compiled.requested_model,
                compiled.destination,
                compiled.body_hash,
                bytes_hash(compiled.body),
            ]
            if compiled.semantic_headers_source != "{}":
                request.append(compiled.semantic_headers_source)
        if item.error is not None:
            error = [
                item.error.code,
                item.error.reason,
                item.error.resource_id,
                item.error.row,
            ]
        prepared.append([item.case_id, item.input_hash, request, error])
    return {
        "kind": "run-review-v1",
        "selection": cast(JsonValue, plan.selection.model_dump(mode="json")),
        "records": _record_identities(plan.review_records),
        "definition": [plan.definition_hash, bytes_hash(dump_record(plan.definition))],
        "provider": bytes_hash(dump_record(plan.provider)),
        "compiler": [plan.review_compiler.compiler, plan.review_compiler.compiler_version],
        "cases": [bytes_hash(dump_record(item)) for item in plan.cases],
        "labels": [bytes_hash(dump_record(item)) for item in plan.labels],
        "development_cases": [bytes_hash(dump_record(item)) for item in plan.development_cases],
        "development_labels": [bytes_hash(dump_record(item)) for item in plan.development_labels],
        "prepared": prepared,
    }


def run_review_hash(plan: RunPlan) -> str:
    return _review_digest(run_review_payload(plan), "run_resource_limit")


def group_review_hash(plan: GroupPlan, selection_source: str) -> str:
    from deykit.runner.group_selection import decode_group_start_selection

    selection = decode_group_start_selection(selection_source, expected_kind=plan.kind)
    payload: JsonValue = {
        "kind": "experiment-group-review-v2" if plan.kind == "experiment" else "group-review-v1",
        "group_kind": plan.kind,
        "selection": selection.original_selection,
        "algorithm": "deykit-choice-order-v1" if plan.kind == "choice_order" else None,
        "members": [
            run_review_hash(member) if plan.kind == "experiment" else run_review_payload(member)
            for member in plan.plans
        ],
        "max_attempts": plan.max_attempts,
        "deadline_seconds": plan.deadline_seconds,
        "default_regression_ids": (
            list(plan.default_regression_ids) if plan.default_regression_ids is not None else None
        ),
        "membership_records": _record_identities(plan.review_membership_records),
    }
    return _review_digest(payload, "execution_group_resource_limit")


def require_review_hash(expected: str | None, actual: str) -> None:
    if expected is None:
        return
    validate_review_hash(expected)
    if expected != actual:
        fail("run_source_changed", "conflict")


def validate_review_hash(expected: str) -> str:
    if type(expected) is not str or _HASH.fullmatch(expected) is None:
        fail("invalid_review_context_hash")
    return expected
