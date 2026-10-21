"""Label identity includes original images, independently of their preparation."""

from deykit.contracts.json_value import JsonDocument, bytes_hash, canonical_bytes, semantic_hash
from deykit.contracts.records import CaseRecord, ChoiceDefinition


def case_input_hash(case: CaseRecord) -> str:
    document = JsonDocument(case.input_source)
    if not case.images:
        return document.content_hash
    return bytes_hash(
        b"deykit-image-input-v1\n"
        + canonical_bytes(
            {
                "input": document.value,
                "images": [
                    [image.name, image.source_hash]
                    for image in sorted(case.images, key=lambda image: image.name)
                ],
            }
        )
    )


def image_treatment_hash(case: CaseRecord, definition: ChoiceDefinition) -> str | None:
    if not definition.selected_images:
        return None
    images = {image.name: image for image in case.images}
    if any(name not in images for name in definition.selected_images):
        raise ValueError("selected_image_missing")
    return semantic_hash([[name, images[name].asset_id] for name in definition.selected_images])
