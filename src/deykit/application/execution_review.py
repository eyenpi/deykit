"""Exact, read-only review projection for a single prepared run plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from deykit.application.dataset_support import fail
from deykit.contracts.errors import ServiceError
from deykit.contracts.identities import ContentHash
from deykit.contracts.json_value import (
    GENERATED_LIMITS,
    JsonError,
    JsonLimits,
    JsonValue,
    bytes_hash,
    dump_json,
    parse_json,
)
from deykit.contracts.ports import Collection
from deykit.contracts.redaction import Sanitizer
from deykit.runner.planner import PlannedCase, RunPlan
from deykit.runner.views import RunPreview, preview_view


@dataclass(frozen=True)
class ReviewSourceRecord:
    collection: Collection
    scope: tuple[str, ...]
    resource_id: str
    etag: ContentHash
    body_hash: ContentHash


@dataclass(frozen=True)
class ReviewedRunContext:
    definition_source: Literal["draft", "revision"]
    revision_id: str | None
    definition_hash: ContentHash
    source_context_hash: ContentHash
    provider_id: str
    destination: str
    adapter: str
    requested_model: str
    compiler_id: str
    compiler_version: str
    fixture_set_id: str | None
    source_records: tuple[ReviewSourceRecord, ...]
    development_case_ids: tuple[str, ...]
    development_label_count: int


@dataclass(frozen=True)
class ReviewedCase:
    case_id: str
    input_hash: ContentHash
    request_hash: ContentHash | None
    compiler: str | None
    compiler_version: str | None
    requested_model: str | None
    input_error: ServiceError | None
    request_source: str | None
    request_source_redacted: bool | None
    semantic_headers_source: str | None = None


@dataclass(frozen=True)
class ReviewedRunPreview:
    preview: RunPreview
    review_context: ReviewedRunContext
    case_reviews: tuple[ReviewedCase, ...]


def _safe_identity(sanitizer: Sanitizer, value: str) -> str:
    if sanitizer.text(value) != value:
        fail("sensitive_review_identity", "preflight_failed")
    return value


def _safe_request_source(
    source: bytes, sanitizer: Sanitizer, limits: JsonLimits = GENERATED_LIMITS
) -> tuple[str, bool]:
    try:
        text = source.decode("utf-8", "strict")
        value = parse_json(text, limits)
        safe_value = cast(JsonValue, sanitizer.value(value))
        if safe_value == value:
            return text, False
        return dump_json(safe_value, limits=limits), True
    except (UnicodeDecodeError, JsonError):
        fail("invalid_compiled_request", "preflight_failed")


def reviewed_run_preview(
    plan: RunPlan,
    *,
    include_request_source: bool,
    sanitizer: Sanitizer | None = None,
) -> ReviewedRunPreview:
    """Project review details exclusively from the plan already used for its hash."""
    safe = sanitizer or Sanitizer()
    context = ReviewedRunContext(
        definition_source="revision" if plan.selection.revision_id is not None else "draft",
        revision_id=(
            _safe_identity(safe, plan.selection.revision_id)
            if plan.selection.revision_id is not None
            else None
        ),
        definition_hash=_safe_identity(safe, plan.definition_hash),
        source_context_hash=_safe_identity(safe, plan.context_hash),
        provider_id=_safe_identity(safe, plan.provider.id),
        destination=safe.text(plan.provider.destination),
        adapter=safe.text(plan.provider.adapter),
        requested_model=safe.text(plan.provider.requested_model),
        compiler_id=safe.text(plan.review_compiler.compiler),
        compiler_version=safe.text(plan.review_compiler.compiler_version),
        fixture_set_id=(
            _safe_identity(safe, plan.selection.fixture_set_id)
            if plan.selection.fixture_set_id is not None
            else None
        ),
        source_records=tuple(
            ReviewSourceRecord(
                collection=record.key.collection,
                scope=tuple(_safe_identity(safe, part) for part in record.key.scope),
                resource_id=_safe_identity(safe, record.key.resource_id),
                etag=_safe_identity(safe, record.etag),
                body_hash=_safe_identity(safe, bytes_hash(record.body)),
            )
            for record in plan.review_records
        ),
        development_case_ids=tuple(case.id for case in plan.development_cases),
        development_label_count=len(plan.development_labels),
    )

    def review_case(prepared: PlannedCase) -> ReviewedCase:
        request_source: str | None = None
        request_source_redacted: bool | None = None
        if include_request_source and prepared.request is not None:
            request_source, request_source_redacted = _safe_request_source(
                prepared.request.body, safe, prepared.request.body_limits
            )
        return ReviewedCase(
            case_id=_safe_identity(safe, prepared.case_id),
            input_hash=_safe_identity(safe, prepared.input_hash),
            request_hash=(
                _safe_identity(safe, prepared.request.body_hash)
                if prepared.request is not None
                else None
            ),
            compiler=(
                safe.text(prepared.request.compiler) if prepared.request is not None else None
            ),
            compiler_version=(
                safe.text(prepared.request.compiler_version)
                if prepared.request is not None
                else None
            ),
            requested_model=(
                safe.text(prepared.request.requested_model)
                if prepared.request is not None
                else None
            ),
            input_error=prepared.error,
            request_source=request_source,
            request_source_redacted=request_source_redacted,
            semantic_headers_source=(
                _safe_request_source(prepared.request.semantic_headers_source.encode(), safe)[0]
                if prepared.request is not None
                else None
            ),
        )

    cases = tuple(review_case(prepared) for prepared in plan.prepared)
    return ReviewedRunPreview(
        preview=preview_view(plan), review_context=context, case_reviews=cases
    )
