"""Jev provider implementation of the shared one-dispatch port."""

import asyncio
import math

from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import dump_json, parse_json
from deykit.contracts.records import CompiledRequest, DispatchOutcome, ProviderProfile
from deykit.providers.choice import (
    JEV_DESTINATION,
    MODELS_DESTINATION,
    ResponseInvalid,
    _object,
    validate_response,
    verify_compiled_request,
)
from deykit.providers.credentials import CredentialReference, Credentials, CredentialUnavailable
from deykit.providers.http import HttpFailure, HttpReply, OneShotHttp
from deykit.providers.safety import Sanitizer


def validate_profile(profile: ProviderProfile) -> ProviderProfile:
    """Local-only profile validation; does not resolve credentials or list models."""
    from deykit.providers.choice import MODEL_VERSION

    if profile.adapter != "jev" or profile.destination != JEV_DESTINATION:
        raise ValueError("Only the official Jev HTTPS inference destination is supported.")
    if not (
        MODEL_VERSION.fullmatch(profile.requested_model)
        or profile.requested_model in {"jev-latest", "jev-preview"}
    ):
        raise ValueError("Unsupported Jev model identity.")
    if profile.credential_ref is None:
        raise ValueError("A credential reference is required.")
    CredentialReference.parse(profile.credential_ref)
    return profile


def _failure(reply: HttpReply) -> DispatchOutcome | None:
    status = reply.status
    if status == 200:
        return None
    if status in {401, 403}:
        return DispatchOutcome(
            state="known", error=ServiceError(code="provider_auth"), provider_wide=True
        )
    if status == 422:
        return DispatchOutcome(
            state="known",
            error=ServiceError(code="provider_rejected", reason="invalid_payload"),
            provider_wide=True,
        )
    if status in {429, 529}:
        delay = float(reply.retry_after_seconds) if reply.retry_after_seconds is not None else None
        # A finite Decimal can overflow float. An unrepresentable delay means stop
        # scheduling rather than silently shorten the provider's backoff instruction.
        if delay is not None and not math.isfinite(delay):
            return DispatchOutcome(
                state="known",
                error=ServiceError(code="provider_rejected", reason="retry_delay_out_of_range"),
                provider_wide=True,
            )
        return DispatchOutcome(
            state="known",
            error=ServiceError(
                code="provider_rejected", reason="rate_limit" if status == 429 else "overloaded"
            ),
            retryable=True,
            retry_after_seconds=delay,
        )
    return DispatchOutcome(
        state="unknown",
        error=ServiceError(code="provider_rejected", reason="unexpected_http_status"),
        provider_wide=True,
    )


class JevProvider:
    def __init__(
        self, profile: ProviderProfile, credentials: Credentials, http: OneShotHttp | None = None
    ) -> None:
        self.profile = validate_profile(profile)
        self._credentials = credentials
        self._http = http or OneShotHttp()

    def preflight(self) -> ServiceError | None:
        try:
            self._credentials.resolve(self.profile.credential_ref or "")
        except CredentialUnavailable:
            return ServiceError(code="preflight_failed", reason="credential_unavailable")
        return None

    async def dispatch(
        self,
        request: CompiledRequest,
        *,
        timeout_seconds: float = 60,
    ) -> DispatchOutcome:
        return await asyncio.to_thread(self._dispatch, request, timeout_seconds=timeout_seconds)

    def _dispatch(self, request: CompiledRequest, *, timeout_seconds: float) -> DispatchOutcome:
        try:
            verify_compiled_request(request)
            if not 0 < timeout_seconds <= 600:
                raise ValueError
        except ValueError:
            return DispatchOutcome(
                state="not_sent",
                error=ServiceError(code="preflight_failed", reason="invalid_request_configuration"),
                provider_wide=True,
            )
        if (
            request.adapter != "jev"
            or request.destination != self.profile.destination
            or request.requested_model != self.profile.requested_model
            or request.compiler != "jev-choice"
            or request.compiler_version != "1"
        ):
            return DispatchOutcome(
                state="not_sent",
                error=ServiceError(code="preflight_failed", reason="request_profile_mismatch"),
                provider_wide=True,
            )
        try:
            credential = self._credentials.resolve(self.profile.credential_ref or "")
        except CredentialUnavailable:
            return DispatchOutcome(
                state="not_sent",
                error=ServiceError(code="preflight_failed", reason="credential_unavailable"),
                provider_wide=True,
            )
        sanitizer = Sanitizer([credential])
        try:
            reply = self._http.send(
                "POST", request.destination, request.body, credential, timeout_seconds
            )
        except HttpFailure as error:
            return DispatchOutcome(
                state="unknown", error=ServiceError(code="provider_rejected", reason=error.kind)
            )
        failure = _failure(reply)
        if failure is not None:
            return failure
        safe_source = None
        try:
            # Sanitize first: an echoed key cannot escape in a normalized field.
            safe_source = dump_json(sanitizer.value(parse_json(reply.body)))
            answer = validate_response(request, safe_source)
        except ValueError as error:
            reason = error.reason if isinstance(error, ResponseInvalid) else "invalid_json"
            return DispatchOutcome(
                state="known",
                error=ServiceError(code="response_invalid", reason=reason),
                raw_response_source=safe_source,
            )
        root = _object(parse_json(safe_source), "invalid_response")
        return DispatchOutcome(
            state="known",
            answer=answer,
            raw_response_source=safe_source,
            usage_source=dump_json(root["usage"]),
        )

    def models(self, *, timeout_seconds: float = 60) -> tuple[dict[str, str], ...]:
        """Explicit network diagnostic: one GET, zero inference requests."""
        credential = self._credentials.resolve(self.profile.credential_ref or "")
        reply = self._http.send("GET", MODELS_DESTINATION, None, credential, timeout_seconds)
        if reply.status != 200:
            raise ValueError(
                "Jev model listing failed; check credentials and provider availability."
            )
        sanitizer = Sanitizer([credential])
        try:
            root = _object(parse_json(reply.body), "invalid_models")
            models = root.get("models")
            if not isinstance(models, list):
                raise ResponseInvalid("invalid_models")
            result: list[dict[str, str]] = []
            for item in models:
                record = _object(item, "invalid_models")
                if any(
                    not isinstance(record.get(key), str) or not record[key]
                    for key in ("name", "description", "release_date")
                ):
                    raise ResponseInvalid("invalid_models")
                result.append(
                    {
                        key: sanitizer.text(str(record[key]))
                        for key in ("name", "description", "release_date")
                    }
                )
            return tuple(result)
        except ValueError:
            raise ResponseInvalid("invalid_models") from None
