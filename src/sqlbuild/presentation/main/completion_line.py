"""Public completion summary line rendering entry."""

from __future__ import annotations

from sqlbuild.presentation._helpers.structure import (
    format_completion_line as _format_completion_line,
)
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.types import CompletionState


def format_completion_line(
    *, style: CliStyle, state: CompletionState, label: str, summary: str | None = None
) -> str:
    """Render a single-line completion summary: state glyph, label, trailing summary."""

    return _format_completion_line(style=style, state=state, label=label, summary=summary)
