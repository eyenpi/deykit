"""Pure OpenAI Decisions choice compilation and strict response admission."""

from deykit.contracts.images import IMAGE_REQUEST_LIMITS, ImageAsset
from deykit.contracts.json_value import JsonLimits, JsonValue, bytes_hash, dump_json, parse_json
from deykit.contracts.ports import CompilerIdentity
from deykit.contracts.provider_configuration import CredentialReference
from deykit.contracts.records import (
    ChoiceDefinition,
    ChoiceOption,
    ChoiceQuestion,
    CompiledRequest,
    NormalizedAnswer,
    ProviderProfile,
)
from deykit.providers.openai_images import image_parts, verify_image_parts
from deykit.providers.response import (
    ResponseInvalid,
    object_value,
    probability,
    usage_count,
    validate_distribution,
)

COMPILER_ID = "openai-decisions-choice"
COMPILER_VERSION = "1"
DESTINATION = "https://api.openai.com/v1/decisions"
MODEL = "gpt-6-luna"
JSON_INPUT_LIMITS = JsonLimits(max_bytes=256 * 1024, max_depth=32, max_nodes=10_000)


def validate_profile(profile: ProviderProfile) -> ProviderProfile:
    if profile.adapter != "openai" or profile.destination != DESTINATION:
        raise ValueError("Only the official OpenAI Decisions destination is supported.")
    if profile.requested_model != MODEL:
        raise ValueError("Unsupported OpenAI Decisions model identity.")
    if profile.credential_ref is not None:
        CredentialReference.parse(profile.credential_ref)
    return profile


def _input(definition: ChoiceDefinition, state: JsonValue) -> JsonValue:
    if definition.input_kind == "text":
        if not isinstance(state, str):
            raise ValueError("Selected text input must be a string.")
        return state
    if not isinstance(state, dict) or (
        definition.selected_fields and set(state) != set(definition.selected_fields)
    ):
        raise ValueError("JSON input must contain exactly the selected fields.")
    dump_json(state, limits=JSON_INPUT_LIMITS)
    return [{"role": "user", "content": [{"type": "input_json", "data": state}]}]


def _compiled(
    root: dict[str, JsonValue], profile: ProviderProfile, *, images: bool = False
) -> CompiledRequest:
    body = dump_json(root, limits=IMAGE_REQUEST_LIMITS).encode("utf-8")
    return CompiledRequest(
        adapter="openai",
        compiler=COMPILER_ID,
        compiler_version=COMPILER_VERSION,
        requested_model=profile.requested_model,
        destination=DESTINATION,
        body=body,
        body_hash=bytes_hash(body),
        body_kind="image_json" if images else "json",
    )


class OpenAIChoiceCompiler:
    @property
    def review_identity(self) -> CompilerIdentity:
        return CompilerIdentity(compiler=COMPILER_ID, compiler_version=COMPILER_VERSION)

    def compile(
        self,
        definition: ChoiceDefinition,
        selected_state: JsonValue,
        profile: ProviderProfile,
    ) -> CompiledRequest:
        validate_profile(profile)
        if definition.selected_images:
            raise ValueError("Selected images require image compilation.")
        question = definition.questions[0]
        if len(question.options) > 255:
            raise ValueError("OpenAI Decisions supports at most 255 choices.")
        return _compiled(
            {
                "model": profile.requested_model,
                "input": _input(definition, selected_state),
                "questions": [
                    {
                        "type": "choice",
                        "name": question.id,
                        "instructions": question.instructions,
                        "choices": [
                            {
                                "value": option.id,
                                "description": option.name
                                + ("\n" + option.description if option.description else ""),
                            }
                            for option in question.options
                        ],
                    }
                ],
            },
            profile,
        )

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
            definition.model_copy(update={"selected_images": ()}),
            selected_state,
            profile,
        )
        root = object_value(parse_json(request.body, request.body_limits), "invalid_request")
        if isinstance(root["input"], str):
            content: list[JsonValue] = [{"type": "input_text", "text": root["input"]}]
            root["input"] = [{"role": "user", "content": content}]
        else:
            content = _content(root["input"])
        content.extend(
            image_parts(images, len(dump_json(root, limits=IMAGE_REQUEST_LIMITS).encode()))
        )
        return _compiled(root, profile, images=True)

    def validate_response(self, request: CompiledRequest, response_source: str) -> NormalizedAnswer:
        return validate_response(request, response_source)


def _content(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list) or len(value) != 1:
        raise ValueError("invalid_input")
    message = object_value(value[0], "invalid_input")
    if set(message) != {"role", "content"} or message["role"] != "user":
        raise ValueError("invalid_input")
    content = message["content"]
    if not isinstance(content, list) or not content:
        raise ValueError("invalid_input")
    return content


