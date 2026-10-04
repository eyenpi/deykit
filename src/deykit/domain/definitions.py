"""Stable choice identities, model input selection, and label applicability."""

from typing import Literal, cast

from deykit.contracts.json_value import JsonDocument, JsonError, JsonValue, semantic_hash
from deykit.contracts.records import ChoiceDefinition, LabelRecord
from deykit.contracts.schema import validate_json


def definition_hash(definition: ChoiceDefinition) -> str:
    """Semantic model-affecting fields; schema source whitespace is not meaningful."""
    value = definition.model_dump(mode="json")
    schema = value.pop("input_schema_source")
    value["input_schema"] = JsonDocument(schema).value if schema is not None else None
    return semantic_hash(cast(JsonValue, value))


def select_input(definition: ChoiceDefinition, document: JsonDocument) -> JsonDocument:
    """Validate the complete input before selecting model fields."""
    value = document.value
    if not isinstance(value, str if definition.input_kind == "text" else dict):
        raise JsonError("invalid_case_input_shape")
    if definition.input_schema_source is not None:
        if validate_json(definition.input_schema_source, document.source):
            raise JsonError("input_schema_mismatch")
    if definition.input_kind == "json" and definition.selected_fields:
        return document.select(definition.selected_fields)
    return document


def missing_options(
    definition: ChoiceDefinition, question_id: str, expected_ids: tuple[str, ...]
) -> tuple[str, ...]:
    """Keep removed IDs visible, including when the whole question was replaced."""
    question = next((q for q in definition.questions if q.id == question_id), None)
    present = {option.id for option in question.options} if question else set()
    return tuple(option_id for option_id in expected_ids if option_id not in present)


ApplicabilityReason = Literal["disputed", "stale", "incompatible"]


def label_applicability(
    label: LabelRecord, definition: ChoiceDefinition, input_hash: str
) -> tuple[ApplicabilityReason, ...]:
    reasons: list[ApplicabilityReason] = []
    if label.status == "disputed":
        reasons.append("disputed")
    if label.input_hash != input_hash:
        reasons.append("stale")
    if missing_options(definition, label.question_id, label.acceptable_option_ids):
        reasons.append("incompatible")
    return tuple(reasons)
