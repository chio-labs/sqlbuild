"""Public command surface header rendering entry."""

from __future__ import annotations

from sqlbuild.presentation._helpers.structure import format_surface_header as _format_surface_header
from sqlbuild.presentation.classes.cli_style import CliStyle


def format_surface_header(*, style: CliStyle, title: str, context: str | None = None) -> str:
    """Render a command surface header: accent title plus dim context."""

    return _format_surface_header(style=style, title=title, context=context)
