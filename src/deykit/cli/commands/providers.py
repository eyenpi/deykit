"""Portable provider profiles and explicit local credential diagnostics."""

from __future__ import annotations

import asyncio
import getpass
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from deykit.application.errors import ServiceFailure
from deykit.cli.context import CliState, new_operation_id, projects_service
from deykit.cli.input import source_text
from deykit.cli.output import execute
from deykit.contracts.codec import load_record
from deykit.contracts.errors import ErrorCode, ServiceError
from deykit.contracts.json_value import JsonError
from deykit.contracts.records import ProviderProfile
from deykit.providers.choice import COMPILER_VERSION, JEV_DESTINATION
from deykit.providers.credentials import (
    CredentialReference,
    Credentials,
    CredentialUnavailable,
    credentials_for,
    os_secret_store,
)
from deykit.providers.fixtures import FIXTURE_DESTINATION
from deykit.providers.profiles import ProfileView, ProviderProfiles

provider_app = typer.Typer(help="Manage non-secret provider and authored fixture profiles.")
credential_app = typer.Typer(help="Manage credential references and explicit OS-store values.")
DEFAULT_JEV_ENV = "JEV_API_KEY"


def register(root: typer.Typer) -> None:
    root.add_typer(provider_app, name="provider")
    root.add_typer(credential_app, name="credential")
    root.command("doctor")(doctor)


def _failure(code: ErrorCode, reason: str) -> ServiceFailure:
    return ServiceFailure(ServiceError(code=code, reason=reason))


def _configured(view: ProfileView) -> dict[str, object]:
    profile = view.profile
    return {
        "view": view,
        "compiler": {"id": "jev-choice", "version": COMPILER_VERSION},
        "capabilities": {
            "input_kinds": ("text", "json"),
            "question_kind": "choice",
            "max_options": 255,
            "evidence_mode": "authored_fixture" if profile.adapter == "fixture" else "live",
        },
        "credential": {
            "configured": profile.credential_ref is not None,
            "kind": (
                CredentialReference.parse(profile.credential_ref).kind
                if profile.credential_ref is not None
                else None
            ),
        },
    }


def _etag(profiles: ProviderProfiles, profile_id: str, if_hash: str | None) -> str | None:
    if if_hash is not None:
        return if_hash
    try:
        return profiles.view(profile_id).etag
    except ServiceFailure as error:
        if error.error.code == "not_found":
            return None
        raise


def _configured_profile(
    profile_id: str,
    *,
    file: Path | None,
    stdin: bool,
    adapter: str | None,
    model: str | None,
    credential_env: str | None,
) -> ProviderProfile:
    if file is not None or stdin:
        if adapter is not None or model is not None or credential_env is not None:
            raise _failure("validation_error", "input_mode_conflict")
        try:
            profile = load_record(
                ProviderProfile, source_text(file=file, stdin=stdin).encode("utf-8")
            )
        except (JsonError, ValidationError, ValueError):
            raise _failure("validation_error", "invalid_provider_profile") from None
        if profile.id != profile_id:
            raise _failure("validation_error", "profile_id_mismatch")
        return profile
    if adapter not in ("jev", "fixture") or model is None:
        raise _failure("validation_error", "profile_options_required")
    if adapter == "fixture":
        if credential_env is not None:
            raise _failure("validation_error", "fixture_has_no_credential")
        try:
            return ProviderProfile(
                id=profile_id,
                adapter="fixture",
                requested_model=model,
                destination=FIXTURE_DESTINATION,
            )
        except ValidationError:
            raise _failure("validation_error", "invalid_provider_profile") from None
    reference = "env:" + (credential_env if credential_env is not None else DEFAULT_JEV_ENV)
    try:
        CredentialReference.parse(reference)
        return ProviderProfile(
            id=profile_id,
            adapter="jev",
            requested_model=model,
            destination=JEV_DESTINATION,
            credential_ref=reference,
        )
    except (ValidationError, ValueError):
        raise _failure("validation_error", "invalid_provider_profile") from None


