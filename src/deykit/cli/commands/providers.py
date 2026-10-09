"""Portable provider profiles and explicit local credential diagnostics."""

from __future__ import annotations

import asyncio
import getpass
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from deykit.application.errors import ServiceFailure
from deykit.application.execution import ExecutionService
from deykit.cli.context import CliState, SystemClock, new_operation_id, projects_service
from deykit.cli.input import source_text
from deykit.cli.output import CommandOutcome, execute, execute_outcome
from deykit.cli.selection import selection_context, selector_hint
from deykit.contracts.codec import load_record
from deykit.contracts.errors import ErrorCode, ServiceError
from deykit.contracts.json_value import JsonError
from deykit.contracts.provider_configuration import (
    CredentialStatus,
    ProfilePage,
    ProviderPresentation,
)
from deykit.contracts.records import ExecutionSettings, ProviderProfile
from deykit.providers.choice import JEV_DESTINATION
from deykit.providers.configuration import create_provider_operations
from deykit.providers.credentials import CredentialReference, os_secret_store
from deykit.providers.fixtures import FIXTURE_DESTINATION
from deykit.providers.profiles import ProviderProfiles
from deykit.runner.backends import ProviderBackends
from deykit.runner.planner import RunRequest
from deykit.runner.views import RunProgress

provider_app = typer.Typer(help="Manage non-secret provider and authored fixture profiles.")
credential_app = typer.Typer(help="Manage credential references and explicit OS-store values.")
DEFAULT_JEV_ENV = "JEV_API_KEY"


def register(root: typer.Typer) -> None:
    root.add_typer(provider_app, name="provider")
    root.add_typer(credential_app, name="credential")
    root.command("doctor")(doctor)


def _failure(code: ErrorCode, reason: str) -> ServiceFailure:
    return ServiceFailure(ServiceError(code=code, reason=reason))


def _configured(presentation: ProviderPresentation) -> dict[str, object]:
    return {
        "view": presentation.view,
        "compiler": {
            "id": presentation.compiler.id,
            "version": presentation.compiler.version,
        },
        "capabilities": {
            "input_kinds": presentation.capabilities.input_kinds,
            "question_kind": presentation.capabilities.question_kind,
            "max_options": presentation.capabilities.max_options,
            "evidence_mode": presentation.capabilities.evidence_mode,
        },
        "credential": {
            "configured": presentation.credential.configured,
            "kind": presentation.credential.kind,
        },
    }


