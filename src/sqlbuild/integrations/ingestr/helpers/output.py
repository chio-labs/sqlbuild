"""Output formatting helpers for ingestr subprocess execution."""

from __future__ import annotations

from shlex import quote
from typing import TextIO

from sqlbuild.executor.load.models import LoaderContext
from sqlbuild.integrations.ingestr.models import IngestrCommandResult


def format_ingestr_command(command: tuple[str, ...]) -> str:
    """Return a display-safe ingestr command line."""

    return " ".join(quote(part) for part in command)


def write_external_output(*, stream: TextIO, label: str, output: str) -> None:
    """Write a labeled external command output block."""

    stream.write(f"{label}\n")
    stream.write(output)
    if not output.endswith("\n"):
        stream.write("\n")
    stream.write("\n")
    stream.flush()


def record_ingestr_output(*, ctx: LoaderContext, result: IngestrCommandResult) -> None:
    """Attach captured ingestr output to the loader lifecycle."""

    ctx.log("ingestr execution")
    ctx.log(result.command_display)
    if result.stdout:
        ctx.log(_format_output_block(label="ingestr stdout", output=result.stdout))
    if result.stderr:
        ctx.log(_format_output_block(label="ingestr stderr", output=result.stderr))


def _format_output_block(*, label: str, output: str) -> str:
    return f"{label}\n{output.rstrip()}"