@provider_app.command("list")
def provider_list(
    ctx: typer.Context,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 50,
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            return ProviderProfiles(source).list_views(cursor=cursor, limit=limit)

    execute(ctx, work)


@provider_app.command("show")
def provider_show(ctx: typer.Context, profile_id: str) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            return _configured(ProviderProfiles(source).view(profile_id))

    execute(ctx, work)


@provider_app.command("configure")
def provider_configure(
    ctx: typer.Context,
    profile_id: str,
    file: Annotated[Path | None, typer.Option("--file")] = None,
    stdin: Annotated[bool, typer.Option("--stdin")] = False,
    adapter: Annotated[str | None, typer.Option("--adapter")] = None,
    model: Annotated[str | None, typer.Option("--model")] = None,
    credential_env: Annotated[str | None, typer.Option("--credential-env")] = None,
    if_hash: Annotated[str | None, typer.Option("--if-hash")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    actual = new_operation_id(operation_id)

    def work(cli: CliState) -> object:
        candidate = _configured_profile(
            profile_id,
            file=file,
            stdin=stdin,
            adapter=adapter,
            model=model,
            credential_env=credential_env,
        )
        with cli.source() as source:
            profiles = ProviderProfiles(source)
            receipt = profiles.configure(
                candidate,
                expected_etag=_etag(profiles, profile_id, if_hash),
                operation_id=actual,
            )
            return {
                "operation_id": actual,
                "profile": _configured(profiles.from_receipt(receipt)),
                "replayed": receipt.replayed,
            }

    execute(ctx, work)


def _status(profile: ProviderProfile) -> dict[str, object]:
    reference = profile.credential_ref
    return {
        "profile_id": profile.id,
        "configured": reference is not None,
        "available": credentials_for(profile).status(reference) if reference is not None else False,
        "kind": CredentialReference.parse(reference).kind if reference is not None else None,
    }


@credential_app.command("status")
def credential_status(
    ctx: typer.Context,
    provider: Annotated[str, typer.Option("--provider")],
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            return _status(ProviderProfiles(source).read(provider))

    execute(ctx, work)


def _secret(stdin: bool, prompt: bool) -> str:
    if stdin == prompt:
        raise _failure("validation_error", "secret_input_mode_required")
    if stdin:
        source = typer.get_binary_stream("stdin").read().decode("utf-8", errors="strict")
        return source.rstrip("\r\n")
    if not typer.get_text_stream("stdin").isatty():
        raise _failure("validation_error", "interactive_required")
    return getpass.getpass("Credential: ")


@credential_app.command("set")
def credential_set(
    ctx: typer.Context,
    provider: Annotated[str, typer.Option("--provider")],
    env: Annotated[str | None, typer.Option("--env")] = None,
    stdin: Annotated[bool, typer.Option("--stdin")] = False,
    prompt: Annotated[bool, typer.Option("--prompt")] = False,
    if_hash: Annotated[str | None, typer.Option("--if-hash")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    actual = new_operation_id(operation_id)

    def work(cli: CliState) -> object:
        if sum((env is not None, stdin, prompt)) != 1:
            raise _failure("validation_error", "input_mode_conflict")
        with cli.source() as source:
            profiles = ProviderProfiles(source)
            reference = (
                "env:" + env
                if env is not None
                else CredentialReference("keyring", "deykit", provider).encode()
            )
            try:
                CredentialReference.parse(reference)
            except ValueError:
                raise _failure("validation_error", "invalid_credential_reference") from None
            expected = if_hash if if_hash is not None else profiles.view(provider).etag
            replay = profiles.credential_replay(
                provider, reference, expected_etag=expected, operation_id=actual
            )
            if replay is not None:
                return {
                    "operation_id": actual,
                    "profile": _configured(profiles.from_receipt(replay)),
                    "replayed": True,
                }
            current = profiles.view(provider)
            if current.etag != expected:
                raise _failure("conflict", "provider_profile_changed")
            if current.profile.adapter != "jev":
                raise _failure("validation_error", "fixture_has_no_credential")
            if env is None:
                value = _secret(stdin, prompt)
                try:
                    Credentials(store=os_secret_store()).set(reference, value)
                except (CredentialUnavailable, ValueError):
                    raise _failure("preflight_failed", "credential_store_unavailable") from None
            receipt = profiles.set_credential_ref(
                provider, reference, expected_etag=expected, operation_id=actual
            )
            return {
                "operation_id": actual,
                "profile": _configured(profiles.from_receipt(receipt)),
                "replayed": receipt.replayed,
            }

    execute(ctx, work)


@credential_app.command("forget")
def credential_forget(
    ctx: typer.Context,
    provider: Annotated[str, typer.Option("--provider")],
    if_hash: Annotated[str | None, typer.Option("--if-hash")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    actual = new_operation_id(operation_id)

    def work(cli: CliState) -> object:
        with cli.source() as source:
            profiles = ProviderProfiles(source)
            expected = if_hash if if_hash is not None else profiles.view(provider).etag
            replay = profiles.credential_replay(
                provider, None, expected_etag=expected, operation_id=actual
            )
            if replay is not None:
                return {
                    "operation_id": actual,
                    "profile": _configured(profiles.from_receipt(replay)),
                    "replayed": True,
                }
            current = profiles.view(provider)
            if current.etag != expected:
                raise _failure("conflict", "provider_profile_changed")
            if current.profile.adapter != "jev":
                raise _failure("validation_error", "fixture_has_no_credential")
            reference = current.profile.credential_ref
            if reference is not None and CredentialReference.parse(reference).kind == "keyring":
                try:
                    Credentials(store=os_secret_store()).forget(reference)
                except (CredentialUnavailable, ValueError):
                    raise _failure("preflight_failed", "credential_store_unavailable") from None
            receipt = profiles.set_credential_ref(
                provider, None, expected_etag=expected, operation_id=actual
            )
            return {
                "operation_id": actual,
                "profile": _configured(profiles.from_receipt(receipt)),
                "replayed": receipt.replayed,
            }

    execute(ctx, work)


def _models(profile: ProviderProfile, timeout_seconds: float) -> tuple[dict[str, str], ...]:
    from deykit.providers.choice import ResponseInvalid
    from deykit.providers.http import HttpFailure
    from deykit.providers.jev import JevProvider

    if profile.adapter != "jev":
        raise _failure("preflight_failed", "models_require_live_provider")
    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 600:
        raise _failure("validation_error", "invalid_timeout")
    provider = JevProvider(profile, credentials_for(profile))
    try:
        return asyncio.run(provider.models(timeout_seconds=timeout_seconds))
    except CredentialUnavailable:
        raise _failure("preflight_failed", "credential_unavailable") from None
    except ResponseInvalid:
        raise _failure("response_invalid", "invalid_models") from None
    except HttpFailure as error:
        raise _failure("provider_rejected", error.kind) from None
    except ValueError:
        raise _failure("provider_rejected", "model_list_failed") from None


@provider_app.command("models")
def provider_models(
    ctx: typer.Context,
    profile_id: str,
    timeout_seconds: Annotated[float, typer.Option("--timeout-seconds")] = 60,
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            profile = ProviderProfiles(source).read(profile_id)
        return {
            "profile_id": profile_id,
            "network_check": True,
            "models": _models(profile, timeout_seconds),
        }

    execute(ctx, work)


@dataclass(frozen=True)
class DoctorResult:
    project: object
    profile_count: int
    provider: object | None = None
    network: object | None = None


def doctor(
    ctx: typer.Context,
    provider: Annotated[str | None, typer.Option("--provider")] = None,
    network_check: Annotated[bool, typer.Option("--network-check")] = False,
    timeout_seconds: Annotated[float, typer.Option("--timeout-seconds")] = 60,
) -> None:
    def work(cli: CliState) -> object:
        if network_check and provider is None:
            raise _failure("validation_error", "provider_required")
        path = cli.require_project()
        project = projects_service().validate(path)
        with cli.source() as source:
            profiles = ProviderProfiles(source)
            listed = profiles.list()
            selected = profiles.read(provider) if provider is not None else None
        return DoctorResult(
            project=project,
            profile_count=len(listed),
            provider=_status(selected) if selected is not None else None,
            network={"model_count": len(_models(selected, timeout_seconds)), "inference_calls": 0}
            if network_check and selected is not None
            else None,
        )

    execute(ctx, work)
