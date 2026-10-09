"""Safe command boundary and deterministic CLI presentation."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, TypeVar

import typer
from pydantic import BaseModel

from deykit.application.errors import ServiceFailure
from deykit.cli.context import CliState, state
from deykit.contracts.errors import ServiceError
from deykit.contracts.json_value import JsonDocument, JsonError
from deykit.contracts.selection import SelectionDetails

T = TypeVar("T")


@dataclass(frozen=True)
class CommandOutcome:
    data: object
    exit_code: Literal[0, 3, 4, 5] = 0
    warnings: tuple[ServiceError, ...] = ()


def _plain(value: Any) -> Any:
    if isinstance(value, JsonDocument):
        return {"source": value.source, "content_hash": value.content_hash}
    if isinstance(value, BaseModel):
        return _plain(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def _human_page(value: object) -> str | None:
    page = _plain(value)
    if not isinstance(page, dict) or not {"items", "total", "next_cursor"} <= set(page):
        return None
    items = page["items"]
    if not isinstance(items, list):
        return None
    columns = ("ID", "NAME", "STATUS")
    rows: list[tuple[str, str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            return None
        if "decision" in item:
            decision = item["decision"]["record"]
            rows.append(
                (
                    decision["id"],
                    decision["name"],
                    "archived"
                    if decision["archived"]
                    else "saved"
                    if decision["latest_revision_id"]
                    else "draft",
                )
            )
        elif "review" in item:
            review = item["review"]
            status = (
                "unlabelled"
                if item["label"] is None
                else "excluded"
                if item["reasons"]
                else "applicable"
            )
            rows.append((review["case_id"], review["question_id"], status))
            columns = ("CASE ID", "QUESTION ID", "STATUS")
        elif "profile" in item:
            profile = item["profile"]
            rows.append((profile["id"], profile["adapter"], profile["requested_model"]))
            columns = ("PROFILE ID", "ADAPTER", "MODEL")
        elif "record" in item:
            record = item["record"]
            if "dataset_id" in record:
                rows.append((record["id"], record["input_kind"], record["split"]))
                columns = ("CASE ID", "INPUT", "SPLIT")
            elif "content_hash" in record:
                rows.append((record["id"], record["created_at"], record["content_hash"]))
                columns = ("REVISION ID", "CREATED", "HASH")
            else:
                rows.append(
                    (record["id"], record["name"], "archived" if record["archived"] else "active")
                )
        else:
            return None
    lines = ["\t".join(columns), *("\t".join(row) for row in rows)]
    lines.append(f"total={page['total']} next_cursor={page['next_cursor'] or '-'}")
    return "\n".join(lines)


def emit(cli: CliState, data: object, warnings: tuple[ServiceError, ...] = ()) -> None:
    if cli.json_output:
        payload = {
            "schema_version": 1,
            "data": _plain(data),
            "warnings": [_plain(warning.safe_dict()) for warning in warnings],
        }
        typer.echo(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    else:
        typer.echo(
            _human_page(data)
            or json.dumps(_plain(data), sort_keys=True, ensure_ascii=False, indent=2)
        )
        for warning in warnings:
            typer.echo(f"Warning: {warning.message} ({warning.reason})", err=True)


def emit_error(
    cli: CliState, error: ServiceError, *, selection: SelectionDetails | None = None
) -> None:
    if cli.json_output:
        envelope: dict[str, object] = {"schema_version": 1, "error": error.safe_dict()}
        if selection is not None:
            envelope["selection"] = _plain(selection)
        typer.echo(
            json.dumps(
                envelope,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    else:
        reason = f" ({error.reason})" if error.reason else ""
        typer.echo(f"Error: {error.message}{reason}", err=True)
        if selection is not None:
            for choice in selection.choices:
                scope = "/".join(choice.scope)
                suffix = f" in {scope}" if scope else ""
                typer.echo(f"Available: {choice.kind}/{choice.resource_id}{suffix}", err=True)


def execute(ctx: typer.Context, work: Callable[[CliState], T]) -> None:
    execute_outcome(ctx, lambda cli: CommandOutcome(work(cli)))


def execute_outcome(ctx: typer.Context, work: Callable[[CliState], CommandOutcome]) -> None:
    """Render one result, then apply run/check exit precedence chosen by its service adapter."""
    cli = state(ctx)
    try:
        outcome = work(cli)
        emit(cli, outcome.data, outcome.warnings)
    except ServiceFailure as failure:
        emit_error(cli, failure.error, selection=failure.selection)
        raise typer.Exit(1 if failure.error.code == "internal_error" else 2) from None
    except JsonError as error:
        emit_error(cli, ServiceError(code="validation_error", reason=error.code))
        raise typer.Exit(2) from None
    except UnicodeDecodeError:
        emit_error(cli, ServiceError(code="validation_error", reason="invalid_utf8"))
        raise typer.Exit(2) from None
    except UnicodeEncodeError:
        emit_error(cli, ServiceError(code="validation_error", reason="invalid_unicode"))
        raise typer.Exit(2) from None
    except (OSError, ValueError):
        emit_error(cli, ServiceError(code="validation_error", reason="invalid_input"))
        raise typer.Exit(2) from None
    except Exception:
        emit_error(cli, ServiceError(code="internal_error"))
        raise typer.Exit(1) from None
    if outcome.exit_code:
        raise typer.Exit(outcome.exit_code)