def _status_payload(status: CredentialStatus) -> dict[str, object]:
    return {
        "profile_id": status.profile_id,
        "configured": status.configured,
        "available": status.available,
        "kind": status.kind,
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
            page = create_provider_operations(
                source, os_store_factory=os_secret_store
            ).list(cursor=cursor, limit=limit)
            return ProfilePage(
                tuple(item.view for item in page.items), page.total, page.next_cursor
            )

    execute(ctx, work)


@provider_app.command("show")
def provider_show(ctx: typer.Context, profile_id: str) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            with selection_context(source, (selector_hint("provider", profile_id, ()),)):
                return _configured(
                    create_provider_operations(
                        source, os_store_factory=os_secret_store
                    ).describe(profile_id)
                )

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
            with selection_context(source, (selector_hint("provider", profile_id, ()),)):
                profiles = ProviderProfiles(source)
                operations = create_provider_operations(
                    source, os_store_factory=os_secret_store
                )
                mutation = operations.configure(
                    candidate,
                    expected_etag=_etag(profiles, profile_id, if_hash),
                    operation_id=actual,
                )
                return {
                    "operation_id": actual,
                    "profile": _configured(mutation.profile),
                    "replayed": mutation.replayed,
                }

    execute(ctx, work)


@credential_app.command("status")
def credential_status(
    ctx: typer.Context,
    provider: Annotated[str, typer.Option("--provider")],
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            with selection_context(source, (selector_hint("provider", provider, ()),)):
                return _status_payload(
                    create_provider_operations(
                        source, os_store_factory=os_secret_store
                    ).credential_status(provider)
                )

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
        with (
            cli.source() as source,
            selection_context(source, (selector_hint("provider", provider, ()),)),
        ):
            profiles = ProviderProfiles(source)
            operations = create_provider_operations(source, os_store_factory=os_secret_store)
            expected = if_hash if if_hash is not None else profiles.view(provider).etag
            if env is not None:
                mutation = operations.attach_environment(
                    provider, env, expected_etag=expected, operation_id=actual
                )
            else:
                mutation = operations.set_os_credential(
                    provider,
                    value_factory=lambda: _secret(stdin, prompt),
                    expected_etag=expected,
                    operation_id=actual,
                )
            return {
                "operation_id": actual,
                "profile": _configured(mutation.profile),
                "replayed": mutation.replayed,
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
        with (
            cli.source() as source,
            selection_context(source, (selector_hint("provider", provider, ()),)),
        ):
            profiles = ProviderProfiles(source)
            operations = create_provider_operations(source, os_store_factory=os_secret_store)
            expected = if_hash if if_hash is not None else profiles.view(provider).etag
            mutation = operations.forget_credential(
                provider, expected_etag=expected, operation_id=actual
            )
            return {
                "operation_id": actual,
                "profile": _configured(mutation.profile),
                "replayed": mutation.replayed,
            }

    execute(ctx, work)


@provider_app.command("models")
def provider_models(
    ctx: typer.Context,
    profile_id: str,
    timeout_seconds: Annotated[float, typer.Option("--timeout-seconds")] = 60,
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            with selection_context(source, (selector_hint("provider", profile_id, ()),)):
                operations = create_provider_operations(source, os_store_factory=os_secret_store)
                profile = operations.describe(profile_id).view.profile
        model_list = asyncio.run(
            operations._list_models_for_profile(profile, timeout_seconds=timeout_seconds)
        )
        return {
            "profile_id": profile_id,
            "network_check": True,
            "models": model_list.models,
        }

    execute(ctx, work)


@dataclass(frozen=True)
class DoctorResult:
    project: object
    profile_count: int
    provider: object | None = None
    network: object | None = None
    smoke: object | None = None


def _smoke_summary(run: RunProgress) -> dict[str, object]:
    return {
        "run_id": run.run_id,
        "result_snapshot_id": run.latest_result_snapshot_id,
        "mode": run.mode,
        "requested_model": run.requested_model,
        "state": run.state,
        "attempts_used": run.attempts_used,
        "attempt_limit": run.attempt_limit,
        "settings": run.settings,
        "case": run.cases[0] if run.cases else None,
        "replayed": run.replayed,
    }


def doctor(
    ctx: typer.Context,
    provider: Annotated[str | None, typer.Option("--provider")] = None,
    network_check: Annotated[bool, typer.Option("--network-check")] = False,
    live_smoke: Annotated[bool, typer.Option("--live-smoke")] = False,
    decision: Annotated[str | None, typer.Option("--decision")] = None,
    dataset: Annotated[str | None, typer.Option("--dataset")] = None,
    case: Annotated[str | None, typer.Option("--case")] = None,
    timeout_seconds: Annotated[
        int,
        typer.Option(
            "--timeout-seconds",
            min=1,
            max=600,
            help="Model-list timeout; live smoke requires the fixed default of 60 seconds.",
        ),
    ] = 60,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    def work(cli: CliState) -> CommandOutcome:
        if network_check and live_smoke:
            raise _failure("validation_error", "diagnostic_mode_conflict")
        if (network_check or live_smoke) and provider is None:
            raise _failure("validation_error", "provider_required")
        if live_smoke and (decision is None or dataset is None or case is None):
            raise _failure("validation_error", "smoke_context_required")
        if live_smoke and timeout_seconds != 60:
            raise _failure("validation_error", "smoke_timeout_fixed_at_60")
        if not live_smoke and (decision is not None or dataset is not None or case is not None):
            raise _failure("validation_error", "live_smoke_required")
        if not live_smoke and operation_id is not None:
            raise _failure("validation_error", "live_smoke_required")
        path = cli.require_project()
        project = projects_service().validate(path)
        hints = tuple(
            hint
            for hint in (
                selector_hint("provider", provider, ()) if provider is not None else None,
                selector_hint("decision", decision, ()) if live_smoke and decision else None,
                selector_hint("dataset", dataset, ()) if live_smoke and dataset else None,
                selector_hint("case", case, (dataset,))
                if live_smoke and case and dataset
                else None,
            )
            if hint is not None
        )
        with cli.source() as source, selection_context(source, hints):
            profiles = ProviderProfiles(source)
            operations = create_provider_operations(source, os_store_factory=os_secret_store)
            listed = profiles.list()
            selected = profiles.read(provider) if provider is not None else None
            status = (
                _status_payload(operations.credential_status(provider))
                if selected is not None and provider is not None
                else None
            )
            if live_smoke:
                assert provider is not None and decision is not None
                assert dataset is not None and case is not None
                try:
                    request = RunRequest(
                        decision_id=decision,
                        dataset_id=dataset,
                        mode="live",
                        provider_id=provider,
                        case_ids=(case,),
                        settings=ExecutionSettings(
                            max_attempts=1,
                            concurrency=1,
                            timeout_seconds=timeout_seconds,
                            deadline_seconds=timeout_seconds,
                            max_retries_per_case=0,
                        ),
                    )
                except ValidationError:
                    raise _failure("validation_error", "invalid_smoke_request") from None
                clock = SystemClock()
                runner = ExecutionService(source, source, ProviderBackends(source, clock), clock)
                actual = new_operation_id(operation_id)
                run = asyncio.run(runner.start(request, operation_id=actual))
                return CommandOutcome(
                    DoctorResult(
                        project=project,
                        profile_count=len(listed),
                        provider=status,
                        smoke={"operation_id": actual, **_smoke_summary(run)},
                    ),
                    run.exit_code,
                )
        return CommandOutcome(
            DoctorResult(
                project=project,
                profile_count=len(listed),
                provider=status,
                network={
                    "model_count": len(
                        asyncio.run(
                            operations._list_models_for_profile(
                                selected, timeout_seconds=timeout_seconds
                            )
                        ).models
                    ),
                    "inference_calls": 0,
                }
                if network_check and selected is not None
                else None,
            )
        )

    execute_outcome(ctx, work)
