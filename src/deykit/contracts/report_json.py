"""Bounds for owned aggregate reports, separate from individual user JSON sources."""

from typing import Annotated

from pydantic import AfterValidator, StringConstraints

from deykit.contracts.json_value import JsonLimits, parse_json

REPORT_CONTENT_LIMITS = JsonLimits(max_bytes=12 * 1024 * 1024, max_depth=128, max_nodes=750_000)
REPORT_ARTIFACT_MAX_BYTES = 16 * 1024 * 1024


def validate_report_source(source: str) -> str:
    parse_json(source, REPORT_CONTENT_LIMITS)
    return source


ReportContentSource = Annotated[
    str, StringConstraints(strict=True), AfterValidator(validate_report_source)
]
