"""Pure choice compilation and strict Jev wire normalization."""

import re

from deykit.contracts.images import ImageAsset
from deykit.contracts.json_value import (
    JsonValue,
    bytes_hash,
    dump_json,
    parse_json,
)
from deykit.contracts.ports import CompilerIdentity
from deykit.contracts.records import (
    ChoiceDefinition,
    CompiledRequest,
    NormalizedAnswer,
    ProviderProfile,
)
from deykit.providers.jev_images import attach_images, verify_images
from deykit.providers.response import ResponseInvalid as ResponseInvalid
from deykit.providers.response import object_value as _object
from deykit.providers.response import probability as _probability
from deykit.providers.response import usage_count as _usage
from deykit.providers.response import validate_distribution

COMPILER_ID = "jev-choice"
COMPILER_VERSION = "1"
JEV_DESTINATION = "https://api.typesafe.ai/v1/systemone"
MODELS_DESTINATION = "https://api.typesafe.ai/v1/models"
MODEL_VERSION = re.compile(r"jev-[0-9]+\.[0-9]+\.[0-9]+(?:[-.][A-Za-z0-9]+)*\Z")


def compile_choice(
    definition: "ChoiceDefinition",
    selected_state: JsonValue,
    requested_model: str,
    *,
    adapter: str = "jev",
) -> "CompiledRequest":
    """Compile validated, selected input; never accept a CaseRecord or labels."""
    if definition.selected_images:
        raise ValueError("Image compilation is not supported by the text choice compiler.")
    if adapter not in {"jev", "fixture"}:
        raise ValueError("Unsupported choice adapter.")
    if not requested_model or requested_model.strip() != requested_model:
        raise ValueError("A nonempty explicit model is required.")
    if adapter == "jev" and not (
        MODEL_VERSION.fullmatch(requested_model) or requested_model in {"jev-latest", "jev-preview"}
    ):
        raise ValueError("Unsupported Jev model identity.")
    question = definition.questions[0]
    if len(question.options) > 255:
        raise ValueError("Jev choice supports at most 255 options.")
    if definition.input_kind == "text":
        if not isinstance(selected_state, str):
            raise ValueError("Selected text state must be a string.")
    elif not isinstance(selected_state, dict) or (
        definition.selected_fields and set(selected_state) != set(definition.selected_fields)
    ):
        raise ValueError("JSON state must contain exactly the declared selected fields.")
    criteria: dict[str, JsonValue] = {
        option.id: {"name": option.name, "description": option.description}
        for option in question.options
    }
    body = dump_json(
        {
            "state": selected_state,
            "model": requested_model,
            "questions": {
                question.id: {
                    "type": "choice",
                    "instructions": question.instructions,
                    "criteria": criteria,
                }
            },
        }
    ).encode("utf-8")
    return CompiledRequest(
        adapter=adapter,
        compiler=COMPILER_ID,
        compiler_version=COMPILER_VERSION,
        requested_model=requested_model,
        destination=JEV_DESTINATION if adapter == "jev" else "fixture:jev-choice",
        body=body,
        body_hash=bytes_hash(body),
    )


