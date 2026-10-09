import pytest

from deykit.application.errors import ServiceFailure
from deykit.application.preview_documents import (
    decode_split_preview,
    encode_split_preview,
)
from deykit.application.splits import SplitPreview


def split_document(dataset_id: str = "data") -> str:
    content_hash = "a" * 64
    input_identity = "b" * 64
    return (
        '{"schema_version":1,"data":{"preview":{'
        f'"dataset_id":"{dataset_id}","dataset_etag":"{content_hash}",'
        f'"input_identity":"{input_identity}","algorithm":"split-v1",'
        '"seed":null,"ratios_source":null,"assignments":[],"groups":[],"counts":[]'
        '}},"warnings":[]}'
    )


def test_split_preview_decoder_accepts_exact_source_as_text_or_bytes():
    source = split_document()

    assert decode_split_preview(source, "data").dataset_id == "data"
    assert decode_split_preview(source.encode("utf-8"), "data").dataset_id == "data"


def test_split_preview_encoder_round_trips_source_values_without_numeric_reconstruction():
    preview = SplitPreview(
        dataset_id="data",
        dataset_etag="a" * 64,
        input_identity="b" * 64,
        algorithm="connected-greedy-squared-v1",
        seed=None,
        ratios_source='{"development":0.1234567890123456789,"test":0.8765432109876543211}',
        assignments=(("case-1", "development"),),
        groups=(("case-1",),),
        counts=(("development", 1), ("calibration", 0), ("test", 0)),
    )

    source = encode_split_preview(preview)

    assert '"ratios_source":"{\\"development\\":0.1234567890123456789,\\"test\\":0.8765432109876543211}"' in source
    assert decode_split_preview(source, "data") == preview


@pytest.mark.parametrize(
    ("source", "dataset_id"),
    [
        (split_document(), "other"),
        (split_document().replace('"warnings":[]', '"warnings":[],"extra":true'), "data"),
        (
            split_document().replace(
                '"dataset_id":"data"', '"dataset_id":"data","extra":true'
            ),
            "data",
        ),
    ],
)
def test_split_preview_decoder_rejects_context_and_extra_fields(source: str, dataset_id: str):
    with pytest.raises(ServiceFailure) as failure:
        decode_split_preview(source, dataset_id)

    assert failure.value.error.reason == "invalid_preview_file"
