"""Decision authoring commands, directly adapting DecisionService."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypeVar

import typer

from deykit.application.definitions import DecisionService
from deykit.cli.context import CliState, SystemClock, new_operation_id
from deykit.cli.input import optional_source, source_text
from deykit.cli.output import execute
from deykit.cli.selection import selection_context, selector_hint
from deykit.contracts.identities import new_id

decision_app = typer.Typer(help="Author choice definitions and immutable revisions.")
T = TypeVar("T")


def register(root: typer.Typer) -> None:
    root.add_typer(decision_app, name="decision")


def _mutate(
    ctx: typer.Context,
    operation_id: str | None,
    work: Callable[[CliState, str], T],
) -> None:
    actual_id = new_operation_id(operation_id)
    execute(ctx, lambda cli: {"operation_id": actual_id, "result": work(cli, actual_id)})


@decision_app.command("list")
def list_decisions(
    ctx: typer.Context,
    include_archived: Annotated[bool, typer.Option("--include-archived")] = False,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 50,
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            return DecisionService(source, SystemClock()).list(
                include_archived=include_archived, cursor=cursor, limit=limit
            )

    execute(ctx, work)


@decision_app.command("show")
def show_decision(
    ctx: typer.Context,
    decision_id: str,
    revision: Annotated[str | None, typer.Option("--revision")] = None,
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            hints = (selector_hint("decision", decision_id, ()),) + (
                (selector_hint("revision", revision, (decision_id,)),) if revision else ()
            )
            with selection_context(source, hints):
                service = DecisionService(source, SystemClock())
                view = service.read(decision_id)
                if revision is None:
                    return view
                return {
                    "decision": view.decision,
                    "revision": service.revision(decision_id, revision),
                }

    execute(ctx, work)


@decision_app.command("create")
def create_decision(
    ctx: typer.Context,
    decision_id: str,
    name: Annotated[str, typer.Option("--name")],
    file: Annotated[Path | None, typer.Option("--file")] = None,
    stdin: Annotated[bool, typer.Option("--stdin")] = False,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    def work(cli: CliState, op: str) -> object:
        text = optional_source(file=file, stdin=stdin)
        with cli.source() as source:
            with selection_context(source, (selector_hint("decision", decision_id, ()),)):
                return DecisionService(source, SystemClock()).create(
                    decision_id, name, text, operation_id=op
                )

    _mutate(ctx, operation_id, work)


@decision_app.command("edit")
def edit_decision(
    ctx: typer.Context,
    decision_id: str,
    file: Annotated[Path | None, typer.Option("--file")] = None,
    stdin: Annotated[bool, typer.Option("--stdin")] = False,
    editor: Annotated[bool, typer.Option("--editor")] = False,
    from_revision: Annotated[str | None, typer.Option("--from-revision")] = None,
    if_hash: Annotated[str | None, typer.Option("--if-hash")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    def work(cli: CliState, op: str) -> object:
        from deykit.application.errors import ServiceFailure
        from deykit.contracts.errors import ServiceError

        if sum((file is not None, stdin, editor, from_revision is not None)) != 1:
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="input_mode_conflict")
            )
        with cli.source() as source:
            hints = (selector_hint("decision", decision_id, ()),) + (
                (selector_hint("revision", from_revision, (decision_id,)),) if from_revision else ()
            )
            with selection_context(source, hints):
                service = DecisionService(source, SystemClock())
                view = service.read(decision_id) if if_hash is None or editor else None
                if if_hash is None:
                    assert view is not None
                    expected = view.draft.etag
                else:
                    expected = if_hash
                if from_revision is not None:
                    return service.restore_revision_to_draft(
                        decision_id,
                        from_revision,
                        expected_draft_etag=expected,
                        operation_id=op,
                    )
                text = source_text(
                    file=file,
                    stdin=stdin,
                    editor=editor,
                    initial=view.draft.record.editor_source if view is not None else "",
                )
                return service.update_draft(
                    decision_id, text, expected_etag=expected, operation_id=op
                )

    _mutate(ctx, operation_id, work)


@decision_app.command("validate")
def validate_decision(ctx: typer.Context, decision_id: str) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            with selection_context(source, (selector_hint("decision", decision_id, ()),)):
                return DecisionService(source, SystemClock()).validate(decision_id)

    execute(ctx, work)


@decision_app.command("save")
def save_decision(
    ctx: typer.Context,
    decision_id: str,
    note: Annotated[str, typer.Option("--note")] = "",
    if_draft_hash: Annotated[str | None, typer.Option("--if-draft-hash")] = None,
    if_decision_hash: Annotated[str | None, typer.Option("--if-decision-hash")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    def work(cli: CliState, op: str) -> object:
        with cli.source() as source:
            with selection_context(source, (selector_hint("decision", decision_id, ()),)):
                service = DecisionService(source, SystemClock(), new_id)
                if if_draft_hash is None or if_decision_hash is None:
                    view = service.read(decision_id)
                    draft_hash = if_draft_hash if if_draft_hash is not None else view.draft.etag
                    decision_hash = (
                        if_decision_hash if if_decision_hash is not None else view.decision.etag
                    )
                else:
                    draft_hash, decision_hash = if_draft_hash, if_decision_hash
                return service.save(
                    decision_id,
                    expected_draft_etag=draft_hash,
                    expected_decision_etag=decision_hash,
                    operation_id=op,
                    note=note,
                )

    _mutate(ctx, operation_id, work)


@decision_app.command("history")
def decision_history(
    ctx: typer.Context,
    decision_id: str,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 50,
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            with selection_context(source, (selector_hint("decision", decision_id, ()),)):
                return DecisionService(source, SystemClock()).history(
                    decision_id, cursor=cursor, limit=limit
                )

    execute(ctx, work)


@decision_app.command("diff")
def diff_decision(ctx: typer.Context, decision_id: str, before: str, after: str) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            hints = (
                selector_hint("decision", decision_id, ()),
                selector_hint("revision", before, (decision_id,)),
                selector_hint("revision", after, (decision_id,)),
            )
            with selection_context(source, hints):
                return DecisionService(source, SystemClock()).diff(decision_id, before, after)

    execute(ctx, work)


def _change(
    ctx: typer.Context,
    decision_id: str,
    operation_id: str | None,
    action: str,
    name: str | None = None,
    if_hash: str | None = None,
) -> None:
    def work(cli: CliState, op: str) -> object:
        with cli.source() as source:
            with selection_context(source, (selector_hint("decision", decision_id, ()),)):
                service = DecisionService(source, SystemClock())
                etag = if_hash if if_hash is not None else service.read(decision_id).decision.etag
                if action == "rename":
                    assert name is not None
                    return service.rename(decision_id, name, expected_etag=etag, operation_id=op)
                if action == "archive":
                    return service.archive(decision_id, expected_etag=etag, operation_id=op)
                return service.restore(decision_id, expected_etag=etag, operation_id=op)

    _mutate(ctx, operation_id, work)


@decision_app.command("rename")
def rename_decision(
    ctx: typer.Context,
    decision_id: str,
    name: Annotated[str, typer.Option("--name")],
    if_hash: Annotated[str | None, typer.Option("--if-hash")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    _change(ctx, decision_id, operation_id, "rename", name, if_hash)


@decision_app.command("archive")
def archive_decision(
    ctx: typer.Context,
    decision_id: str,
    if_hash: Annotated[str | None, typer.Option("--if-hash")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    _change(ctx, decision_id, operation_id, "archive", if_hash=if_hash)


@decision_app.command("restore")
def restore_decision(
    ctx: typer.Context,
    decision_id: str,
    if_hash: Annotated[str | None, typer.Option("--if-hash")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    _change(ctx, decision_id, operation_id, "restore", if_hash=if_hash)