def validate_response(request: "CompiledRequest", source: str | bytes) -> "NormalizedAnswer":
    """Strict provider wire validation. Generic optional answer fields do not relax it."""
    try:
        root = _object(parse_json(source), "object_required")
    except ValueError:
        raise ResponseInvalid("invalid_json") from None
    verify_compiled_request(request)
    compiled = _object(parse_json(request.body, request.body_limits), "invalid_request")
    questions = _object(compiled.get("questions"), "invalid_request")
    if len(questions) != 1:
        raise ResponseInvalid("invalid_request")
    question_id = next(iter(questions))
    criteria = _object(
        _object(questions[question_id], "invalid_request").get("criteria"), "invalid_request"
    )
    answers = _object(root.get("answers"), "missing_answers")
    if set(answers) != {question_id}:
        raise ResponseInvalid("question_mismatch")
    answer = _object(answers[question_id], "invalid_answer")
    if answer.get("type") != "choice":
        raise ResponseInvalid("type_mismatch")
    choice = answer.get("choice")
    if not isinstance(choice, str) or choice not in criteria:
        raise ResponseInvalid("unknown_option")
    probabilities = _object(answer.get("probabilities"), "missing_probabilities")
    if set(probabilities) != set(criteria):
        raise ResponseInvalid("probability_option_mismatch")
    numeric = {
        key: _probability(value, "invalid_probability") for key, value in probabilities.items()
    }
    validate_distribution(numeric, choice)
    confidence = _probability(answer.get("confidence"), "invalid_confidence")
    model = root.get("model")
    if not isinstance(model, str) or not MODEL_VERSION.fullmatch(model):
        raise ResponseInvalid("invalid_model")
    if MODEL_VERSION.fullmatch(request.requested_model) and model != request.requested_model:
        raise ResponseInvalid("model_pin_mismatch")
    usage = _object(root.get("usage"), "missing_usage")
    _usage(usage.get("input_tokens"))
    _usage(usage.get("output_tokens"))
    return NormalizedAnswer(
        question_id=question_id,
        option_id=choice,
        probabilities_source=dump_json(probabilities),
        native_confidence_source=dump_json(confidence),
        native_confidence_semantics="jev_native_distribution_confidence",
        reported_model=model,
    )


class JevChoiceCompiler:
    @property
    def review_identity(self) -> CompilerIdentity:
        return CompilerIdentity(compiler=COMPILER_ID, compiler_version=COMPILER_VERSION)

    def compile(
        self,
        definition: ChoiceDefinition,
        selected_state: JsonValue,
        profile: ProviderProfile,
    ) -> CompiledRequest:
        expected = JEV_DESTINATION if profile.adapter == "jev" else "fixture:jev-choice"
        if profile.destination != expected:
            raise ValueError("Profile destination does not match the choice compiler.")
        return compile_choice(
            definition, selected_state, profile.requested_model, adapter=profile.adapter
        )

    def validate_response(self, request: CompiledRequest, response_source: str) -> NormalizedAnswer:
        return validate_response(request, response_source)

    def compile_images(
        self,
        definition: ChoiceDefinition,
        selected_state: JsonValue,
        profile: ProviderProfile,
        images: tuple[tuple[str, ImageAsset], ...],
    ) -> CompiledRequest:
        if not images or tuple(name for name, _ in images) != definition.selected_images:
            raise ValueError("selected_image_mismatch")
        request = self.compile(
            definition.model_copy(update={"selected_images": ()}), selected_state, profile
        )
        return attach_images(request, images)


def verify_compiled_request(request: CompiledRequest) -> None:
    """Check persisted or externally constructed records before credential resolution."""
    try:
        CompiledRequest.model_validate(request.model_dump())
        root = _object(parse_json(request.body, request.body_limits), "invalid_request")
        expected = {"state", "model", "questions"}
        if "assets" in root:
            expected.add("assets")
        if set(root) != expected:
            raise ValueError
        if "assets" in root:
            verify_images(root, request.semantic_headers_source)
        elif request.semantic_headers_source != "{}":
            raise ValueError
        if root["model"] != request.requested_model or not isinstance(root["state"], (str, dict)):
            raise ValueError
        questions = _object(root["questions"], "invalid_request")
        if len(questions) != 1:
            raise ValueError
        question_id = next(iter(questions))
        question = _object(questions[question_id], "invalid_request")
        if set(question) != {"type", "instructions", "criteria"} or question["type"] != "choice":
            raise ValueError
        criteria = _object(question["criteria"], "invalid_request")
        if not 2 <= len(criteria) <= 255:
            raise ValueError
        from deykit.contracts.records import ChoiceOption, ChoiceQuestion

        options = []
        for key, value in criteria.items():
            option = _object(value, "invalid_request")
            if set(option) != {"name", "description"}:
                raise ValueError
            options.append(ChoiceOption.model_validate({"id": key, **option}))
        ChoiceQuestion.model_validate(
            {"id": question_id, "instructions": question["instructions"], "options": tuple(options)}
        )
    except ValueError:
        raise ResponseInvalid("invalid_request") from None
