"""Expected-answer commands over review tokens and atomic LabelService edits."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Annotated, TypeVar, cast

import typer

from deykit.application.errors import ServiceFailure
from deykit.application.labels import Action, LabelEdit, LabelReview, LabelService, Provenance
from deykit.cli.context import CliState, SystemClock, new_operation_id
from deykit.cli.input import source_text
from deykit.cli.output import execute
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import JsonValue, parse_json

label_app = typer.Typer(help="Review expected answers without changing model input.")
T = TypeVar("T")
REVIEW_KEYS = {
    "decision_id",
    "dataset_id",
    "case_id",
    "question_id",
    "input_hash",
    "decision_etag",
    "draft_etag",
    "label_etag",
}


def register(root: typer.Typer) -> None:
    root.add_typer(label_app, name="label")


def _invalid(reason: str) -> ServiceFailure:
    return ServiceFailure(ServiceError(code="validation_error", reason=reason))


def _review(value: JsonValue) -> LabelReview:
    if not isinstance(value, dict) or set(value) != REVIEW_KEYS:
        raise _invalid("invalid_label_review")
    if any(type(value[key]) is not str for key in REVIEW_KEYS - {"label_etag"}):
        raise _invalid("invalid_label_review")
    if value["label_etag"] is not None and type(value["label_etag"]) is not str:
        raise _invalid("invalid_label_review")
    return LabelReview(
        decision_id=cast(str, value["decision_id"]),
        dataset_id=cast(str, value["dataset_id"]),
        case_id=cast(str, value["case_id"]),
        question_id=cast(str, value["question_id"]),
        input_hash=cast(str, value["input_hash"]),
        decision_etag=cast(str, value["decision_etag"]),
        draft_etag=cast(str, value["draft_etag"]),
        label_etag=value["label_etag"],
    )


def _review_file(path: Path) -> LabelReview:
    value = parse_json(path.read_text(encoding="utf-8"))
    if isinstance(value, dict) and "data" in value:
        nested = value["data"]
        if isinstance(nested, dict) and "review" in nested:
            value = nested["review"]
    return _review(value)


def _selected_review(
    service: LabelService,
    decision: str,
    dataset: str,
    case_id: str,
    review_file: Path | None,
) -> LabelReview:
    review = (
        _review_file(review_file)
        if review_file is not None
        else service.read(decision, dataset, case_id).review
    )
    if (review.decision_id, review.dataset_id, review.case_id) != (decision, dataset, case_id):
        raise _invalid("label_review_target_mismatch")
    return review


def _mutate(
    ctx: typer.Context, operation_id: str | None, work: Callable[[CliState, str], T]
) -> None:
    actual = new_operation_id(operation_id)
    execute(ctx, lambda cli: {"operation_id": actual, "result": work(cli, actual)})


@label_app.command("list")
def list_labels(
    ctx: typer.Context,
    decision: Annotated[str, typer.Option("--decision")],
    dataset: Annotated[str, typer.Option("--dataset")],
    status: Annotated[str | None, typer.Option("--status")] = None,
    cursor: Annotated[str | None, typer.Option("--cursor")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 50,
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            return LabelService(source, SystemClock()).list(
                decision, dataset, status=status, cursor=cursor, limit=limit
            )

    execute(ctx, work)


@label_app.command("show")
def show_label(
    ctx: typer.Context,
    case_id: str,
    decision: Annotated[str, typer.Option("--decision")],
    dataset: Annotated[str, typer.Option("--dataset")],
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            return LabelService(source, SystemClock()).read(decision, dataset, case_id)

    execute(ctx, work)


@label_app.command("history")
def label_history(
    ctx: typer.Context,
    case_id: str,
    decision: Annotated[str, typer.Option("--decision")],
    dataset: Annotated[str, typer.Option("--dataset")],
) -> None:
    def work(cli: CliState) -> object:
        with cli.source() as source:
            return LabelService(source, SystemClock()).history(decision, dataset, case_id)

    execute(ctx, work)


@label_app.command("set")
def set_label(
    ctx: typer.Context,
    decision: Annotated[str, typer.Option("--decision")],
    dataset: Annotated[str, typer.Option("--dataset")],
    case_id: Annotated[str | None, typer.Argument()] = None,
    expected: Annotated[list[str] | None, typer.Option("--expected")] = None,
    provenance: Annotated[str | None, typer.Option("--provenance")] = None,
    note: Annotated[str | None, typer.Option("--note")] = None,
    file: Annotated[Path | None, typer.Option("--file")] = None,
    stdin: Annotated[bool, typer.Option("--stdin")] = False,
    review: Annotated[Path | None, typer.Option("--review")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    def work(cli: CliState, op: str) -> object:
        batch_mode = file is not None or stdin
        if batch_mode:
            if case_id is not None or expected or provenance or note or review:
                raise _invalid("input_mode_conflict")
            data = parse_json(source_text(file=file, stdin=stdin))
            return _batch(cli, decision, dataset, data, op)
        if case_id is None:
            raise _invalid("case_id_required")
        with cli.source() as source:
            service = LabelService(source, SystemClock())
            token = _selected_review(service, decision, dataset, case_id, review)
            return service.set(
                token,
                tuple(expected or ()),
                provenance=cast(Provenance | None, provenance),
                note=note,
                operation_id=op,
            )

    _mutate(ctx, operation_id, work)


def _batch(cli: CliState, decision: str, dataset: str, data: JsonValue, op: str) -> object:
    if (
        not isinstance(data, dict)
        or set(data) != {"schema_version", "items"}
        or type(data["schema_version"]) is not Decimal
        or data["schema_version"] != Decimal(1)
        or not isinstance(data["items"], list)
    ):
        raise _invalid("invalid_label_batch")
    with cli.source() as source:
        service = LabelService(source, SystemClock())
        edits: list[LabelEdit] = []
        for item in data["items"]:
            if not isinstance(item, dict) or set(item) - {
                "case_id",
                "question_id",
                "action",
                "expected",
                "provenance",
                "note",
                "review",
            }:
                raise _invalid("invalid_label_batch")
            case_id = item.get("case_id")
            action = item.get("action")
            if type(case_id) is not str or action not in ("set", "clear", "dispute", "resolve"):
                raise _invalid("invalid_label_batch")
            supplied = item.get("review")
            question_id = item.get("question_id")
            if question_id is not None and type(question_id) is not str:
                raise _invalid("invalid_label_batch")
            token = (
                _review(supplied)
                if supplied is not None
                else service.read(decision, dataset, case_id, question_id=question_id).review
            )
            if (token.decision_id, token.dataset_id, token.case_id) != (decision, dataset, case_id):
                raise _invalid("label_review_target_mismatch")
            if question_id is not None and token.question_id != question_id:
                raise _invalid("label_review_target_mismatch")
            values = item.get("expected", [])
            if not isinstance(values, list) or any(type(value) is not str for value in values):
                raise _invalid("invalid_label_batch")
            provenance = item.get("provenance")
            note = item.get("note")
            if provenance is not None and type(provenance) is not str:
                raise _invalid("invalid_label_batch")
            if note is not None and type(note) is not str:
                raise _invalid("invalid_label_batch")
            edits.append(
                LabelEdit(
                    token,
                    cast(Action, action),
                    tuple(cast(list[str], values)),
                    cast(Provenance | None, provenance),
                    note,
                )
            )
        return service.batch(tuple(edits), operation_id=op)


def _single_action(
    ctx: typer.Context,
    decision: str,
    dataset: str,
    case_id: str,
    review: Path | None,
    operation_id: str | None,
    action: str,
    expected: tuple[str, ...] = (),
    provenance: str | None = None,
    note: str | None = None,
) -> None:
    def work(cli: CliState, op: str) -> object:
        with cli.source() as source:
            service = LabelService(source, SystemClock())
            token = _selected_review(service, decision, dataset, case_id, review)
            if action == "clear":
                return service.clear(token, operation_id=op)
            if action == "dispute":
                return service.dispute(token, reason=note or "", operation_id=op)
            return service.resolve(
                token,
                expected,
                provenance=cast(Provenance | None, provenance),
                note=note,
                operation_id=op,
            )

    _mutate(ctx, operation_id, work)


@label_app.command("clear")
def clear_label(
    ctx: typer.Context,
    case_id: str,
    decision: Annotated[str, typer.Option("--decision")],
    dataset: Annotated[str, typer.Option("--dataset")],
    review: Annotated[Path | None, typer.Option("--review")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    _single_action(ctx, decision, dataset, case_id, review, operation_id, "clear")


@label_app.command("dispute")
def dispute_label(
    ctx: typer.Context,
    case_id: str,
    decision: Annotated[str, typer.Option("--decision")],
    dataset: Annotated[str, typer.Option("--dataset")],
    reason: Annotated[str, typer.Option("--reason")],
    review: Annotated[Path | None, typer.Option("--review")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    _single_action(ctx, decision, dataset, case_id, review, operation_id, "dispute", note=reason)


@label_app.command("resolve")
def resolve_label(
    ctx: typer.Context,
    case_id: str,
    decision: Annotated[str, typer.Option("--decision")],
    dataset: Annotated[str, typer.Option("--dataset")],
    expected: Annotated[list[str] | None, typer.Option("--expected")] = None,
    provenance: Annotated[str | None, typer.Option("--provenance")] = None,
    note: Annotated[str | None, typer.Option("--note")] = None,
    review: Annotated[Path | None, typer.Option("--review")] = None,
    operation_id: Annotated[str | None, typer.Option("--operation-id")] = None,
) -> None:
    _single_action(
        ctx,
        decision,
        dataset,
        case_id,
        review,
        operation_id,
        "resolve",
        tuple(expected or ()),
        provenance,
        note,
    )
