from deykit.providers.safety import Sanitizer


def test_a42_recursively_redacts_credentials_headers_and_unknown_objects():
    sentinel = "AUTH_SENTINEL_FOR_OFFLINE_TESTS"
    sanitizer = Sanitizer([sentinel])
    safe = sanitizer.value(
        {
            "configuration": {"api_key": sentinel},
            "nested": [{"request_headers": {"Authorization": "Bearer " + sentinel}}],
            "message": "transport failed with " + sentinel,
            "unknown": ValueError(sentinel),
            "bearer": "Bearer arbitrary-credential",
            "count": 2,
        }
    )
    assert sentinel not in str(safe)
    assert "arbitrary-credential" not in str(safe)
    assert safe["count"] == 2
    assert sentinel not in repr(sanitizer)


def test_secret_is_redacted_in_mapping_keys_and_longest_first():
    sanitizer = Sanitizer(["short", "short-long"])
    assert sanitizer.value({"short-long": "short-long"}) == {"[REDACTED]": "[REDACTED]"}
