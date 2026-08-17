"""Public fixed-width status cell rendering entry."""

from __future__ import annotations

from sqlbuild.presentation._helpers.structure import format_status_cell as _format_status_cell
from sqlbuild.presentation.classes.cli_style import CliStyle


def format_status_cell(*, style: CliStyle, status: str, width: int = 6) -> str:
    """Render a fixed-width status cell padded on the plain text, not the ANSI text."""

    return _format_status_cell(style=style, status=status, width=width)
