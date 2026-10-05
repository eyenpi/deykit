"""Exact authored choice bindings; no provider transport, credentials, or fallback."""

from __future__ import annotations

from decimal import Decimal, localcontext

from pydantic import ValidationError

from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import validate_resource_id
from deykit.contracts.json_value import (
    GENERATED_LIMITS,
    JsonError,
    JsonValue,
    bytes_hash,
    parse_json,
    semantic_hash,
)
from deykit.contracts.records import (
    CompiledRequest,
    DispatchOutcome,
    FixtureSet,
    NormalizedAnswer,
)
from deykit.providers.choice import ResponseInvalid, verify_compiled_request

FIXTURE_DESTINATION = "fixture:jev-choice"
SUM_TOLERANCE = Decimal("0.000001")


class FixtureInvalid(ValueError):
    """Safe reason with no authored input or response content."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def fixture_set_hash(fixture_set: FixtureSet) -> str:
    """Hash immutable authored content without display name, note, or timestamp."""
    bindings: list[JsonValue] = []
    for binding in fixture_set.bindings:
        request = binding.request
        answer = binding.answer
        error = binding.error
        bindings.append(
            {
                "id": binding.id,
                "case_id": binding.case_id,
                "adapter": request.adapter,
                "compiler": request.compiler,
                "compiler_version": request.compiler_version,
                "requested_model": request.requested_model,
                "destination": request.destination,
                "body_hash": request.body_hash,
                "body_bytes_hash": bytes_hash(request.body),
                "answer": {
                    "schema_version": answer.schema_version,
                    "question_id": answer.question_id,
                    "option_id": answer.option_id,
                    "probabilities_source": answer.probabilities_source,
                    "native_confidence_source": answer.native_confidence_source,
                    "native_confidence_semantics": answer.native_confidence_semantics,
                    "reported_model": answer.reported_model,
                }
                if answer is not None
                else None,
                "error": {
                    "schema_version": error.schema_version,
                    "code": error.code,
                    "resource_id": error.resource_id,
                    "row": error.row,
                    "reason": error.reason,
                }
                if error is not None
                else None,
            }
        )
    return semantic_hash(
        {
            "decision_id": fixture_set.decision_id,
            "dataset_id": fixture_set.dataset_id,
            "model_identity": fixture_set.model_identity,
            "evidence_mode": fixture_set.evidence_mode,
            "bindings": bindings,
        }
    )


def _request_options(request: CompiledRequest) -> tuple[str, set[str]]:
    if (
        request.adapter != "fixture"
        or request.compiler != "jev-choice"
        or request.destination != FIXTURE_DESTINATION
    ):
        raise FixtureInvalid("fixture_request_identity")
    try:
        CompiledRequest(
            adapter=request.adapter,
            compiler=request.compiler,
            compiler_version=request.compiler_version,
            requested_model=request.requested_model,
            destination=request.destination,
            body=request.body,
            body_hash=request.body_hash,
        )
        verify_compiled_request(request)
        root = parse_json(request.body, GENERATED_LIMITS)
        if not isinstance(root, dict):
            raise FixtureInvalid("fixture_request_shape")
        questions = root["questions"]
        if not isinstance(questions, dict) or len(questions) != 1:
            raise FixtureInvalid("fixture_request_shape")
        question_id = next(iter(questions))
        question = questions[question_id]
        if not isinstance(question, dict):
            raise FixtureInvalid("fixture_request_shape")
        criteria = question["criteria"]
        if not isinstance(criteria, dict):
            raise FixtureInvalid("fixture_request_shape")
        return question_id, set(criteria)
    except (ValidationError, ResponseInvalid, JsonError, KeyError, TypeError):
        raise FixtureInvalid("fixture_request_shape") from None


def _probability(source: str) -> Decimal:
    try:
        value = parse_json(source)
    except JsonError:
        raise FixtureInvalid("invalid_authored_confidence") from None
    if not isinstance(value, Decimal) or not 0 <= value <= 1:
        raise FixtureInvalid("invalid_authored_confidence")
    return value


def _validate_answer(
    answer: NormalizedAnswer, question_id: str, option_ids: set[str], model_identity: str
) -> None:
    if answer.question_id != question_id:
        raise FixtureInvalid("fixture_question_mismatch")
    if answer.option_id not in option_ids:
        raise FixtureInvalid("fixture_unknown_option")
    if answer.reported_model != model_identity:
        raise FixtureInvalid("fixture_model_mismatch")
    if answer.native_confidence_source is None:
        if answer.native_confidence_semantics is not None:
            raise FixtureInvalid("fixture_confidence_semantics")
    else:
        if answer.native_confidence_semantics != "authored_fixture_confidence":
            raise FixtureInvalid("fixture_confidence_semantics")
        _probability(answer.native_confidence_source)
    if answer.probabilities_source is None:
        return
    try:
        probabilities = parse_json(answer.probabilities_source)
    except JsonError:
        raise FixtureInvalid("invalid_authored_probability") from None
    if not isinstance(probabilities, dict) or set(probabilities) != option_ids:
        raise FixtureInvalid("fixture_probability_options")
    numeric: dict[str, Decimal] = {}
    for option_id, value in probabilities.items():
        if not isinstance(value, Decimal) or not 0 <= value <= 1:
            raise FixtureInvalid("invalid_authored_probability")
        numeric[option_id] = value
    with localcontext() as context:
        context.prec = 30_000
        if abs(sum(numeric.values(), Decimal(0)) - 1) > SUM_TOLERANCE:
            raise FixtureInvalid("fixture_probability_sum")
        if max(numeric.values()) - numeric[answer.option_id] > SUM_TOLERANCE:
            raise FixtureInvalid("fixture_choice_not_argmax")


def validate_fixture_set(fixture_set: FixtureSet) -> None:
    """Validate every binding before storage or dispatch, including the named hash."""
    if fixture_set_hash(fixture_set) != fixture_set.content_hash:
        raise FixtureInvalid("fixture_content_hash")
    for binding in fixture_set.bindings:
        question_id, option_ids = _request_options(binding.request)
        if binding.request.requested_model != fixture_set.model_identity:
            raise FixtureInvalid("fixture_model_mismatch")
        if binding.answer is not None:
            _validate_answer(binding.answer, question_id, option_ids, fixture_set.model_identity)


class FixtureCaseTransport:
    """A runner creates one instance per case; dispatch itself carries no case ID."""

    def __init__(self, fixture_set: FixtureSet, case_id: str) -> None:
        self._set = fixture_set
        try:
            self._case_id = validate_resource_id(case_id)
        except ValueError:
            raise FixtureInvalid("invalid_case_id") from None

    async def dispatch(
        self, request: CompiledRequest, *, timeout_seconds: float
    ) -> DispatchOutcome:
        # No network or clock is consulted. The caller's timeout belongs to the
        # common transport contract, not to authored fixture timing evidence.
        try:
            _request_options(request)
        except FixtureInvalid:
            return DispatchOutcome(
                state="not_sent",
                error=ServiceError(code="preflight_failed", reason="fixture_request_invalid"),
            )
        for binding in self._set.bindings:
            bound = binding.request
            if (
                binding.case_id == self._case_id
                and bound.compiler == request.compiler
                and bound.compiler_version == request.compiler_version
                and bound.body_hash == request.body_hash
                and bound.body == request.body
                and bound.adapter == request.adapter
                and bound.destination == request.destination
                and bound.requested_model == request.requested_model
            ):
                if binding.answer is not None:
                    return DispatchOutcome(state="known", answer=binding.answer)
                return DispatchOutcome(state="known", error=binding.error)
        return DispatchOutcome(
            state="not_sent", error=ServiceError(code="missing_fixture", reason="binding_not_found")
        )


class FixtureTransportFactory:
    def __init__(self, fixture_set: FixtureSet) -> None:
        validate_fixture_set(fixture_set)
        self.fixture_set = fixture_set

    def for_case(self, case_id: str) -> FixtureCaseTransport:
        return FixtureCaseTransport(self.fixture_set, case_id)
