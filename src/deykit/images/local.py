"""Bounded local image loading and explicit, deterministic RGB canvas padding."""

import base64
import io
import warnings
from pathlib import Path, PurePosixPath

from PIL import Image, UnidentifiedImageError

from deykit.application.errors import ServiceFailure
from deykit.contracts.images import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    ImageAsset,
    ImageInfo,
    ImagePreparation,
    ImagePreparationError,
    image_asset_id,
)
from deykit.contracts.json_value import bytes_hash
from deykit.storage.filesystem import SafeFiles


def _open(body: bytes) -> Image.Image:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        image = Image.open(io.BytesIO(body), formats=("PNG", "JPEG", "WEBP"))
        if (
            image.width > 8192
            or image.height > 8192
            or image.width * image.height > MAX_IMAGE_PIXELS
            or getattr(image, "n_frames", 1) != 1
        ):
            image.close()
            raise ImagePreparationError("image_resource_or_animation_limit")
        image.load()
        return image


def _info(body: bytes, image: Image.Image) -> ImageInfo:
    return ImageInfo.model_validate(
        {
            "content_hash": bytes_hash(body),
            "byte_count": len(body),
            "width": image.width,
            "height": image.height,
            "format": image.format,
            "mode": image.mode,
        }
    )


class LocalImages:
    def __init__(self, root: Path) -> None:
        if not root.is_absolute():
            raise ValueError("absolute_image_root_required")
        # Construction performs no required read: completed import retries can
        # replay their receipts after the original directory has been removed.
        self.root = root.resolve()

    def prepare(self, path: str, preparation: ImagePreparation) -> ImageAsset:
        relative = PurePosixPath(path)
        if (
            not path
            or relative.is_absolute()
            or ".." in relative.parts
            or "\\" in path
            or ":" in path
        ):
            raise ImagePreparationError("unsafe_image_path")
        try:
            files = SafeFiles(self.root)
            try:
                original = files.read(relative.parts, limit=MAX_IMAGE_BYTES)
            finally:
                files.close()
            if not original or len(original) > MAX_IMAGE_BYTES:
                raise ImagePreparationError("image_byte_limit")
            with _open(original) as image:
                source = _info(original, image)
                prepared_bytes = original
                prepared = source
                if preparation.mode == "pad":
                    assert preparation.min_width is not None and preparation.min_height is not None
                    width = max(image.width, preparation.min_width)
                    height = max(image.height, preparation.min_height)
                    if width * height > MAX_IMAGE_PIXELS:
                        raise ImagePreparationError("image_pixel_limit")
                    if (width, height) != image.size:
                        if image.mode != "RGB" or image.getexif().get(274, 1) != 1:
                            raise ImagePreparationError("padding_requires_unoriented_rgb")
                        with Image.new("RGB", (width, height), preparation.background) as canvas:
                            canvas.paste(
                                image, ((width - image.width) // 2, (height - image.height) // 2)
                            )
                            output = io.BytesIO()
                            canvas.save(output, format="PNG", compress_level=0)
                            prepared_bytes = output.getvalue()
                            canvas.format = "PNG"
                            prepared = _info(prepared_bytes, canvas)
            return ImageAsset(
                id=image_asset_id(source, prepared, preparation),
                source=source,
                prepared=prepared,
                preparation=preparation,
                source_base64=base64.b64encode(original).decode("ascii"),
                prepared_base64=base64.b64encode(prepared_bytes).decode("ascii")
                if prepared_bytes != original
                else None,
            )
        except ImagePreparationError:
            raise
        except ServiceFailure as error:
            reason = (
                "image_byte_limit"
                if error.error.reason == "record_resource_limit"
                else "image_file_unavailable_or_unsafe"
            )
            raise ImagePreparationError(reason) from None
        except (
            OSError,
            UnidentifiedImageError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            ValueError,
        ):
            raise ImagePreparationError("image_decode_or_format_failed") from None
