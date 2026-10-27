"""Pure choice compilation and strict Jev wire normalization."""

from deykit.contracts.images import ImageAsset
from deykit.contracts.json_value import (
    JsonValue,
    bytes_hash,
    dump_json,
)
from deykit.contracts.ports import CompilerIdentity
from deykit.contracts.records import (
    ChoiceDefinition,
    CompiledRequest,
    NormalizedAnswer,
    ProviderProfile,
)
from deykit.domain.jev_request_v1 import verify_request_v1
from deykit.domain.jev_response_v1 import JEV_DESTINATION_V1, MODEL_VERSION_V1, validate_response_v1
from deykit.providers.jev_images import attach_images, verify_images
from deykit.providers.response import ResponseInvalid as ResponseInvalid

COMPILER_ID = "jev-choice"
COMPILER_VERSION = "1"
JEV_DESTINATION = JEV_DESTINATION_V1
MODELS_DESTINATION = "https://api.typesafe.ai/v1/models"
MODEL_VERSION = MODEL_VERSION_V1


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


def validate_response(request: CompiledRequest, source: str | bytes) -> NormalizedAnswer:
    """Strict provider wire validation. Generic optional answer fields do not relax it."""
    return validate_response_v1(request, source, verify_request=_verify_compiled_request_v1)


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


def _verify_compiled_request_v1(request: CompiledRequest) -> None:
    verify_request_v1(request, verify_images=verify_images)


def verify_compiled_request(request: CompiledRequest) -> None:
    """Check persisted or externally constructed records before credential resolution."""
    _verify_compiled_request_v1(request)
