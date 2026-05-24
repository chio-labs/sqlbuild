"""Output formatting helpers for ingestr subprocess execution."""

from __future__ import annotations

from shlex import quote
from typing import TextIO


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
