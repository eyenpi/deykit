"""Provider-neutral, content-addressed local image evidence; no image I/O."""

from __future__ import annotations

import base64
from typing import Annotated, Literal, Protocol, Self, cast

from pydantic import Field, model_validator

from deykit.contracts.base import FrozenModel, Record
from deykit.contracts.identities import ContentHash, ResourceId
from deykit.contracts.json_value import JsonValue, bytes_hash, semantic_hash

MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
Dimension = Annotated[int, Field(ge=1, le=8192)]
Channel = Annotated[int, Field(ge=0, le=255)]


class ImagePreparationError(ValueError):
    """A stable adapter reason, without a local path or image content."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class ImagePreparation(FrozenModel):
    mode: Literal["preserve", "pad"] = "preserve"
    min_width: Dimension | None = None
    min_height: Dimension | None = None
    background: tuple[Channel, Channel, Channel] = (255, 255, 255)
    algorithm: Literal["center-pad-rgb-v1"] = "center-pad-rgb-v1"

    @model_validator(mode="after")
    def explicit_transform(self) -> Self:
        if self.mode == "preserve":
            if (
                self.min_width is not None
                or self.min_height is not None
                or self.background != (255, 255, 255)
            ):
                raise ValueError("preserve_has_no_transform_settings")
        elif self.min_width is None or self.min_height is None:
            raise ValueError("padding_dimensions_required")
        return self


class ImageInfo(FrozenModel):
    content_hash: ContentHash
    byte_count: Annotated[int, Field(ge=1, le=MAX_IMAGE_BYTES)]
    width: Dimension
    height: Dimension
    format: Literal["PNG", "JPEG", "WEBP"]
    mode: Literal["1", "L", "LA", "P", "RGB", "RGBA", "CMYK", "I", "I;16"]

    @model_validator(mode="after")
    def pixel_limit(self) -> Self:
        if self.width * self.height > MAX_IMAGE_PIXELS:
            raise ValueError("image_pixel_limit")
        return self


class ImageIdentity(FrozenModel):
    id: ResourceId
    source: ImageInfo
    prepared: ImageInfo
    preparation: ImagePreparation

    @model_validator(mode="after")
    def content_address(self) -> Self:
        expected = image_asset_id(self.source, self.prepared, self.preparation)
        if self.id != expected:
            raise ValueError("image_asset_identity_mismatch")
        if self.preparation.mode == "preserve" and self.source != self.prepared:
            raise ValueError("image_preservation_mismatch")
        if self.preparation.mode == "pad":
            assert (
                self.preparation.min_width is not None and self.preparation.min_height is not None
            )
            dimensions = (
                max(self.source.width, self.preparation.min_width),
                max(self.source.height, self.preparation.min_height),
            )
            if (self.prepared.width, self.prepared.height) != dimensions:
                raise ValueError("image_padding_dimensions_mismatch")
            if dimensions == (self.source.width, self.source.height):
                if self.source != self.prepared:
                    raise ValueError("unnecessary_image_transformation")
            elif (
                self.source.mode != "RGB"
                or self.prepared.mode != "RGB"
                or self.prepared.format != "PNG"
            ):
                raise ValueError("invalid_padding_format")
        return self


def image_asset_id(source: ImageInfo, prepared: ImageInfo, preparation: ImagePreparation) -> str:
    return "image-" + semantic_hash(
        cast(
            JsonValue,
            {
                "source": source.model_dump(mode="json"),
                "prepared": prepared.model_dump(mode="json"),
                "preparation": preparation.model_dump(mode="json"),
            },
        )
    )


class ImageAsset(ImageIdentity, Record):
    source_base64: Annotated[str, Field(max_length=4 * ((MAX_IMAGE_BYTES + 2) // 3))]
    prepared_base64: Annotated[str, Field(max_length=4 * ((MAX_IMAGE_BYTES + 2) // 3))] | None = (
        None
    )

    def source_bytes(self) -> bytes:
        return base64.b64decode(self.source_base64, validate=True)

    def prepared_bytes(self) -> bytes:
        return (
            self.source_bytes()
            if self.prepared_base64 is None
            else base64.b64decode(self.prepared_base64, validate=True)
        )

    def identity(self) -> ImageIdentity:
        return ImageIdentity(
            id=self.id, source=self.source, prepared=self.prepared, preparation=self.preparation
        )

    @model_validator(mode="after")
    def exact_bytes(self) -> Self:
        for value, info in (
            (self.source_bytes(), self.source),
            (self.prepared_bytes(), self.prepared),
        ):
            if len(value) != info.byte_count or bytes_hash(value) != info.content_hash:
                raise ValueError("image_asset_bytes_mismatch")
        if base64.b64encode(self.source_bytes()).decode("ascii") != self.source_base64:
            raise ValueError("noncanonical_image_encoding")
        if (
            self.prepared_base64 is not None
            and base64.b64encode(self.prepared_bytes()).decode("ascii") != self.prepared_base64
        ):
            raise ValueError("noncanonical_image_encoding")
        if self.preparation.mode == "preserve" and self.prepared_base64 is not None:
            raise ValueError("redundant_prepared_image")
        return self


class CaseImage(FrozenModel):
    name: ResourceId
    asset_id: ResourceId
    source_hash: ContentHash


class SelectedImage(FrozenModel):
    name: ResourceId
    asset: ImageIdentity


class ImageReader(Protocol):
    def prepare(self, path: str, preparation: ImagePreparation) -> ImageAsset: ...
