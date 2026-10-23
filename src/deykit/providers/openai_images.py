"""Bounded inline images for OpenAI Decisions, without paths or remote URLs."""

import base64
import io
import struct

from PIL import Image

from deykit.contracts.images import (
    IMAGE_REQUEST_LIMITS,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    ImageAsset,
)
from deykit.contracts.json_value import JsonError, JsonValue, dump_json

MIME_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def _inspect(body: bytes, format: str) -> tuple[int, int]:
    if not 0 < len(body) <= MAX_IMAGE_BYTES or format not in MIME_TYPES:
        raise ValueError("image_byte_or_format_limit")
    try:
        with Image.open(io.BytesIO(body), formats=tuple(MIME_TYPES)) as image:
            if image.format != format:
                raise ValueError("image_format_mismatch")
            if (
                image.width > 8192
                or image.height > 8192
                or image.width * image.height > MAX_IMAGE_PIXELS
                or getattr(image, "n_frames", 1) != 1
            ):
                raise ValueError("image_resource_or_animation_limit")
            image.load()
            return image.size
    except (OSError, SyntaxError, IndexError, struct.error, Image.DecompressionBombError):
        raise ValueError("image_decode_failed") from None


def image_parts(images: tuple[tuple[str, ImageAsset], ...], request_bytes: int) -> list[JsonValue]:
    parts: list[JsonValue] = []
    for name, asset in images:
        label: JsonValue = {"type": "input_text", "text": f"Image: {name}"}
        prefix = f"data:{MIME_TYPES[asset.prepared.format]};base64,"
        part: dict[str, JsonValue] = {"type": "input_image", "image_url": prefix, "detail": "auto"}
        request_bytes += len(dump_json([label, part]).encode()) + 4 * (
            (asset.prepared.byte_count + 2) // 3
        )
        if request_bytes > IMAGE_REQUEST_LIMITS.max_bytes:
            raise JsonError("json_resource_limit")
        body = asset.prepared_bytes()
        if _inspect(body, asset.prepared.format) != (asset.prepared.width, asset.prepared.height):
            raise ValueError("image_dimensions_mismatch")
        part["image_url"] = prefix + base64.b64encode(body).decode("ascii")
        parts.extend((label, part))
    return parts


def verify_image_parts(parts: list[JsonValue]) -> None:
    if len(parts) % 2:
        raise ValueError("invalid_image_parts")
    from deykit.contracts.identities import validate_resource_id

    names: set[str] = set()
    for index in range(0, len(parts), 2):
        label, part = parts[index : index + 2]
        if (
            not isinstance(label, dict)
            or set(label) != {"type", "text"}
            or label["type"] != "input_text"
            or not isinstance(label["text"], str)
            or not label["text"].startswith("Image: ")
        ):
            raise ValueError("invalid_image_label")
        name = validate_resource_id(label["text"][len("Image: ") :])
        if name in names:
            raise ValueError("duplicate_image_name")
        names.add(name)
        if (
            not isinstance(part, dict)
            or set(part) != {"type", "image_url", "detail"}
            or part["type"] != "input_image"
            or part["detail"] != "auto"
            or not isinstance(part["image_url"], str)
        ):
            raise ValueError("invalid_image_part")
        prefix, separator, encoded = part["image_url"].partition(";base64,")
        format = next((fmt for fmt, mime in MIME_TYPES.items() if prefix == f"data:{mime}"), None)
        if not separator or format is None or len(encoded) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
            raise ValueError("invalid_inline_image")
        body = base64.b64decode(encoded, validate=True)
        if base64.b64encode(body).decode("ascii") != encoded:
            raise ValueError("noncanonical_image_encoding")
        _inspect(body, format)
