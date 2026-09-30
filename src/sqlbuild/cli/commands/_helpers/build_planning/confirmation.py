"""Typed confirmation shared by the build safety policies."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.cli.commands.exceptions import CliUserError


def confirm_typed_action(
    *,
    action: str,
    non_interactive_help: str,
    warning: str,
    expected: str,
    input_stream: TextIO,
    output_stream: TextIO,
    code: str | None = None,
) -> None:
    """Ask the user to type the expected text, or fail when the run is not interactive."""

    if not input_stream.isatty():
        raise CliUserError(
            f"{action} requires confirmation",
            code=code,
            help=non_interactive_help,
        )
    _ = output_stream.write(f"{warning}\n\n")
    _ = output_stream.write(f"Type `{expected}` to continue: ")
    output_stream.flush()
    if input_stream.readline().strip() != expected:
        raise CliUserError(f"{action} cancelled", code=code)
