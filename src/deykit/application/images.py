"""Admission of immutable asset dependencies from a captured project epoch."""

from collections import OrderedDict
from collections.abc import Iterable, Mapping

from deykit.application.dataset_support import decoded, fail
from deykit.contracts.images import ImageAsset
from deykit.contracts.ports import ResourceKey, StoredRecord
from deykit.contracts.records import CaseRecord

MAX_ADMITTED_IMAGE_BYTES = 64 * 1024 * 1024


class ImageAssets:
    """Bounded admission reuse within one exact, independently captured record view."""

    def __init__(self, records: Mapping[ResourceKey, StoredRecord]) -> None:
        self._records = {
            key: record for key, record in records.items() if key.collection == "image_assets"
        }
        self._admitted: OrderedDict[ResourceKey, ImageAsset] = OrderedDict()
        self._retained_bytes = 0

    def for_case(self, case: CaseRecord) -> dict[str, ImageAsset]:
        assets: dict[str, ImageAsset] = {}
        for image in case.images:
            key = ResourceKey("image_assets", image.asset_id)
            stored = self._records.get(key)
            if stored is None:
                fail("image_asset_missing", "incompatible_data")
            asset = self._admitted.get(key)
            if asset is None:
                asset = decoded(ImageAsset, stored)
                weight = len(stored.body)
                if weight <= MAX_ADMITTED_IMAGE_BYTES:
                    while (
                        self._admitted and self._retained_bytes + weight > MAX_ADMITTED_IMAGE_BYTES
                    ):
                        evicted, _ = self._admitted.popitem(last=False)
                        self._retained_bytes -= len(self._records[evicted].body)
                    self._admitted[key] = asset
                    self._retained_bytes += weight
            else:
                self._admitted.move_to_end(key)
            if asset.id != image.asset_id or asset.source.content_hash != image.source_hash:
                fail("image_asset_changed", "incompatible_data")
            assets[image.name] = asset
        return assets


def case_assets(
    case: CaseRecord, records: Mapping[ResourceKey, StoredRecord]
) -> dict[str, ImageAsset]:
    return ImageAssets(records).for_case(case)


def check_case_assets(cases: Iterable[CaseRecord], records: tuple[StoredRecord, ...]) -> None:
    images = ImageAssets({record.key: record for record in records})
    for case in cases:
        images.for_case(case)
