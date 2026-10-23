"""One-shot OpenAI Decisions transport using frozen, validated requests."""

import json
import re
from typing import cast

from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import JsonValue, bytes_hash, dump_json, parse_json
from deykit.contracts.records import CompiledRequest, DispatchOutcome, ProviderProfile
from deykit.providers.credentials import Credentials, CredentialUnavailable
from deykit.providers.http import HttpFailure, OneShotHttp, dispatch_failure
from deykit.providers.openai_choice import (
    validate_profile,
    validate_response,
    validated_usage,
    verify_compiled_request,
)
from deykit.providers.response import ResponseInvalid, object_value
from deykit.providers.safety import Sanitizer

_JSON_ESCAPES = re.compile(r'(?:\\(?:u[0-9a-fA-F]{4}|["\\/bfnrt]))+')


def _unparsed_evidence(body: bytes, sanitizer: Sanitizer) -> str:
    text = body.decode("utf-8", "replace")
    # Decode only escape runs, never JSON numbers or a permissive response object.
    # This exposes escaped credentials even in duplicate-key or incomplete JSON.
    decoded = _JSON_ESCAPES.sub(lambda match: json.loads('"' + match[0] + '"'), text)
    replaced = decoded.encode("utf-8", "replace").decode("utf-8")
    lone_surrogates_replaced = replaced != decoded
    decoded = replaced
    sanitized = sanitizer.text(decoded)
    encoded = sanitized.encode("utf-8")
    # Even six-byte JSON escapes per captured byte fit the 1 MiB source bound.
    captured = encoded[:150_000].decode("utf-8", "ignore")
    return dump_json(
        {
            "deykit_unparsed_response": {
                "encoding": "utf8_text",
                "body": captured,
                "normalized_json_escapes": decoded != text,
                "invalid_utf8_replaced": text.encode("utf-8") != body,
                "lone_surrogates_replaced": lone_surrogates_replaced,
                "capture_byte_count": len(captured.encode("utf-8")),
                "capture_source_byte_count": len(encoded),
                "capture_source_hash": bytes_hash(encoded),
                "changed_by_redaction": sanitized != decoded,
                "truncated": captured != sanitized,
            }
        }
    )


class OpenAIDecisionsProvider:
    def __init__(
        self,
        profile: ProviderProfile,
        credentials: Credentials,
        http: OneShotHttp | None = None,
    ) -> None:
        self.profile = validate_profile(profile)
        self._credentials = credentials
        self._http = http or OneShotHttp()

    def preflight(self) -> ServiceError | None:
        if self.profile.credential_ref is None:
            return ServiceError(code="preflight_failed", reason="credential_unavailable")
        try:
            self._credentials.resolve(self.profile.credential_ref)
        except CredentialUnavailable:
            return ServiceError(code="preflight_failed", reason="credential_unavailable")
        return None

    async def dispatch(
        self, request: CompiledRequest, *, timeout_seconds: float = 60
    ) -> DispatchOutcome:
        try:
            verify_compiled_request(request)
            if not 0 < timeout_seconds <= 600:
                raise ValueError
        except ValueError:
            return DispatchOutcome(
                state="not_sent",
                provider_wide=True,
                error=ServiceError(code="preflight_failed", reason="invalid_request_configuration"),
            )
        if request.requested_model != self.profile.requested_model:
            return DispatchOutcome(
                state="not_sent",
                provider_wide=True,
                error=ServiceError(code="preflight_failed", reason="request_profile_mismatch"),
            )
        try:
            if self.profile.credential_ref is None:
                raise CredentialUnavailable()
            credential = self._credentials.resolve(self.profile.credential_ref)
        except CredentialUnavailable:
            return DispatchOutcome(
                state="not_sent",
                provider_wide=True,
                error=ServiceError(code="preflight_failed", reason="credential_unavailable"),
            )
        try:
            reply = await self._http.send(
                "POST", request.destination, request.body, credential, timeout_seconds
            )
        except HttpFailure as error:
            return DispatchOutcome(
                state="unknown", error=ServiceError(code="provider_rejected", reason=error.kind)
            )
        if reply.status == 404:
            return DispatchOutcome(
                state="known",
                provider_wide=True,
                error=ServiceError(
                    code="provider_rejected", reason="model_or_endpoint_unavailable"
                ),
            )
        failure = dispatch_failure(reply)
        if failure is not None:
            return failure
        safe_source = usage_source = None
        sanitizer = Sanitizer([credential])
        try:
            candidate = dump_json(cast(JsonValue, sanitizer.value(parse_json(reply.body))))
            parsed = parse_json(candidate)
            safe_source = candidate
            root = object_value(parsed, "object_required")
            # Usage belongs to the attempt even when its answer is refused or invalid.
            try:
                usage_source = validated_usage(root)
            except ResponseInvalid:
                pass  # Unknown usage remains None; raw evidence retains the invalid fields.
            answer = validate_response(request, safe_source)
        except ValueError as error:
            reason = error.reason if isinstance(error, ResponseInvalid) else "invalid_json"
            if safe_source is None:
                safe_source = _unparsed_evidence(reply.body, sanitizer)
            return DispatchOutcome(
                state="known",
                error=ServiceError(code="response_invalid", reason=reason),
                raw_response_source=safe_source,
                usage_source=usage_source,
            )
        return DispatchOutcome(
            state="known", answer=answer, raw_response_source=safe_source, usage_source=usage_source
        )
