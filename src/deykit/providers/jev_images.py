"""Jev image wire compilation and admission, with no filesystem or network access."""

import base64
import io
import struct
from collections.abc import Iterator

from PIL import Image

from deykit.contracts.images import IMAGE_REQUEST_LIMITS, MAX_IMAGE_BYTES, ImageAsset
from deykit.contracts.json_value import JsonError, JsonValue, bytes_hash, dump_json, parse_json
from deykit.contracts.records import CompiledRequest

IMAGE_HEADER = "TypeSafe-Danger-Zone-Images"
IMAGE_HEADERS_SOURCE = '{"TypeSafe-Danger-Zone-Images":"true"}'


def _strings(value: JsonValue) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _inspect(body: bytes, format: str) -> tuple[int, int]:
    if not 0 < len(body) <= MAX_IMAGE_BYTES:
        raise ValueError("image_byte_limit")
    if format not in {"png", "jpg"}:
        raise ValueError("image_format_unsupported")
    try:
        with Image.open(io.BytesIO(body), formats=("PNG", "JPEG")) as image:
            if image.format != {"png": "PNG", "jpg": "JPEG"}[format]:
                raise ValueError("image_format_mismatch")
            if not (280 <= image.width <= 1568 and 280 <= image.height <= 1568):
                raise ValueError("image_dimensions_unsupported")
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("image_animation_unsupported")
            image.load()
            return image.size
    except (OSError, SyntaxError, IndexError, struct.error, Image.DecompressionBombError):
        raise ValueError("image_decode_failed") from None


def attach_images(
    request: CompiledRequest, images: tuple[tuple[str, ImageAsset], ...]
) -> CompiledRequest:
    root = parse_json(request.body, request.body_limits)
    assert isinstance(root, dict)
    selected = root["state"]
    state: dict[str, JsonValue] = (
        dict(selected) if isinstance(selected, dict) else {"text": selected}
    )
    existing = tuple(_strings(root))
    assets: dict[str, JsonValue] = {}
    root["state"], root["assets"] = state, assets
    request_bytes = len(dump_json(root, limits=IMAGE_REQUEST_LIMITS).encode("utf-8"))
    reference_bytes = 0
    for index, (name, asset) in enumerate(images):
        if name in state:
            raise ValueError("image_state_name_collision")
        format = {"PNG": "png", "JPEG": "jpg"}.get(asset.prepared.format)
        if format is None:
            raise ValueError("image_format_unsupported")
        nonce = 0
        while True:
            reference = f"deykit-image-{index}-{asset.prepared.content_hash}-{nonce:08x}~"
            if not any(reference in text for text in existing):
                break
            nonce += 1
        reference_bytes += len(reference.encode("utf-8"))
        if reference_bytes > 65_536:
            raise ValueError("image_reference_limit")
        entry: dict[str, JsonValue] = {"type": "image", "format": format, "data_base64": ""}
        # Count each entry without its braces, plus its separator and base64 bytes,
        # before decoding or encoding the admitted asset. Repeated selections count too.
        request_bytes += (
            len(dump_json({name: reference}).encode("utf-8"))
            - 2
            + bool(state)
            + len(dump_json({reference: entry}).encode("utf-8"))
            - 2
            + bool(assets)
            + 4 * ((asset.prepared.byte_count + 2) // 3)
        )
        if request_bytes > IMAGE_REQUEST_LIMITS.max_bytes:
            raise JsonError("json_resource_limit")
        body = asset.prepared_bytes()
        if _inspect(body, format) != (asset.prepared.width, asset.prepared.height):
            raise ValueError("image_dimensions_mismatch")
        entry["data_base64"] = base64.b64encode(body).decode("ascii")
        state[name] = reference
        assets[reference] = entry
    if not assets:
        raise ValueError("image_reference_limit")
    body = dump_json(root, limits=IMAGE_REQUEST_LIMITS).encode("utf-8")
    return CompiledRequest(
        adapter=request.adapter,
        compiler=request.compiler,
        compiler_version=request.compiler_version,
        requested_model=request.requested_model,
        destination=request.destination,
        body=body,
        body_hash=bytes_hash(body),
        semantic_headers_source=IMAGE_HEADERS_SOURCE,
    )


def verify_images(root: dict[str, JsonValue], headers_source: str) -> None:
    if headers_source != IMAGE_HEADERS_SOURCE:
        raise ValueError("image_header_required")
    assets, state = root["assets"], root["state"]
    if not isinstance(assets, dict) or not assets or not isinstance(state, dict):
        raise ValueError("invalid_image_assets")
    if sum(len(key.encode()) for key in assets) > 65_536:
        raise ValueError("image_reference_limit")
    text = tuple(_strings({"state": state, "questions": root["questions"]}))
    for reference, value in assets.items():
        if (
            not reference.strip()
            or len(reference.encode()) > 1024
            or reference not in state.values()
            or sum(part.count(reference) for part in text) != 1
        ):
            raise ValueError("image_reference_collision")
        if (
            not isinstance(value, dict)
            or set(value) != {"type", "format", "data_base64"}
            or value["type"] != "image"
            or not isinstance(value["format"], str)
            or not isinstance(value["data_base64"], str)
        ):
            raise ValueError("invalid_image_asset")
        encoded = value["data_base64"]
        if len(encoded) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
            raise ValueError("image_byte_limit")
        body = base64.b64decode(encoded, validate=True)
        if base64.b64encode(body).decode("ascii") != encoded:
            raise ValueError("noncanonical_image_encoding")
        _inspect(body, value["format"])
