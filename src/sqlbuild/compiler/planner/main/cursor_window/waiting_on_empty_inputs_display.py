"""Public display of a cursor window that waits on empty inputs while others have rows."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.resolve.cursor import (
    format_waiting_on_empty_inputs as _format_waiting_on_empty_inputs,
)


def format_waiting_on_empty_inputs(input_names: tuple[str, ...]) -> str:
    """Explain that a cursor window waits on empty inputs while other inputs have rows."""

    return _format_waiting_on_empty_inputs(input_names)
