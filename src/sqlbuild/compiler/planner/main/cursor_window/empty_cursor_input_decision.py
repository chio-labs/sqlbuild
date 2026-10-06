"""Public decision on whether empty cursor inputs leave a model with no window."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.resolve.cursor import (
    decide_empty_cursor_inputs as _decide_empty_cursor_inputs,
)
from sqlbuild.compiler.planner.models import EmptyCursorInputDecision


def decide_empty_cursor_inputs(
    *,
    empty_input_names: tuple[str, ...],
    waits_for_every_input: bool,
    inputs_with_rows: bool,
    has_window_start: bool,
) -> EmptyCursorInputDecision:
    """Decide whether empty cursor inputs leave no window, shared by planning and runtime."""

    return _decide_empty_cursor_inputs(
        empty_input_names=empty_input_names,
        waits_for_every_input=waits_for_every_input,
        inputs_with_rows=inputs_with_rows,
        has_window_start=has_window_start,
    )
