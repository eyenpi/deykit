"""Explicit source modes; arbitrary user JSON remains UTF-8 source text."""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

import typer

from deykit.application.errors import ServiceFailure
from deykit.contracts.errors import ServiceError


def source_text(
    *,
    file: Path | None = None,
    stdin: bool = False,
    editor: bool = False,
    initial: str = "",
) -> str:
    if sum((file is not None, stdin, editor)) != 1:
        raise ServiceFailure(ServiceError(code="validation_error", reason="input_mode_conflict"))
    if file is not None:
        return file.read_text(encoding="utf-8")
    if stdin:
        return typer.get_binary_stream("stdin").read().decode("utf-8", errors="strict")
    if not typer.get_text_stream("stdin").isatty():
        raise ServiceFailure(ServiceError(code="validation_error", reason="interactive_required"))
    editor_command = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    arguments = shlex.split(editor_command)
    if not arguments:
        raise ServiceFailure(ServiceError(code="validation_error", reason="editor_unavailable"))
    with tempfile.TemporaryDirectory(prefix="deykit-editor-") as directory:
        path = Path(directory) / "decision.json"
        path.write_text(initial, encoding="utf-8")
        try:
            with open("/dev/tty", "r+") as terminal:
                completed = subprocess.run(
                    [*arguments, str(path)],
                    check=False,
                    stdin=terminal,
                    stdout=terminal,
                    stderr=terminal,
                )
        except OSError:
            raise ServiceFailure(
                ServiceError(code="validation_error", reason="editor_unavailable")
            ) from None
        if completed.returncode != 0:
            raise ServiceFailure(ServiceError(code="validation_error", reason="editor_cancelled"))
        return path.read_text(encoding="utf-8")


def optional_source(*, file: Path | None = None, stdin: bool = False) -> str:
    if file is None and not stdin:
        return ""
    return source_text(file=file, stdin=stdin)
