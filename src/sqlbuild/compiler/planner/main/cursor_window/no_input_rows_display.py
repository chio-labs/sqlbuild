"""Public display of cursor inputs that currently have no rows."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.resolve.cursor import (
    format_no_input_rows as _format_no_input_rows,
)


def format_no_input_rows(input_names: tuple[str, ...]) -> str:
    """Explain that a cursor window is empty because its inputs have no rows."""

    return _format_no_input_rows(input_names)