def verify_compiled_request(request: CompiledRequest) -> None:
    """Admit frozen requests before credentials; only the compiler's wire subset is allowed."""
    try:
        CompiledRequest.model_validate(request.model_dump())
        if (
            request.adapter,
            request.compiler,
            request.compiler_version,
            request.requested_model,
            request.destination,
            request.semantic_headers_source,
        ) != (
            "openai",
            COMPILER_ID,
            COMPILER_VERSION,
            MODEL,
            DESTINATION,
            "{}",
        ):
            raise ValueError
        root = object_value(parse_json(request.body, request.body_limits), "invalid_request")
        if set(root) != {"model", "input", "questions"} or root["model"] != MODEL:
            raise ValueError
        if not isinstance(root["input"], str):
            content = _content(root["input"])
            first = object_value(content[0], "invalid_input")
            if first.get("type") == "input_json":
                if set(first) != {"type", "data"} or not isinstance(first["data"], dict):
                    raise ValueError
                dump_json(first["data"], limits=JSON_INPUT_LIMITS)
            elif (
                set(first) != {"type", "text"}
                or first["type"] != "input_text"
                or not isinstance(first["text"], str)
            ):
                raise ValueError
            verify_image_parts(content[1:])
        questions = root["questions"]
        if not isinstance(questions, list) or len(questions) != 1:
            raise ValueError
        question = object_value(questions[0], "invalid_request")
        if (
            set(question) != {"type", "name", "instructions", "choices"}
            or question["type"] != "choice"
        ):
            raise ValueError
        choices = question["choices"]
        if not isinstance(choices, list) or not 2 <= len(choices) <= 255:
            raise ValueError
        options = []
        for value in choices:
            choice = object_value(value, "invalid_request")
            if set(choice) != {"value", "description"} or not isinstance(
                choice["description"], str
            ):
                raise ValueError
            options.append(
                ChoiceOption.model_validate(
                    {"id": choice["value"], "name": "Choice", "description": choice["description"]}
                )
            )
        ChoiceQuestion.model_validate(
            {
                "id": question["name"],
                "instructions": question["instructions"],
                "options": tuple(options),
            }
        )
    except ValueError:
        raise ResponseInvalid("invalid_request") from None


def validated_usage(root: dict[str, JsonValue]) -> str:
    usage = object_value(root.get("usage"), "missing_usage")
    inputs, outputs = (
        usage_count(usage.get("input_tokens")),
        usage_count(usage.get("output_tokens")),
    )
    if usage_count(usage.get("total_tokens")) != inputs + outputs:
        raise ResponseInvalid("invalid_usage")
    input_details = object_value(usage.get("input_tokens_details"), "invalid_usage")
    output_details = object_value(usage.get("output_tokens_details"), "invalid_usage")
    cached = usage_count(input_details.get("cached_tokens"))
    written = usage_count(input_details.get("cache_write_tokens"))
    reasoning = usage_count(output_details.get("reasoning_tokens"))
    if cached + written > inputs or reasoning > outputs:
        raise ResponseInvalid("invalid_usage")
    return dump_json(usage)


def validate_response(request: CompiledRequest, source: str | bytes) -> NormalizedAnswer:
    verify_compiled_request(request)
    try:
        root = object_value(parse_json(source), "object_required")
    except ValueError:
        raise ResponseInvalid("invalid_json") from None
    if root.get("model") != request.requested_model:
        raise ResponseInvalid("model_pin_mismatch")
    compiled = object_value(parse_json(request.body, request.body_limits), "invalid_request")
    questions = compiled["questions"]
    assert isinstance(questions, list)
    question = object_value(questions[0], "invalid_request")
    choices = question["choices"]
    assert isinstance(choices, list)
    option_ids = [object_value(item, "invalid_request")["value"] for item in choices]
    answers = root.get("answers")
    if not isinstance(answers, list) or len(answers) != 1:
        raise ResponseInvalid("question_mismatch")
    answer = object_value(answers[0], "invalid_answer")
    if answer.get("name") != question["name"]:
        raise ResponseInvalid("question_mismatch")
    if answer.get("type") == "refusal":
        raise ResponseInvalid("provider_refusal")
    if answer.get("type") != "choice":
        raise ResponseInvalid("type_mismatch")
    choice = answer.get("choice")
    if not isinstance(choice, str) or choice not in option_ids:
        raise ResponseInvalid("unknown_option")
    values = answer.get("probabilities")
    if not isinstance(values, list):
        raise ResponseInvalid("missing_probabilities")
    numeric = {}
    for value in values:
        entry = object_value(value, "invalid_probability")
        option_id = entry.get("value")
        if not isinstance(option_id, str) or option_id not in option_ids or option_id in numeric:
            raise ResponseInvalid("probability_option_mismatch")
        numeric[option_id] = probability(entry.get("probability"), "invalid_probability")
    if len(numeric) != len(option_ids):
        raise ResponseInvalid("probability_option_mismatch")
    validate_distribution(numeric, choice)
    confidence = probability(answer.get("confidence"), "invalid_confidence")
    validated_usage(root)
    question_id = question["name"]
    assert isinstance(question_id, str)
    return NormalizedAnswer(
        question_id=question_id,
        option_id=choice,
        probabilities_source=dump_json(
            {key: numeric[key] for key in option_ids if isinstance(key, str)}
        ),
        native_confidence_source=dump_json(confidence),
        native_confidence_semantics="openai_decisions_native_distribution_confidence",
        reported_model=request.requested_model,
    )
